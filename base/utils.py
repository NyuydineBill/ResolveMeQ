import base64
import logging
import mimetypes
import os
from email.mime.image import MIMEImage
from io import BytesIO

from PIL import Image, ImageOps
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.mail import EmailMultiAlternatives
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


def generate_secure_code(length: int = 6) -> str:
    """
    Generate a random numeric code of a specified length.

    Args:
        length (int): The length of the code to generate. Default is 6.

    Returns:
        str: A random numeric code of the specified length.
    """
    import random
    import string

    return ''.join(random.choice(string.digits) for _ in range(length))


class ImageProcessor:
    """
    Utility class for image processing operations.
    """

    ALLOWED_FORMATS = ['JPEG', 'PNG', 'WEBP']
    MAX_FILE_SIZE = 5 * 1024 * 1024
    THUMBNAIL_SIZES = {
        'small': (50, 50),
        'medium': (150, 150),
        'large': (300, 300),
    }

    @staticmethod
    def validate_image(image_file):
        """
        Validate uploaded image file.
        """
        if image_file.size > ImageProcessor.MAX_FILE_SIZE:
            raise ValidationError(
                _('Image file size cannot exceed %(max_size)s MB.') % {
                    'max_size': ImageProcessor.MAX_FILE_SIZE / (1024 * 1024)
                }
            )

        try:
            img = Image.open(image_file)
            img.verify()
        except Exception:
            raise ValidationError(_('Invalid image file.'))

        image_file.seek(0)
        img = Image.open(image_file)
        if img.format not in ImageProcessor.ALLOWED_FORMATS:
            raise ValidationError(
                _('Unsupported image format. Allowed formats: %(formats)s') % {
                    'formats': ', '.join(ImageProcessor.ALLOWED_FORMATS)
                }
            )

    @staticmethod
    def optimize_image(image_file, max_size=(800, 800), quality=85):
        """
        Optimize image for web use.
        """
        img = Image.open(image_file)

        if img.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            if img.mode == 'RGBA':
                background.paste(img, mask=img.split()[-1])
            else:
                background.paste(img)
            img = background

        img = ImageOps.exif_transpose(img)

        if img.size[0] > max_size[0] or img.size[1] > max_size[1]:
            img.thumbnail(max_size, Image.Resampling.LANCZOS)

        output = BytesIO()
        img.save(output, format='JPEG', quality=quality, optimize=True)
        output.seek(0)

        # Use the original filename or generate a new one, ensuring it has a .jpg extension
        filename = os.path.splitext(image_file.name)[0] + '.jpg'
        return ContentFile(output.read(), name=filename)
    @staticmethod
    def create_thumbnail(image_file, size=(150, 150), crop=True):
        """
        Create thumbnail from image.
        """
        img = Image.open(image_file)

        if img.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            if img.mode == 'RGBA':
                background.paste(img, mask=img.split()[-1])
            else:
                background.paste(img)
            img = background

        img = ImageOps.exif_transpose(img)

        if crop:
            img = ImageOps.fit(img, size, Image.Resampling.LANCZOS)
        else:
            img.thumbnail(size, Image.Resampling.LANCZOS)

        output = BytesIO()
        img.save(output, format='JPEG', quality=85, optimize=True)
        output.seek(0)

        return ContentFile(output.read())

    @staticmethod
    def get_image_info(image_file):
        """
        Get image information.
        """
        img = Image.open(image_file)
        return {
            'format': img.format,
            'mode': img.mode,
            'size': img.size,
            'width': img.size[0],
            'height': img.size[1],
        }


def validate_profile_image(image):
    """
    Validator for profile images.
    """
    ImageProcessor.validate_image(image)


def validate_image_aspect_ratio(image, min_ratio=0.5, max_ratio=2.0):
    """
    Validate image aspect ratio.
    """
    img = Image.open(image)
    ratio = img.size[0] / img.size[1]

    if ratio < min_ratio or ratio > max_ratio:
        raise ValidationError(
            _('Image aspect ratio must be between %(min)s and %(max)s.') % {
                'min': min_ratio,
                'max': max_ratio
            }
        )


class EmailImageHandler:
    """Utility class for handling images in emails"""

    DEFAULT_IMAGES = {
        'logo': 'images/logo.png',
        'facebook_icon': 'social/facebook2x.png',
        'twitter_icon': 'social/twitter2x.png',
        'linkedin_icon': 'social/linkedin2x.png',
        'instagram_icon': 'social/instagram2x.png',
    }

    @staticmethod
    def encode_image(image_path):
        """Convert image to base64 string"""
        full_path = os.path.join(settings.BASE_DIR / "static", image_path)
        try:
            with open(full_path, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode('utf-8')
        except FileNotFoundError:
            print(f"Warning: Image not found at {full_path}")
            return None

    @staticmethod
    def attach_inline_image(email, image_path, image_cid):
        """Helper function to attach an inline image to the email"""
        full_path = os.path.join(settings.BASE_DIR / "static", image_path)

        try:
            with open(full_path, 'rb') as img_file:
                img_data = img_file.read()
                img_mime_type, _ = mimetypes.guess_type(full_path)

                if not img_mime_type or not img_mime_type.startswith('image/'):
                    print(f"Warning: Invalid image type for {full_path}")
                    return False

                img_attachment = MIMEImage(img_data, _subtype=img_mime_type.split('/')[1])

                img_attachment.add_header('Content-ID', f'<{image_cid}>')
                img_attachment.add_header('Content-Disposition', 'inline', filename=os.path.basename(full_path))

                email.attach(img_attachment)
                return True

        except FileNotFoundError:
            print(f"Warning: Could not attach image - {full_path} not found")
            return False
        except Exception as e:
            print(f"Error attaching image {image_path}: {str(e)}")
            return False

    @classmethod
    def attach_default_images(cls, email):
        """Attach all default images to email"""
        success_count = 0
        for cid, path in cls.DEFAULT_IMAGES.items():
            if cls.attach_inline_image(email, path, cid):
                success_count += 1

        print(f"Successfully attached {success_count}/{len(cls.DEFAULT_IMAGES)} images")
        return success_count

    @staticmethod
    def create_email_with_images(subject, text_content, html_content, from_email, to_emails, images=None):
        """Create EmailMultiAlternatives with images attached"""
        email = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=from_email,
            to=to_emails if isinstance(to_emails, list) else [to_emails],
        )

        email.attach_alternative(html_content, "text/html")

        if images:
            for image_path, image_cid in images.items():
                EmailImageHandler.attach_inline_image(email, image_path, image_cid)
        else:
            EmailImageHandler.attach_default_images(email)

        return email
