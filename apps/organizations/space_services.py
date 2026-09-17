"""
Space create/update/suspend and space-incharge assignment.

Views call these functions — they do not contain the business rules themselves.
"""
import logging

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.organizations.models import Organization, Space
from apps.organizations.services import get_org_member_profile
from apps.users.models import UserProfile

logger = logging.getLogger(__name__)

DUPLICATE_NAME = "A space with this name already exists."
ALREADY_SUSPENDED = "This space is already suspended."
NOT_SUSPENDED = "This space is not suspended."
SPACE_SUSPENDED = "Space suspended."
SPACE_UNSUSPENDED = "Space unsuspended."
NOT_SPACE_INCHARGE = "Only a space incharge can be assigned to a space."
ALREADY_ASSIGNED = "This member is already assigned to this space."
NOT_ASSIGNED = "This member is not assigned to this space."
INCHARGE_ASSIGNED = "Space incharge assigned."
INCHARGE_UNASSIGNED = "Space incharge unassigned."


def get_org_space(*, org: Organization, slug: str) -> Space:
    """Return the Space for *slug* in *org*."""
    return Space.objects.get(org=org, slug=slug)


@transaction.atomic
def create_space(*, org: Organization, name: str, location: str = "") -> Space:
    """Create a space in *org*. Slug is generated from *name*."""
    if Space.objects.filter(org=org, name=name).exists():
        raise ValidationError({"name": DUPLICATE_NAME})
    space = Space.objects.create(org=org, name=name, location=location)
    logger.info("Created space '%s' for org '%s'", name, org.org_suffix)
    return space


@transaction.atomic
def update_space(*, space: Space, **fields) -> Space:
    """Apply allowed field updates. Slug and org are never rewritten."""
    if "name" in fields and fields["name"] != space.name:
        if Space.objects.filter(org=space.org, name=fields["name"]).exists():
            raise ValidationError({"name": DUPLICATE_NAME})
    allowed = ("name", "location")
    changed = []
    for key in allowed:
        if key in fields:
            setattr(space, key, fields[key])
            changed.append(key)
    if changed:
        space.save(update_fields=[*changed, "updated_at"])
        logger.info("Updated space '%s' fields %s", space.slug, changed)
    return space


def set_space_active(*, org: Organization, slug: str, is_active: bool) -> Space:
    """Suspend or unsuspend the space identified by *slug* in *org*."""
    space = get_org_space(org=org, slug=slug)
    if is_active and space.is_active:
        raise ValidationError({"detail": NOT_SUSPENDED})
    if not is_active and not space.is_active:
        raise ValidationError({"detail": ALREADY_SUSPENDED})
    space.is_active = is_active
    space.save(update_fields=["is_active", "updated_at"])
    logger.info(
        "%s space '%s' in org '%s'",
        "Unsuspended" if is_active else "Suspended",
        space.slug,
        org.org_suffix,
    )
    return space


def suspend_space(*, org: Organization, slug: str) -> Space:
    """Set is_active=False."""
    return set_space_active(org=org, slug=slug, is_active=False)


def unsuspend_space(*, org: Organization, slug: str) -> Space:
    """Set is_active=True."""
    return set_space_active(org=org, slug=slug, is_active=True)


@transaction.atomic
def assign_space_incharge(*, org: Organization, space_slug: str, member_slug: str):
    """Link a space_incharge member to *space_slug* (reassigns if needed)."""
    space = get_org_space(org=org, slug=space_slug)
    profile = get_org_member_profile(org=org, slug=member_slug)
    if profile.user_type != UserProfile.UserType.SPACE_INCHARGE:
        raise ValidationError({"member": NOT_SPACE_INCHARGE})
    if profile.space_id == space.id:
        raise ValidationError({"detail": ALREADY_ASSIGNED})
    profile.space = space
    profile.full_clean()
    profile.save(update_fields=["space"])
    logger.info(
        "Assigned '%s' to space '%s' in org '%s'",
        member_slug,
        space.slug,
        org.org_suffix,
    )
    return profile


@transaction.atomic
def unassign_space_incharge(*, org: Organization, space_slug: str, member_slug: str):
    """Clear UserProfile.space when the member is assigned to this space."""
    space = get_org_space(org=org, slug=space_slug)
    profile = get_org_member_profile(org=org, slug=member_slug)
    if profile.space_id != space.id:
        raise ValidationError({"detail": NOT_ASSIGNED})
    profile.space = None
    profile.save(update_fields=["space"])
    logger.info(
        "Unassigned '%s' from space '%s' in org '%s'",
        member_slug,
        space.slug,
        org.org_suffix,
    )
    return profile
