"""
Vendor provisioning and suspend/unsuspend services.

Views call these functions — they do not contain the business rules themselves.
"""
import logging

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.organizations.models import Organization
from apps.vendors.models import Vendor

logger = logging.getLogger(__name__)

DUPLICATE_NAME = "A vendor with this name already exists."
ALREADY_SUSPENDED = "This vendor is already suspended."
NOT_SUSPENDED = "This vendor is not suspended."
VENDOR_SUSPENDED = "Vendor suspended."
VENDOR_UNSUSPENDED = "Vendor unsuspended."


def get_org_vendor(*, org: Organization, slug: str) -> Vendor:
    """
    Return the Vendor for *slug* in *org*.

    Raises Vendor.DoesNotExist when the slug is unknown or belongs to
    a different organisation.
    """
    return Vendor.objects.get(org=org, slug=slug)


@transaction.atomic
def create_vendor(
    *,
    org: Organization,
    name: str,
    contact_name: str,
    phone: str,
    address: str,
    email: str = "",
    gst: str = "",
    website: str = "",
) -> Vendor:
    """Create a vendor in *org*. Slug is generated from *name*."""
    if Vendor.objects.filter(org=org, name=name).exists():
        raise ValidationError({"name": DUPLICATE_NAME})

    vendor = Vendor.objects.create(
        org=org,
        name=name,
        contact_name=contact_name,
        phone=phone,
        address=address,
        email=email,
        gst=gst,
        website=website,
    )
    logger.info("Created vendor '%s' for org '%s'", name, org.org_suffix)
    return vendor


@transaction.atomic
def update_vendor(*, vendor: Vendor, **fields) -> Vendor:
    """Apply allowed field updates. Slug and org are never rewritten."""
    if "name" in fields and fields["name"] != vendor.name:
        if Vendor.objects.filter(org=vendor.org, name=fields["name"]).exists():
            raise ValidationError({"name": DUPLICATE_NAME})

    allowed = ("name", "contact_name", "phone", "address", "email", "gst", "website")
    changed = []
    for key in allowed:
        if key in fields:
            setattr(vendor, key, fields[key])
            changed.append(key)
    if changed:
        vendor.save(update_fields=[*changed, "updated_at"])
        logger.info("Updated vendor '%s' fields %s", vendor.slug, changed)
    return vendor


def set_vendor_active(*, org: Organization, slug: str, is_active: bool) -> Vendor:
    """Suspend or unsuspend the vendor identified by *slug* in *org*."""
    vendor = get_org_vendor(org=org, slug=slug)
    if is_active and vendor.is_active:
        raise ValidationError({"detail": NOT_SUSPENDED})
    if not is_active and not vendor.is_active:
        raise ValidationError({"detail": ALREADY_SUSPENDED})

    vendor.is_active = is_active
    vendor.save(update_fields=["is_active", "updated_at"])
    logger.info(
        "%s vendor '%s' in org '%s'",
        "Unsuspended" if is_active else "Suspended",
        vendor.slug,
        org.org_suffix,
    )
    return vendor


def suspend_vendor(*, org: Organization, slug: str) -> Vendor:
    """Set is_active=False."""
    return set_vendor_active(org=org, slug=slug, is_active=False)


def unsuspend_vendor(*, org: Organization, slug: str) -> Vendor:
    """Set is_active=True."""
    return set_vendor_active(org=org, slug=slug, is_active=True)
