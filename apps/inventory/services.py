"""
Inventory catalog services.

Views and org registration call these functions. Stock quantity is updated
only by warehouse receiving (increment_stock).
"""
import logging
from io import BytesIO
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from PIL import Image, UnidentifiedImageError

from apps.common.slugs import assign_unique_slug
from apps.inventory.models import Item, ItemCategory, ItemPhoto, Warehouse
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
    logger.info("Created item '%s' for org '%s'", name, org.org_suffix)
    return item


@transaction.atomic
def update_item(*, item: Item, **fields) -> Item:
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
def add_item_photo(*, item: Item, uploaded_file) -> ItemPhoto:
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
    logger.info("Added photo '%s' to item '%s'", photo.slug, item.slug)
    return photo


@transaction.atomic
def delete_item_photo(*, item: Item, photo_slug: str) -> None:
    """Remove a photo row and its stored file."""
    photo = item.photos.get(slug=photo_slug)
    photo.image.delete(save=False)
    photo.delete()
    logger.info("Deleted photo '%s' from item '%s'", photo_slug, item.slug)


@transaction.atomic
def increment_stock(*, item: Item, quantity) -> Item:
    """Add *quantity* to on-hand stock and stamp last-purchase fields."""
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
    return item
