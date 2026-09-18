"""Serializers for warehouses, categories, and the item catalog."""
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.inventory.models import Item, ItemCategory, ItemPhoto, Warehouse
from apps.inventory.services import (
    add_item_photo,
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
    """Nested photo: public slug plus absolute media URL."""

    url = serializers.SerializerMethodField()

    class Meta:
        model = ItemPhoto
        fields = ("slug", "url")
        read_only_fields = fields

    def get_url(self, obj) -> str:
        if not obj.image:
            return ""
        request = self.context.get("request")
        url = obj.image.url
        if request:
            return request.build_absolute_uri(url)
        return url


class ItemPhotoCreateSerializer(serializers.Serializer):
    """Multipart upload. The file is converted to WebP in the service."""

    image = serializers.ImageField()

    def create(self, validated_data):
        try:
            return add_item_photo(
                item=self.context["item"], uploaded_file=validated_data["image"]
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

    warehouse = serializers.SlugField()
    name = serializers.CharField(max_length=255)
    unit = serializers.CharField(max_length=50)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    part_number = serializers.CharField(
        max_length=100, required=False, allow_blank=True, default=""
    )
    alternate_part_number = serializers.CharField(
        max_length=100, required=False, allow_blank=True, default=""
    )
    category = serializers.SlugField(required=False, allow_null=True, allow_blank=True)
    location = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default=""
    )
    remarks = serializers.CharField(required=False, allow_blank=True, default="")

    def create(self, validated_data):
        category = validated_data.pop("category", None)
        if category == "":
            category = None
        try:
            return create_item(
                org=self.context["org"],
                category=category,
                **validated_data,
            )
        except DjangoValidationError as exc:
            _raise_django_validation(exc)


class ItemUpdateSerializer(serializers.Serializer):
    """Partial update. quantity_on_hand and slug are not writable."""

    warehouse = serializers.SlugField(required=False)
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
    last_purchase_date = serializers.DateField(required=False, allow_null=True)
    last_purchase_quantity = serializers.DecimalField(
        max_digits=12, decimal_places=3, required=False, allow_null=True
    )

    def update(self, instance, validated_data):
        if "category" in validated_data and validated_data["category"] == "":
            validated_data["category"] = None
        try:
            return update_item(item=instance, **validated_data)
        except DjangoValidationError as exc:
            _raise_django_validation(exc)
