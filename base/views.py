from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status, permissions
from rest_framework.generics import GenericAPIView
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from base.models import Profile
from base.serializers import RegisterSerializer, LoginSerializer, UserProfileSerializer, VerifyUserSerializer, \
    ChangePasswordSerializer, ResetPasswordSerializer, ResendVerificationCodeSerializer
from base.tasks import send_email_with_template
from base.utils import generate_secure_code

User = get_user_model()


class RegisterAPIView(GenericAPIView):
    """
    API view for user registration.
    """
    serializer_class = RegisterSerializer

    @swagger_auto_schema(
        operation_description="Register a new user",
        responses={
            200: openapi.Response("Account created successfully"),
            400: openapi.Response("Invalid token or email"),
        }
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            with transaction.atomic():
                password = serializer.validated_data['password']
                user = serializer.save()
                user.set_password(password)

                if not user.secure_code:
                    user.generate_new_secure_code()

                user.save()

                # All database operations completed successfully

            # Email sending outside transaction since it's an external operation
            data = {
                "subject": "Verify your email",
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
            print("Email sent to:", user.email)
            print("With token:", user.secure_code)

            return Response({
                "Message": "Successfully registered"
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response({
                "error": str(e)
            }, status=status.HTTP_400_BAD_REQUEST)


class VerifyUserAPIView(GenericAPIView):
    """
    API view for verifying user email using a verification token.
    """
    serializer_class = VerifyUserSerializer

    @swagger_auto_schema(
        operation_description="Verify user email using verification token",
        responses={
            200: openapi.Response("User verified successfully"),
            400: openapi.Response("Invalid token or email"),
        }
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response({
            "message": "User verified successfully"
        }, status=status.HTTP_200_OK)


class LoginAPIView(GenericAPIView):
    """
    API view for user login.
    """
    serializer_class = LoginSerializer

    @swagger_auto_schema(
        operation_description="Login a user",
        responses={
            200: openapi.Response("User login successfully"),
            400: openapi.Response("Invalid credentials or user not verified"),
        }
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        user = User.objects.get(email=email)

        if not user.is_verified:
            return Response({
                "message": "User is not verified. Please verify your email first.",
            }, status=status.HTTP_403_FORBIDDEN)

        token = RefreshToken.for_user(user)
        access_token = token.access_token
        return Response({
            "message": "Successfully logged in",
            "email": email,
            "access_token": str(access_token),
            "refresh_token": str(token),
        }, status=status.HTTP_200_OK)


class ChangePasswordAPIView(GenericAPIView):
    """
    API view for requesting a password reset.
    """
    serializer_class = ChangePasswordSerializer
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Forgot password request",
        responses={
            200: openapi.Response("New code or token send successfully"),
            400: openapi.Response("Invalid  email"),
        }
    )
    def post(self, request, *args, **kwargs):
        """
          Handle password change request  and the user must be login to carry out this request.
        :param request:
        :param args:
        :param kwargs:
        :return: updated user password in the system
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        new_password = serializer.validated_data['new_password']
        user.set_password(new_password)
        user.save()
        return Response({
            "message": "Password changed successfully",
            "email": user.email
        }, status=status.HTTP_200_OK)


class ResetPasswordAPIView(GenericAPIView):
    """
    API view for resetting the user's password using a reset token.
    """
    serializer_class = ResetPasswordSerializer
    permission_classes = [permissions.AllowAny]

    @swagger_auto_schema(
        operation_description="Reset user password with token",
        responses={
            200: openapi.Response("Password reset successfully"),
            400: openapi.Response("Invalid token or password validation failed"),
        }
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        serializer.save()

        return Response({
            "message": "Password reset successfully"
        }, status=status.HTTP_200_OK)


class ResendVerificationCodeAPIView(GenericAPIView):
    """
    API view for resending the verification code to the user's email.
    """
    serializer_class = ResendVerificationCodeSerializer

    @swagger_auto_schema(
        operation_description="Resend verification code to user's email",
        responses={
            200: openapi.Response("Verification code resent successfully"),
            400: openapi.Response("Invalid email or user not found"),
        }
    )
    def post(self, request, *args, **kwargs):
        """
        Resend verification code to the user's email.
        :param request: The HTTP request containing the email.
        :return: A response indicating the success or failure of the operation.
        200: openapi.Response("Verification code resent successfully"),
        400: openapi.Response("Invalid email or user not found"),
        """
        ip_address = request.META.get('REMOTE_ADDR')
        cache_key = f"forgot_password_{ip_address}"

        if cache.get(cache_key):
            return Response({
                "error": "Too many requests. Please try again later."
            }, status=status.HTTP_429_TOO_MANY_REQUESTS)

        cache.set(cache_key, True, timeout=60)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        user = User.objects.get(email=email)
        user.secure_code = generate_secure_code()
        user.secure_code_expiry = timezone.now() + timedelta(minutes=10)
        user.save(update_fields=['secure_code', 'secure_code_expiry'])
        data = {
            "subject": "Resend verification code",

        }
        context = {
            "email": user.email,
            "token": user.secure_code,
            "username": user.username,
            "expiration": user.secure_code_expiry,
            "app_name": "ResolveMeQ",
            "verification_link": settings.FRONTEND_URL + reverse('verify_user'),
        }
        send_email_with_template.delay(data, 'welcome.html', context, [user.email])
        return Response({
            "message": "Verification code resent successfully."
        }, status=status.HTTP_200_OK)


class CurrentUserProfileView(GenericAPIView):
    """
    Manage the current user's profile at a fixed endpoint.
    """
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = UserProfileSerializer

    def get_object(self):
        return get_object_or_404(Profile, user=self.request.user)

    def get(self, request):
        profile = self.get_object()
        serializer = self.get_serializer(profile)
        return Response(serializer.data)

    def patch(self, request):
        profile = self.get_object()
        serializer = self.get_serializer(profile, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request):
        profile = self.get_object()
        profile.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
