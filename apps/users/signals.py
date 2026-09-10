"""
User post-save signal.

Auto-creates a super_admin UserProfile when a staff / superuser is first
saved (e.g. after `createsuperuser`).

Non-staff user profiles are always created explicitly by the organisation
registration service, so the signal does nothing for them — this avoids
creating a profile without an org (which would violate the org link rule).
"""
import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.users.models import User, UserProfile

logger = logging.getLogger(__name__)


@receiver(post_save, sender=User)
def create_staff_profile(sender, instance: User, created: bool, **kwargs):
    """
    Create a SUPER_ADMIN profile for newly created staff / superusers.

    Uses get_or_create so re-saving a staff user is idempotent and never
    overwrites an existing profile.
    """
    if created and instance.is_staff:
        profile, made = UserProfile.objects.get_or_create(
            user=instance,
            defaults={"user_type": UserProfile.UserType.SUPER_ADMIN},
        )
        if made:
            logger.debug("Auto-created super_admin profile for %s", instance.email)
