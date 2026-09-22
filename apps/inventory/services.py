"""
Inventory catalog services.

Views and org registration call these functions. Stock quantity is updated
by warehouse receiving (increment_stock) or adjust_item_stock.
"""
import logging
from decimal import Decimal
from io import BytesIO
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from PIL import Image, UnidentifiedImageError

from apps.common.slugs import assign_unique_slug
from apps.inventory.models import Item, ItemActivity, ItemCategory, ItemPhoto, Warehouse
from apps.organizations.models import Organization

logger = logging.getLogger(__name__)

DEFAULT_WAREHOUSE_NAME = "Warehouse"
MAX_ITEM_PHOTOS = 5

DUPLICATE_WAREHOUSE_NAME = "A warehouse with this name already exists."
DUPLICATE_CATEGORY_NAME = "A category with this name already exists."
DUPLICATE_NAME = "An item with this name already exists."
DUPLICATE_PART_NUMBER = "An item with this part number already exists."
WAREHOUSE_REQUIRED = "A warehouse is required."
WAREHOUSE_NOT_FOUND = "Unknown warehouse."
WAREHOUSE_INACTIVE = "This warehouse is inactive."
CATEGORY_NOT_FOUND = "Unknown category."
PHOTO_LIMIT = "An item can have at most 5 photos."
INVALID_IMAGE = "Upload a valid image."
ALREADY_SUSPENDED = "This item is already suspended."
NOT_SUSPENDED = "This item is not suspended."
ITEM_SUSPENDED = "Item suspended."
ITEM_UNSUSPENDED = "Item unsuspended."
STOCK_REASON_REQUIRED = "A reason is required."
STOCK_ACTION_INVALID = 'Must be "add" or "remove".'
STOCK_QTY_POSITIVE = "Quantity must be greater than 0."
INSUFFICIENT_STOCK = "Insufficient stock."

DEFAULT_ACTIVITY_REMARKS = {
    ItemActivity.Action.CREATED: "Item created",
    ItemActivity.Action.UPDATED: "Item updated",
    ItemActivity.Action.ADDED: "Stock added",
    ItemActivity.Action.REMOVED: "Stock removed",
    ItemActivity.Action.RECEIVED: "Warehouse receipt",
    ItemActivity.Action.SUSPENDED: "Item suspended",
    ItemActivity.Action.UNSUSPENDED: "Item unsuspended",
    ItemActivity.Action.PHOTO_ADDED: "Photo added",
    ItemActivity.Action.PHOTO_DELETED: "Photo deleted",
}


def _qty_str(value) -> str:
    return f"{Decimal(value):.3f}"


def _public_field_value(key, value):
    """Serialize a catalog field for activity payload (slugs, never UUIDs)."""
    if key in ("warehouse", "category") and value is not None:
        return getattr(value, "slug", value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, Decimal):
        return _qty_str(value)
    return value


def record_item_activity(
    *,
    item: Item,
    actor,
    kind: str,
    action: str,
    remarks: str = "",
    previous_quantity=None,
    quantity=None,
    delta=None,
    reference_type: str = "",
    reference_slug: str = "",
    payload: dict | None = None,
) -> ItemActivity:
    """Append one activity row in the same transaction as the domain write."""
    actor_slug = ""
    actor_full_name = ""
    actor_user_type = ""
    if actor is not None:
        actor_slug = actor.slug
        actor_full_name = actor.full_name
        actor_user_type = actor.user_type
    activity = ItemActivity(
        org=item.org,
        item=item,
        actor=actor,
        actor_slug=actor_slug,
        actor_full_name=actor_full_name,
        actor_user_type=actor_user_type,
        kind=kind,
        action=action,
        remarks=remarks or DEFAULT_ACTIVITY_REMARKS.get(action, ""),
        previous_quantity=previous_quantity,
        quantity=quantity,
        delta=delta,
        reference_type=reference_type or "item_activity",
        reference_slug=reference_slug,
        payload=payload or {},
    )
    activity.save()
    if not activity.reference_slug:
        activity.reference_slug = activity.slug
        activity.reference_type = "item_activity"
        activity.save(update_fields=["reference_slug", "reference_type"])
    return activity


def get_org_warehouse(*, org: Organization, slug: str) -> Warehouse:
    """Return the Warehouse for *slug* in *org*."""
    return Warehouse.objects.get(org=org, slug=slug)


def get_org_category(*, org: Organization, slug: str) -> ItemCategory:
    """Return the ItemCategory for *slug* in *org*."""
    return ItemCategory.objects.get(org=org, slug=slug)


def get_org_item(*, org: Organization, slug: str) -> Item:
    """Return the Item for *slug* in *org*."""
    return Item.objects.get(org=org, slug=slug)


def default_receipt_warehouse(*, org: Organization) -> Warehouse | None:
    """Return the only active warehouse, else None when the org has several."""
    qs = Warehouse.objects.filter(org=org, is_active=True)
    if qs.count() == 1:
        return qs.get()
    return None


def _resolve_warehouse(*, org: Organization, warehouse, require_active: bool):
    if warehouse is None or warehouse == "":
        raise ValidationError({"warehouse": WAREHOUSE_REQUIRED})
    if isinstance(warehouse, Warehouse):
        wh = warehouse
    else:
        try:
            wh = Warehouse.objects.get(org=org, slug=warehouse)
        except Warehouse.DoesNotExist as exc:
            raise ValidationError({"warehouse": WAREHOUSE_NOT_FOUND}) from exc
    if wh.org_id != org.id:
        raise ValidationError({"warehouse": WAREHOUSE_NOT_FOUND})
    if require_active and not wh.is_active:
        raise ValidationError({"warehouse": WAREHOUSE_INACTIVE})
    return wh


def _resolve_category(*, org: Organization, category):
    if category is None or category == "":
        return None
    if isinstance(category, ItemCategory):
        cat = category
    else:
        try:
            cat = ItemCategory.objects.get(org=org, slug=category)
        except ItemCategory.DoesNotExist as exc:
            raise ValidationError({"category": CATEGORY_NOT_FOUND}) from exc
    if cat.org_id != org.id:
        raise ValidationError({"category": CATEGORY_NOT_FOUND})
    return cat


@transaction.atomic
def create_warehouse(
    *,
    org: Organization,
    name: str,
    location: str = "",
) -> Warehouse:
    """Create a warehouse in *org*. Slug is generated from *name*."""
    if Warehouse.objects.filter(org=org, name=name).exists():
        raise ValidationError({"name": DUPLICATE_WAREHOUSE_NAME})
    warehouse = Warehouse.objects.create(org=org, name=name, location=location)
    logger.info("Created warehouse '%s' for org '%s'", name, org.org_suffix)
    return warehouse


@transaction.atomic
def update_warehouse(*, warehouse: Warehouse, **fields) -> Warehouse:
    """Update name, location, or is_active. Slug and org are never rewritten."""
    if "name" in fields and fields["name"] != warehouse.name:
        if Warehouse.objects.filter(org=warehouse.org, name=fields["name"]).exists():
            raise ValidationError({"name": DUPLICATE_WAREHOUSE_NAME})
    allowed = ("name", "location", "is_active")
    changed = []
    for key in allowed:
        if key in fields:
            setattr(warehouse, key, fields[key])
            changed.append(key)
    if changed:
        warehouse.save(update_fields=[*changed, "updated_at"])
        logger.info("Updated warehouse '%s' fields %s", warehouse.slug, changed)
    return warehouse


@transaction.atomic
def create_item_category(*, org: Organization, name: str) -> ItemCategory:
    """Create an org-wide item category. Slug is generated from *name*."""
    if ItemCategory.objects.filter(org=org, name=name).exists():
        raise ValidationError({"name": DUPLICATE_CATEGORY_NAME})
    category = ItemCategory.objects.create(org=org, name=name)
    logger.info("Created item category '%s' for org '%s'", name, org.org_suffix)
    return category


@transaction.atomic
def update_item_category(*, category: ItemCategory, **fields) -> ItemCategory:
    """Update name or is_active. Slug and org are never rewritten."""
    if "name" in fields and fields["name"] != category.name:
        if ItemCategory.objects.filter(org=category.org, name=fields["name"]).exists():
            raise ValidationError({"name": DUPLICATE_CATEGORY_NAME})
    allowed = ("name", "is_active")
    changed = []
    for key in allowed:
        if key in fields:
            setattr(category, key, fields[key])
            changed.append(key)
    if changed:
        category.save(update_fields=[*changed, "updated_at"])
        logger.info("Updated item category '%s' fields %s", category.slug, changed)
    return category


def _assert_unique_name(*, warehouse: Warehouse, name: str, exclude_pk=None):
    qs = Item.objects.filter(warehouse=warehouse, name=name)
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    if qs.exists():
        raise ValidationError({"name": DUPLICATE_NAME})


def _assert_unique_part_number(*, warehouse: Warehouse, part_number: str, exclude_pk=None):
    if not part_number:
        return
    qs = Item.objects.filter(warehouse=warehouse, part_number=part_number)
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    if qs.exists():
        raise ValidationError({"part_number": DUPLICATE_PART_NUMBER})


@transaction.atomic
def create_item(
    *,
    org: Organization,
    warehouse,
    name: str,
    unit: str,
    part_number: str = "",
    description: str = "",
    alternate_part_number: str = "",
    category=None,
    location: str = "",
    remarks: str = "",
    actor=None,
) -> Item:
    """Create a catalog item with quantity_on_hand=0 in an active warehouse."""
    wh = _resolve_warehouse(org=org, warehouse=warehouse, require_active=True)
    cat = _resolve_category(org=org, category=category)
    _assert_unique_name(warehouse=wh, name=name)
    _assert_unique_part_number(warehouse=wh, part_number=part_number)
    item = Item.objects.create(
        org=org,
        warehouse=wh,
        category=cat,
        name=name,
        description=description,
        part_number=part_number,
        alternate_part_number=alternate_part_number,
        unit=unit,
        location=location,
        remarks=remarks,
    )
    record_item_activity(
        item=item,
        actor=actor,
        kind=ItemActivity.Kind.ITEM_EDIT,
        action=ItemActivity.Action.CREATED,
        payload={
            "warehouse": wh.slug,
            "name": name,
            "unit": unit,
            "description": description,
            "part_number": part_number,
            "alternate_part_number": alternate_part_number,
            "category": cat.slug if cat else None,
            "location": location,
            "remarks": remarks,
        },
    )
    logger.info("Created item '%s' for org '%s'", name, org.org_suffix)
    return item


@transaction.atomic
def update_item(*, item: Item, actor=None, **fields) -> Item:
    """Update catalog fields. Never quantity_on_hand."""
    warehouse = item.warehouse
    if "warehouse" in fields:
        warehouse = _resolve_warehouse(
            org=item.org,
            warehouse=fields["warehouse"],
            require_active=True,
        )
        fields["warehouse"] = warehouse
    if "category" in fields:
        fields["category"] = _resolve_category(org=item.org, category=fields["category"])
    name = fields.get("name", item.name)
    part_number = fields.get("part_number", item.part_number)
    if name != item.name or warehouse.pk != item.warehouse_id:
        _assert_unique_name(warehouse=warehouse, name=name, exclude_pk=item.pk)
    if part_number != item.part_number or warehouse.pk != item.warehouse_id:
        _assert_unique_part_number(
            warehouse=warehouse, part_number=part_number, exclude_pk=item.pk
        )
    allowed = (
        "name",
        "description",
        "part_number",
        "alternate_part_number",
        "unit",
        "category",
        "warehouse",
        "location",
        "remarks",
        "last_purchase_date",
        "last_purchase_quantity",
    )
    changes = {}
    changed = []
    for key in allowed:
        if key not in fields:
            continue
        old = _public_field_value(key, getattr(item, key))
        new = _public_field_value(key, fields[key])
        setattr(item, key, fields[key])
        changed.append(key)
        if old != new:
            changes[key] = {"from": old, "to": new}
    if changed:
        item.save(update_fields=[*changed, "updated_at"])
        logger.info("Updated item '%s' fields %s", item.slug, changed)
        if changes:
            record_item_activity(
                item=item,
                actor=actor,
                kind=ItemActivity.Kind.ITEM_EDIT,
                action=ItemActivity.Action.UPDATED,
                payload={"changes": changes},
            )
    return item


@transaction.atomic
def set_item_active(*, org: Organization, slug: str, is_active: bool, actor=None) -> Item:
    """Suspend or unsuspend a catalog item."""
    item = get_org_item(org=org, slug=slug)
    if is_active and item.is_active:
        raise ValidationError({"detail": NOT_SUSPENDED})
    if not is_active and not item.is_active:
        raise ValidationError({"detail": ALREADY_SUSPENDED})
    previous = item.is_active
    item.is_active = is_active
    item.save(update_fields=["is_active", "updated_at"])
    action = (
        ItemActivity.Action.UNSUSPENDED if is_active else ItemActivity.Action.SUSPENDED
    )
    actor_payload = {}
    if actor is not None:
        actor_payload = {
            "slug": actor.slug,
            "full_name": actor.full_name,
            "user_type": actor.user_type,
        }
    record_item_activity(
        item=item,
        actor=actor,
        kind=ItemActivity.Kind.ITEM_EDIT,
        action=action,
        payload={
            "is_active": {"from": previous, "to": is_active},
            "actor": actor_payload,
        },
    )
    return item


def suspend_item(*, org: Organization, slug: str, actor=None) -> Item:
    return set_item_active(org=org, slug=slug, is_active=False, actor=actor)


def unsuspend_item(*, org: Organization, slug: str, actor=None) -> Item:
    return set_item_active(org=org, slug=slug, is_active=True, actor=actor)


def convert_upload_to_webp(uploaded_file) -> ContentFile:
    """Decode an image upload, strip EXIF, and return WebP bytes."""
    try:
        image = Image.open(uploaded_file)
        image.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValidationError({"image": INVALID_IMAGE}) from exc
    if image.mode == "P":
        image = image.convert("RGBA" if "transparency" in image.info else "RGB")
    elif image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGBA") if "A" in image.mode else image.convert("RGB")
    cleaned = Image.new(image.mode, image.size)
    cleaned.putdata(list(image.getdata()))
    buffer = BytesIO()
    cleaned.save(buffer, format="WEBP", quality=85)
    buffer.seek(0)
    return ContentFile(buffer.getvalue(), name="photo.webp")


@transaction.atomic
def add_item_photo(*, item: Item, uploaded_file, actor=None) -> ItemPhoto:
    """Store a WebP photo on *item*, rejecting a sixth image."""
    if item.photos.count() >= MAX_ITEM_PHOTOS:
        raise ValidationError({"detail": PHOTO_LIMIT})
    original_name = getattr(uploaded_file, "name", "") or "photo"
    webp = convert_upload_to_webp(uploaded_file)
    photo = ItemPhoto(item=item)
    photo._slug_source = Path(original_name).stem or "photo"
    photo.slug = assign_unique_slug(photo, photo._slug_source)
    photo.image.save(f"{photo.slug}.webp", webp, save=False)
    photo.save()
    record_item_activity(
        item=item,
        actor=actor,
        kind=ItemActivity.Kind.ITEM_EDIT,
        action=ItemActivity.Action.PHOTO_ADDED,
        payload={"photo": photo.slug},
    )
    logger.info("Added photo '%s' to item '%s'", photo.slug, item.slug)
    return photo


@transaction.atomic
def delete_item_photo(*, item: Item, photo_slug: str, actor=None) -> None:
    """Remove a photo row and its stored file."""
    photo = item.photos.get(slug=photo_slug)
    photo.image.delete(save=False)
    photo.delete()
    record_item_activity(
        item=item,
        actor=actor,
        kind=ItemActivity.Kind.ITEM_EDIT,
        action=ItemActivity.Action.PHOTO_DELETED,
        payload={"photo": photo_slug},
    )
    logger.info("Deleted photo '%s' from item '%s'", photo_slug, item.slug)


@transaction.atomic
def increment_stock(*, item: Item, quantity, actor=None, receipt_slug="", line_slug="") -> Item:
    """Add *quantity* to on-hand stock and stamp last-purchase fields."""
    previous = item.quantity_on_hand
    item.quantity_on_hand = item.quantity_on_hand + quantity
    item.last_purchase_date = timezone.localdate()
    item.last_purchase_quantity = quantity
    item.save(
        update_fields=[
            "quantity_on_hand",
            "last_purchase_date",
            "last_purchase_quantity",
            "updated_at",
        ]
    )
    remarks = (
        f"Warehouse receipt {receipt_slug}" if receipt_slug else "Warehouse receipt"
    )
    record_item_activity(
        item=item,
        actor=actor,
        kind=ItemActivity.Kind.INCOMING,
        action=ItemActivity.Action.RECEIVED,
        remarks=remarks,
        previous_quantity=previous,
        quantity=item.quantity_on_hand,
        delta=quantity,
        reference_type="warehouse_receipt" if receipt_slug else "item_activity",
        reference_slug=receipt_slug,
        payload={
            "amount": _qty_str(quantity),
            "previous_quantity": _qty_str(previous),
            "quantity": _qty_str(item.quantity_on_hand),
            "receipt": receipt_slug or None,
            "line": line_slug or None,
        },
    )
    return item


@transaction.atomic
def adjust_item_stock(*, item: Item, actor, action: str, quantity, reason: str) -> Item:
    """Add or remove a positive quantity without stamping last-purchase."""
    if action not in ("add", "remove"):
        raise ValidationError({"action": STOCK_ACTION_INVALID})
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError({"reason": STOCK_REASON_REQUIRED})
    qty = Decimal(quantity)
    if qty <= 0:
        raise ValidationError({"quantity": STOCK_QTY_POSITIVE})
    locked = Item.objects.select_for_update().get(pk=item.pk)
    previous = locked.quantity_on_hand
    if action == "add":
        new_qty = previous + qty
        kind = ItemActivity.Kind.INCOMING
        activity_action = ItemActivity.Action.ADDED
        delta = qty
    else:
        new_qty = previous - qty
        if new_qty < 0:
            raise ValidationError({"quantity": INSUFFICIENT_STOCK})
        kind = ItemActivity.Kind.OUTGOING
        activity_action = ItemActivity.Action.REMOVED
        delta = -qty
    locked.quantity_on_hand = new_qty
    locked.save(update_fields=["quantity_on_hand", "updated_at"])
    record_item_activity(
        item=locked,
        actor=actor,
        kind=kind,
        action=activity_action,
        remarks=reason,
        previous_quantity=previous,
        quantity=new_qty,
        delta=delta,
        payload={
            "action": action,
            "amount": _qty_str(qty),
            "previous_quantity": _qty_str(previous),
            "quantity": _qty_str(new_qty),
            "reason": reason,
        },
    )
    return locked
