from datetime import timedelta

from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from rest_framework import serializers

from .models import User, Profile
from .tasks import send_email_with_template
from .utils import ImageProcessor, generate_secure_code


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['email', 'username', 'password', 'confirm_password']

    def validate(self, data):
        password = data['password']
        confirm_password = data.pop('confirm_password')
        if password != confirm_password:
            raise serializers.ValidationError('Passwords do not match')

        if User.objects.filter(username=data['username']).exists():
            raise serializers.ValidationError('Username already exists')

        if User.objects.filter(email=data['email']).exists():
            raise serializers.ValidationError('Email already registered')
        return data


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        email = data['email']
        password = data['password']
        user = User.objects.filter(email=email).first()

        if not user:
            raise serializers.ValidationError('No user found with this email')

        if not user.is_verified:
            raise serializers.ValidationError('User is not verified')

        if not user.check_password(password):
            raise serializers.ValidationError('Invalid password')

        return data


class VerifyUserSerializer(serializers.Serializer):
    token = serializers.CharField(write_only=True, required=True)
    email = serializers.EmailField(write_only=True, required=True)

    def validate(self, data):
        token = data['token']
        email = data['email']

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError('Invalid email or token')

        try:
            user.verify_user(token)
        except ValueError as e:
            error_message = str(e)

            if "expired" in error_message.lower() and not user.is_verified:
                user.secure_code = generate_secure_code()
                user.secure_code_expiry = timezone.now() + timedelta(minutes=15)
                user.save(update_fields=['secure_code', 'secure_code_expiry'])
                data = {
                    "subject": "New verification code",

                }
                context = {
                    "email": user.email,
                    "token": user.secure_code,
                    "username": user.username,
                    "expiration": user.secure_code_expiry,
                    "app_name": "ResolveMeQ",
                    "verification_link": settings.FRONTEND_URL + reverse('verify-user'),
                }
                send_email_with_template.delay(data, 'welcome.html', context, [user.email])
                error_message += " A new verification code has been sent."

            raise serializers.ValidationError(error_message)

        return data


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True, required=True)
    new_password = serializers.CharField(write_only=True, required=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True, required=True)

    def validate_new_password(self, value):
        """
        Validate that the new password meets the requirements.
        :param value: new_password
        :return: new_password
        """
        if len(value) < 8:
            raise serializers.ValidationError("Password must be at least 8 characters long")
        return value

    def validate(self, data):
        """
        Validate that the old password is correct and new passwords match.
        :param data:
        :return: validated data
        """
        user = self.context['request'].user
        old_password = data['old_password']
        new_password = data['new_password']
        confirm_password = data['confirm_password']

        if not user.check_password(old_password):
            raise serializers.ValidationError("Old password is incorrect")

        if not constant_time_compare(new_password, confirm_password):
            raise serializers.ValidationError("New passwords do not match")

        if constant_time_compare(old_password, new_password):
            raise serializers.ValidationError("Old password cannot be the same as new password")

        return data


class ResetPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    token = serializers.CharField(required=True)
    new_password = serializers.CharField(write_only=True, required=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True, required=True)

    def validate_new_password(self, value):
        if len(value) < 8:
            raise serializers.ValidationError("Password must be at least 8 characters long")
        return value

    def validate(self, data):
        if not constant_time_compare(str(data['new_password']), str(data['confirm_password'])):
            raise serializers.ValidationError("Passwords do not match")

        email = data['email']
        token = data['token']

        try:
            user = User.objects.get(email=email)

            if not user.secure_code or not constant_time_compare(str(user.secure_code), str(token)):
                raise serializers.ValidationError("Invalid or expired reset token")

            if user.secure_code_expiry and user.secure_code_expiry < timezone.now():
                raise serializers.ValidationError("Reset token has expired")

        except User.DoesNotExist:
            raise serializers.ValidationError("Invalid reset token")

        return data

    def save(self, **kwargs):
        email = self.validated_data['email']
        new_password = self.validated_data['new_password']
        token = self.validated_data['token']

        try:
            user = User.objects.get(email=email)

            if (user.secure_code and
                    constant_time_compare(str(user.secure_code), str(token)) and
                    user.secure_code_expiry and
                    user.secure_code_expiry >= timezone.now()):

                user.set_password(new_password)

                user.secure_code = None
                user.secure_code_expiry = None

                user.save(update_fields=['password', 'secure_code', 'secure_code_expiry'])

            else:
                raise serializers.ValidationError("Invalid or expired reset token")

        except User.DoesNotExist:
            raise serializers.ValidationError("Invalid reset token")


class ResendVerificationCodeSerializer(serializers.Serializer):
    """
    Serializer for resending verification code to the user.
    """
    email = serializers.EmailField(required=True)

    def validate_email(self, value):
        """
        Validate that the email exists and is not verified.
        """
        try:
            user = User.objects.get(email=value)
            if user.is_verified:
                raise serializers.ValidationError("User is already verified")
        except User.DoesNotExist:
            raise serializers.ValidationError("User with this email does not exist")
        return value


class UserProfileSerializer(serializers.ModelSerializer):
    """
    Serializer for user profile with image handling.
    """
    profile_image = serializers.ImageField(
        required=False,
        allow_null=True,
        validators=[ImageProcessor.validate_image]
    )

    thumbnail_url = serializers.SerializerMethodField()
    profile_image_url = serializers.SerializerMethodField()
    user_email = serializers.CharField(source='user.email', read_only=True)
    user_full_name = serializers.CharField(source='user.full_name', read_only=True)

    class Meta:
        model = Profile
        fields = [
            'id',
            'user_email',
            'user_full_name',
            'profile_image',
            'profile_image_url',
            'thumbnail_url',
            'bio',
            'location',
            'city'
        ]

    def get_profile_image_url(self, obj):
        """Get full URL for profile image."""
        if obj.profile_image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.profile_image.url)
            return obj.profile_image.url
        return obj.get_default_image_url()

    def get_thumbnail_url(self, obj):
        """Get full URL for thumbnail."""
        if obj.thumbnail:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.thumbnail.url)
            return obj.thumbnail.url
        return obj.get_default_image_url()

    def validate_profile_image(self, value):
        """Additional validation for profile image."""
        if value:
            ImageProcessor.validate_image(value)
        return value



    def update(self, instance, validated_data):
        """Handle image updates properly."""
        profile_image = validated_data.get('profile_image')

        if profile_image:
            optimized_image = ImageProcessor.optimize_image(profile_image)
            validated_data['profile_image'] = optimized_image

        return super().update(instance, validated_data)
