"""Serializers for warehouses, categories, and the item catalog."""
from django.core.exceptions import ValidationError as DjangoValidationError
from django.urls import reverse
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.inventory.models import Item, ItemActivity, ItemCategory, ItemPhoto, Warehouse
from apps.inventory.services import (
    add_item_photo,
    adjust_item_stock,
    create_item,
    create_item_category,
    create_warehouse,
    update_item,
    update_item_category,
    update_warehouse,
)


def _raise_django_validation(exc: DjangoValidationError):
    if hasattr(exc, "message_dict"):
        raise serializers.ValidationError(exc.message_dict) from exc
    raise serializers.ValidationError(exc.messages) from exc


class WarehouseSerializer(serializers.ModelSerializer):
    """Read-only public warehouse JSON (slug, never UUID)."""

    class Meta:
        model = Warehouse
        fields = (
            "slug",
            "name",
            "location",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class WarehouseCreateSerializer(serializers.Serializer):
    """Create a warehouse in context['org']. Slug is generated."""

    name = serializers.CharField(max_length=255)
    location = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default=""
    )

    def create(self, validated_data):
        try:
            return create_warehouse(org=self.context["org"], **validated_data)
        except DjangoValidationError as exc:
            _raise_django_validation(exc)


class WarehouseUpdateSerializer(serializers.Serializer):
    """Partial update including is_active. Slug and org are not accepted."""

    name = serializers.CharField(max_length=255, required=False)
    location = serializers.CharField(max_length=255, required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False)

    def update(self, instance, validated_data):
        try:
            return update_warehouse(warehouse=instance, **validated_data)
        except DjangoValidationError as exc:
            _raise_django_validation(exc)


class ItemCategorySerializer(serializers.ModelSerializer):
    """Read-only public category JSON (slug, never UUID)."""

    class Meta:
        model = ItemCategory
        fields = ("slug", "name", "is_active", "created_at", "updated_at")
        read_only_fields = fields


class ItemCategoryCreateSerializer(serializers.Serializer):
    """Create an org-wide category. Slug is generated."""

    name = serializers.CharField(max_length=255)

    def create(self, validated_data):
        try:
            return create_item_category(org=self.context["org"], **validated_data)
        except DjangoValidationError as exc:
            _raise_django_validation(exc)


class ItemCategoryUpdateSerializer(serializers.Serializer):
    """Partial update. Slug and org are not accepted."""

    name = serializers.CharField(max_length=255, required=False)
    is_active = serializers.BooleanField(required=False)

    def update(self, instance, validated_data):
        try:
            return update_item_category(category=instance, **validated_data)
        except DjangoValidationError as exc:
            _raise_django_validation(exc)


class ItemPhotoSerializer(serializers.ModelSerializer):
    """Nested photo: slug plus authenticated file URL (not a Spaces CDN path)."""

    url = serializers.SerializerMethodField()

    class Meta:
        model = ItemPhoto
        fields = ("slug", "url")
        read_only_fields = fields

    def get_url(self, obj) -> str:
        if not obj.image:
            return ""
        path = reverse(
            "inventory:item-photo-file",
            kwargs={"slug": obj.item.slug, "photo_slug": obj.slug},
        )
        request = self.context.get("request")
        if request:
            return request.build_absolute_uri(path)
        return path


class ItemPhotoCreateSerializer(serializers.Serializer):
    """Multipart upload. The file is converted to WebP in the service."""

    image = serializers.ImageField(
        help_text="JPEG, PNG, GIF, or WebP. Stored as WebP. Multipart field name: image."
    )

    def create(self, validated_data):
        try:
            return add_item_photo(
                item=self.context["item"],
                uploaded_file=validated_data["image"],
                actor=self.context.get("actor"),
            )
        except DjangoValidationError as exc:
            _raise_django_validation(exc)


class ItemSerializer(serializers.ModelSerializer):
    """Read-only public item JSON (slug, never UUID)."""

    warehouse = serializers.SlugRelatedField(read_only=True, slug_field="slug")
    category = serializers.SlugRelatedField(read_only=True, slug_field="slug")
    photos = ItemPhotoSerializer(many=True, read_only=True)
    balance_in_stock = serializers.DecimalField(
        max_digits=12, decimal_places=3, read_only=True, source="quantity_on_hand"
    )

    class Meta:
        model = Item
        fields = (
            "slug",
            "warehouse",
            "name",
            "description",
            "part_number",
            "alternate_part_number",
            "unit",
            "category",
            "location",
            "remarks",
            "quantity_on_hand",
            "balance_in_stock",
            "last_purchase_date",
            "last_purchase_quantity",
            "photos",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class ItemCreateSerializer(serializers.Serializer):
    """Create a catalog item. Stock starts at 0. Requires a warehouse slug."""

    warehouse = serializers.SlugField(help_text="Active warehouse slug.")
    name = serializers.CharField(max_length=255, help_text="Catalog name. Unique per warehouse.")
    unit = serializers.CharField(max_length=50, help_text="Unit of measure, e.g. ream.")
    description = serializers.CharField(
        required=False, allow_blank=True, default="", help_text="Optional long description."
    )
    part_number = serializers.CharField(
        max_length=100,
        required=False,
        allow_blank=True,
        default="",
        help_text="Optional. Unique per warehouse when set.",
    )
    alternate_part_number = serializers.CharField(
        max_length=100,
        required=False,
        allow_blank=True,
        default="",
        help_text="Optional alternate part number.",
    )
    category = serializers.SlugField(
        required=False,
        allow_null=True,
        allow_blank=True,
        help_text="Optional item-category slug.",
    )
    location = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
        default="",
        help_text="Optional bin / aisle location.",
    )
    remarks = serializers.CharField(
        required=False, allow_blank=True, default="", help_text="Optional notes."
    )

    def create(self, validated_data):
        category = validated_data.pop("category", None)
        if category == "":
            category = None
        try:
            return create_item(
                org=self.context["org"],
                category=category,
                actor=self.context.get("actor"),
                **validated_data,
            )
        except DjangoValidationError as exc:
            _raise_django_validation(exc)


class ItemUpdateSerializer(serializers.Serializer):
    """Partial update. quantity_on_hand and slug are not writable."""

    warehouse = serializers.SlugField(required=False, help_text="Move to another active warehouse.")
    name = serializers.CharField(max_length=255, required=False)
    unit = serializers.CharField(max_length=50, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    part_number = serializers.CharField(
        max_length=100, required=False, allow_blank=True
    )
    alternate_part_number = serializers.CharField(
        max_length=100, required=False, allow_blank=True
    )
    category = serializers.SlugField(required=False, allow_null=True, allow_blank=True)
    location = serializers.CharField(max_length=255, required=False, allow_blank=True)
    remarks = serializers.CharField(required=False, allow_blank=True)
    last_purchase_date = serializers.DateField(
        required=False, allow_null=True, help_text="Usually set by completing a receipt."
    )
    last_purchase_quantity = serializers.DecimalField(
        max_digits=12,
        decimal_places=3,
        required=False,
        allow_null=True,
        help_text="Usually set by completing a receipt.",
    )

    def update(self, instance, validated_data):
        if "category" in validated_data and validated_data["category"] == "":
            validated_data["category"] = None
        try:
            return update_item(
                item=instance, actor=self.context.get("actor"), **validated_data
            )
        except DjangoValidationError as exc:
            _raise_django_validation(exc)


class ItemStockAdjustSerializer(serializers.Serializer):
    """Add or remove a positive quantity. Reason is required."""

    action = serializers.ChoiceField(
        choices=("add", "remove"),
        help_text='Use "add" to increase on-hand stock or "remove" to decrease it.',
    )
    quantity = serializers.DecimalField(
        max_digits=12,
        decimal_places=3,
        help_text="Positive amount to add or remove. Not the new total.",
    )
    reason = serializers.CharField(
        max_length=255, help_text="Required. Stored on the activity row as remarks."
    )

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("Quantity must be greater than 0.")
        return value

    def save(self, **kwargs):
        try:
            return adjust_item_stock(
                item=self.context["item"],
                actor=self.context["actor"],
                action=self.validated_data["action"],
                quantity=self.validated_data["quantity"],
                reason=self.validated_data["reason"],
            )
        except DjangoValidationError as exc:
            _raise_django_validation(exc)


class ItemActivityRecordedBySerializer(serializers.Serializer):
    """Member snapshot on an activity row (profile slug, never User UUID)."""

    slug = serializers.SlugField()
    full_name = serializers.CharField()
    user_type = serializers.CharField()


class ItemActivityReferenceSerializer(serializers.Serializer):
    """Source document or this activity, identified by slug."""

    type = serializers.CharField()
    slug = serializers.SlugField()


class ItemActivitySerializer(serializers.ModelSerializer):
    """List row for the item history table. No UUID id."""

    recorded_on = serializers.DateTimeField(source="created_at", read_only=True)
    recorded_by = serializers.SerializerMethodField()
    reference = serializers.SerializerMethodField()

    class Meta:
        model = ItemActivity
        fields = (
            "slug",
            "kind",
            "action",
            "previous_quantity",
            "quantity",
            "delta",
            "recorded_on",
            "recorded_by",
            "remarks",
            "reference",
        )
        read_only_fields = fields

    @extend_schema_field(ItemActivityRecordedBySerializer)
    def get_recorded_by(self, obj) -> dict:
        return {
            "slug": obj.actor_slug,
            "full_name": obj.actor_full_name,
            "user_type": obj.actor_user_type,
        }

    @extend_schema_field(ItemActivityReferenceSerializer)
    def get_reference(self, obj) -> dict:
        return {"type": obj.reference_type, "slug": obj.reference_slug}


class ItemActivityDetailSerializer(ItemActivitySerializer):
    """History row plus payload for the details panel."""

    class Meta(ItemActivitySerializer.Meta):
        fields = (*ItemActivitySerializer.Meta.fields, "payload")
        read_only_fields = fields
