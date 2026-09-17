"""Item catalog services. Stock quantity is not updated here."""
import logging

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.inventory.models import Item
from apps.organizations.models import Organization

logger = logging.getLogger(__name__)

DUPLICATE_NAME = "An item with this name already exists."
ALREADY_SUSPENDED = "This item is already suspended."
NOT_SUSPENDED = "This item is not suspended."
ITEM_SUSPENDED = "Item suspended."
ITEM_UNSUSPENDED = "Item unsuspended."


def get_org_item(*, org: Organization, slug: str) -> Item:
    """Return the Item for *slug* in *org*."""
    return Item.objects.get(org=org, slug=slug)


@transaction.atomic
def create_item(
    *,
    org: Organization,
    name: str,
    unit: str,
    sku: str = "",
) -> Item:
    """Create a catalog item with quantity_on_hand=0."""
    if Item.objects.filter(org=org, name=name).exists():
        raise ValidationError({"name": DUPLICATE_NAME})
    item = Item.objects.create(org=org, name=name, unit=unit, sku=sku)
    logger.info("Created item '%s' for org '%s'", name, org.org_suffix)
    return item


@transaction.atomic
def update_item(*, item: Item, **fields) -> Item:
    """Update name/sku/unit. Never quantity_on_hand."""
    if "name" in fields and fields["name"] != item.name:
        if Item.objects.filter(org=item.org, name=fields["name"]).exists():
            raise ValidationError({"name": DUPLICATE_NAME})
    allowed = ("name", "sku", "unit")
    changed = []
    for key in allowed:
        if key in fields:
            setattr(item, key, fields[key])
            changed.append(key)
    if changed:
        item.save(update_fields=[*changed, "updated_at"])
        logger.info("Updated item '%s' fields %s", item.slug, changed)
    return item


def set_item_active(*, org: Organization, slug: str, is_active: bool) -> Item:
    """Suspend or unsuspend a catalog item."""
    item = get_org_item(org=org, slug=slug)
    if is_active and item.is_active:
        raise ValidationError({"detail": NOT_SUSPENDED})
    if not is_active and not item.is_active:
        raise ValidationError({"detail": ALREADY_SUSPENDED})
    item.is_active = is_active
    item.save(update_fields=["is_active", "updated_at"])
    return item


def suspend_item(*, org: Organization, slug: str) -> Item:
    return set_item_active(org=org, slug=slug, is_active=False)


def unsuspend_item(*, org: Organization, slug: str) -> Item:
    return set_item_active(org=org, slug=slug, is_active=True)


@transaction.atomic
def increment_stock(*, item: Item, quantity) -> Item:
    """Add *quantity* to quantity_on_hand. Used only by warehouse receiving."""
    item.quantity_on_hand = item.quantity_on_hand + quantity
    item.save(update_fields=["quantity_on_hand", "updated_at"])
    return item
