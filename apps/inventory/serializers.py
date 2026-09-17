"""Serializers for the item catalog. quantity_on_hand is never writable."""
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.inventory.models import Item
from apps.inventory.services import create_item, update_item


def _raise_django_validation(exc: DjangoValidationError):
    if hasattr(exc, "message_dict"):
        raise serializers.ValidationError(exc.message_dict) from exc
    raise serializers.ValidationError(exc.messages) from exc


class ItemSerializer(serializers.ModelSerializer):
    """Read-only public item JSON (slug, never UUID)."""

    class Meta:
        model = Item
        fields = (
            "slug",
            "name",
            "sku",
            "unit",
            "quantity_on_hand",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class ItemCreateSerializer(serializers.Serializer):
    """Create a catalog item. Stock starts at 0."""

    name = serializers.CharField(max_length=255)
    unit = serializers.CharField(max_length=50)
    sku = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")

    def create(self, validated_data):
        try:
            return create_item(org=self.context["org"], **validated_data)
        except DjangoValidationError as exc:
            _raise_django_validation(exc)


class ItemUpdateSerializer(serializers.Serializer):
    """Partial update. quantity_on_hand and slug are not writable."""

    name = serializers.CharField(max_length=255, required=False)
    unit = serializers.CharField(max_length=50, required=False)
    sku = serializers.CharField(max_length=100, required=False, allow_blank=True)

    def update(self, instance, validated_data):
        try:
            return update_item(item=instance, **validated_data)
        except DjangoValidationError as exc:
            _raise_django_validation(exc)
