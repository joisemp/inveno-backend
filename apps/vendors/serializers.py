"""
Serializers for vendor management.

VendorSerializer        — public vendor JSON (slug, never UUID).
VendorCreateSerializer  — create; slug is generated.
VendorUpdateSerializer  — partial update; slug and org are not accepted.
"""
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.vendors.models import Vendor
from apps.vendors.services import create_vendor, update_vendor


class VendorSerializer(serializers.ModelSerializer):
    """Read-only public representation of a vendor."""

    class Meta:
        model = Vendor
        fields = (
            "slug",
            "name",
            "contact_name",
            "phone",
            "email",
            "address",
            "gst",
            "website",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


def _raise_django_validation(exc: DjangoValidationError):
    if hasattr(exc, "message_dict"):
        raise serializers.ValidationError(exc.message_dict) from exc
    raise serializers.ValidationError(exc.messages) from exc


class VendorCreateSerializer(serializers.Serializer):
    """Create a vendor in context['org']. Slug is generated, never accepted."""

    name = serializers.CharField(max_length=255)
    contact_name = serializers.CharField(max_length=150)
    phone = serializers.CharField(max_length=30)
    address = serializers.CharField()
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    gst = serializers.CharField(
        max_length=50, required=False, allow_blank=True, default=""
    )
    website = serializers.URLField(required=False, allow_blank=True, default="")

    def create(self, validated_data):
        try:
            return create_vendor(org=self.context["org"], **validated_data)
        except DjangoValidationError as exc:
            _raise_django_validation(exc)


class VendorUpdateSerializer(serializers.Serializer):
    """Partial update. Slug, org, and is_active are not writable here."""

    name = serializers.CharField(max_length=255, required=False)
    contact_name = serializers.CharField(max_length=150, required=False)
    phone = serializers.CharField(max_length=30, required=False)
    address = serializers.CharField(required=False)
    email = serializers.EmailField(required=False, allow_blank=True)
    gst = serializers.CharField(max_length=50, required=False, allow_blank=True)
    website = serializers.URLField(required=False, allow_blank=True)

    def update(self, instance, validated_data):
        try:
            return update_vendor(vendor=instance, **validated_data)
        except DjangoValidationError as exc:
            _raise_django_validation(exc)
