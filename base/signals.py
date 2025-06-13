from django.contrib.auth import get_user_model
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from base.models import Profile

User = get_user_model()
from django.db import transaction
import logging

logger = logging.getLogger(__name__)


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        def on_commit():
            try:
                Profile.objects.get_or_create(user=instance)
            except Exception as e:
                logger.error(f"Error creating profile for user {instance.id}: {str(e)}")

        transaction.on_commit(on_commit)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """Save user profile when user is saved."""
    try:
        if hasattr(instance, 'profile'):
            instance.profile.save()
    except Profile.DoesNotExist:
        Profile.objects.create(user=instance)
    except Exception as e:
        logger.error(f"Error saving profile for user {instance.id}: {str(e)}")


@receiver(post_delete, sender=User)
def delete_user_profile(sender, instance, **kwargs):
    """Delete user profile when user is deleted."""
    try:
        instance.profile.delete()
    except Profile.DoesNotExist:
        pass
