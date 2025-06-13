import os
import uuid
from datetime import timedelta
from io import BytesIO

from PIL import Image
from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.validators import FileExtensionValidator
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.utils.translation import gettext_lazy as _

from .manager import UserManager
from .utils import generate_secure_code


def profile_image_path(instance, filename):
    """Generate upload path for profile images"""
    try:
        user_id = instance.user.id if instance.user else 'unknown'
        return f"profiles/{user_id}/{filename}"
    except (AttributeError, Profile.user.RelatedObjectDoesNotExist):
        return f"profiles/temp/{filename}"


def validate_image_size(image):
    """
    Validate image file size (max 5MB).
    """
    max_size = 5 * 1024 * 1024  # 5MB
    if image.size > max_size:
        raise ValidationError(_('Image file size cannot exceed 5MB.'))


class User(AbstractBaseUser, PermissionsMixin):
    """
    Custom User model that extends AbstractBaseUser and PermissionsMixin.
    Uses email as the unique identifier instead of username.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text=_("Unique identifier for the user")
    )

    email = models.EmailField(
        _("email address"),
        unique=True,
        error_messages={
            'unique': _("A user with that email already exists."),
        },
        help_text=_("Required. Enter a valid email address.")
    )

    username = models.CharField(
        _("username"),
        max_length=150,
        unique=True,
        validators=[
            RegexValidator(
                regex=r'^[\w.@+-]+$',
                message=_(
                    'Enter a valid username. This value may contain only letters, numbers, and @/./+/-/_ characters.')
            )
        ],
        help_text=_("Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only."),
        error_messages={
            'unique': _("A user with that username already exists."),
        }
    )

    first_name = models.CharField(
        _("first name"),
        max_length=150,
        blank=True,
        help_text=_("User's first name")
    )

    last_name = models.CharField(
        _("last name"),
        max_length=150,
        blank=True,
        help_text=_("User's last name")
    )

    secure_code = models.CharField(
        _("secure code"),
        max_length=6,
        null=True,
        blank=True,
        help_text=_("Auto-generated secure code for user verification")
    )

    secure_code_expiry = models.DateTimeField(verbose_name=_("secure code expiry"),
                                              help_text=_("The date and time when the secure code expires"), blank=True,
                                              null=True)

    is_active = models.BooleanField(
        _("active"),
        default=False,
        help_text=_(
            "Designates whether this user should be treated as active. "
            "Unselect this instead of deleting accounts."
        ),
    )

    is_staff = models.BooleanField(
        _("staff status"),
        default=False,
        help_text=_("Designates whether the user can log into this admin site."),
    )

    is_verified = models.BooleanField(
        _("verified"),
        default=False,
        help_text=_("Designates whether the user has verified their email address."),
    )

    date_joined = models.DateTimeField(
        _("date joined"),
        default=timezone.now,
        help_text=_("The date and time when the user account was created")
    )

    last_login = models.DateTimeField(
        _("last login"),
        blank=True,
        null=True,
        help_text=_("The date and time of the user's last login")
    )

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    class Meta:
        verbose_name = _("User")
        verbose_name_plural = _("Users")
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['secure_code']),
            models.Index(fields=['is_active', 'is_staff']),
        ]

    def __str__(self):
        return self.email

    def clean(self):
        super().clean()
        self.email = self.__class__.objects.normalize_email(self.email)

    def save(self, *args, **kwargs):
        if not self.pk and not self.secure_code:
            self.secure_code = generate_secure_code()
            self.secure_code_expiry = timezone.now() + timedelta(minutes=10)

        self.email = self.__class__.objects.normalize_email(self.email)

        super().save(*args, **kwargs)

    @property
    def full_name(self):
        """Return the user's full name."""
        return f"{self.first_name} {self.last_name}".strip()

    def get_short_name(self):
        """Return the user's first name."""
        return self.first_name

    def get_full_name(self):
        """Return the user's full name."""
        return self.full_name

    def activate(self):
        """Activate the user account."""
        self.is_active = True
        self.is_verified = True
        self.save(update_fields=['is_active', 'is_verified'])

    def deactivate(self):
        """Deactivate the user account."""
        self.is_active = False
        self.save(update_fields=['is_active'])

    def verify_user(self, secure_code=None):
        """Verify the user account."""
        if self.is_verified:
            raise ValueError(_("User is already verified."))
        if secure_code is None:
            raise ValueError(_("Secure code is required for verification."))
        if not constant_time_compare(str(self.secure_code), str(secure_code)):
            raise ValueError(_("Invalid secure code."))
        if self.secure_code_expiry < timezone.now():
            self.secure_code = None
            self.secure_code_expiry = None
            self.save(update_fields=['secure_code', 'secure_code_expiry'])
            raise ValueError(_("Secure code has expired."))

        self.is_verified = True
        self.is_active = True
        self.secure_code = None
        self.secure_code_expiry = None
        self.save(update_fields=['is_verified', 'is_active', 'secure_code', 'secure_code_expiry'])
        self.refresh_from_db()
        print(f"After save: secure_code_expiry = {self.secure_code_expiry}")

    def check_user_is_verified(self, secure_code=None) -> bool:
        """
        Check if the user is verified, attempting verification if needed.
        :param secure_code: The secure code for verification (required if not already verified)
        :return: True if the user is verified, False otherwise.
        """
        if self.is_verified:
            return True

        if secure_code is None:
            return False

        try:
            self.verify_user(secure_code)
            return True
        except ValueError:
            self.secure_code = generate_secure_code()
            self.secure_code_expiry = timezone.now() + timedelta(minutes=15)
            self.save(update_fields=['secure_code', 'secure_code_expiry'])
            return False

    def generate_new_secure_code(self):
        """Generate a new secure code for the user."""
        self.secure_code = generate_secure_code()
        self.secure_code_expiry = timezone.now() + timedelta(minutes=5)
        self.save(update_fields=['secure_code', 'secure_code_expiry'])
        return  self.secure_code


class Profile(models.Model):
    """
Profile model that extends the User model with additional fields.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, unique=True,
                          help_text=_("Unique identifier for the user")
                          )

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile', verbose_name='User',
                                help_text="The user associated with this profile")

    bio = models.TextField(null=True, blank=True, verbose_name='About yourself',
                           help_text="A brief biography or description of the user")

    profile_image = models.ImageField(
        _('profile image'),
        upload_to=profile_image_path,
        blank=True,
        null=True,
        validators=[
            FileExtensionValidator(
                allowed_extensions=['jpg', 'jpeg', 'png', 'webp']
            ),
            validate_image_size
        ],
        help_text=_('Upload a profile image (JPG, PNG, WebP). Max size: 5MB.')
    )

    thumbnail = models.ImageField(
        _('thumbnail'),
        upload_to=profile_image_path,
        blank=True,
        null=True,
        editable=False
    )

    location = models.CharField(max_length=300, verbose_name='Location',
                                help_text="The location of the user, e.g., country or city")

    city = models.CharField(max_length=300, verbose_name='City', help_text="The city where the user resides")

    def __str__(self):
        return self.user.username

    def save(self, *args, **kwargs):
        if self.pk:
            try:
                old_profile = Profile.objects.get(pk=self.pk)
                if old_profile.profile_image != self.profile_image:
                    self.delete_old_images(old_profile)
            except Profile.DoesNotExist:
                pass

        super().save(*args, **kwargs)

        # Generate thumbnail after saving
        if self.profile_image:
            self.create_thumbnail()

    def delete_old_images(self, old_profile):
        """Delete old profile images and thumbnails."""
        if old_profile.profile_image:
            if default_storage.exists(old_profile.profile_image.name):
                default_storage.delete(old_profile.profile_image.name)

        if old_profile.thumbnail:
            if default_storage.exists(old_profile.thumbnail.name):
                default_storage.delete(old_profile.thumbnail.name)

    def create_thumbnail(self, size=(150, 150)):
        """
        Create a thumbnail from the profile image.
        """
        if not self.profile_image:
            return

        try:
            image = Image.open(self.profile_image.path)

            if image.mode in ('RGBA', 'LA', 'P'):
                background = Image.new('RGB', image.size, (255, 255, 255))
                if image.mode == 'P':
                    image = image.convert('RGBA')
                background.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
                image = background

            image.thumbnail(size, Image.Resampling.LANCZOS)

            thumb_io = BytesIO()
            image.save(thumb_io, format='JPEG', quality=85, optimize=True)
            thumb_io.seek(0)

            thumb_name = f"thumb_{os.path.basename(self.profile_image.name)}"
            thumb_path = f"profiles/{self.user.id}/{thumb_name}"

            self.thumbnail.save(
                thumb_path,
                ContentFile(thumb_io.read()),
                save=False
            )

            Profile.objects.filter(pk=self.pk).update(thumbnail=self.thumbnail)

        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error creating thumbnail for user {self.user.id}: {str(e)}")

    def get_profile_image_url(self):
        """Get profile image URL with fallback to default."""
        if self.profile_image:
            return self.profile_image.url
        return self.get_default_image_url()

    def get_thumbnail_url(self):
        """Get thumbnail URL with fallback to default."""
        if self.thumbnail:
            return self.thumbnail.url
        return self.get_default_image_url()

    def get_default_image_url(self):
        """Return default profile image URL."""
        return f"{settings.STATIC_URL}images/default-profile.png"

    def delete_images(self):
        """Delete all associated images."""
        if self.profile_image:
            if default_storage.exists(self.profile_image.name):
                default_storage.delete(self.profile_image.name)

        if self.thumbnail:
            if default_storage.exists(self.thumbnail.name):
                default_storage.delete(self.thumbnail.name)

    def delete(self, *args, **kwargs):
        """Override delete to clean up image files."""
        self.delete_images()
        super().delete(*args, **kwargs)
