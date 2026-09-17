"""
Serializers for organisation spaces and incharge assignment.

SpaceSerializer        — public space JSON (slug, never UUID).
SpaceCreateSerializer  — create; slug is generated.
SpaceUpdateSerializer  — partial update; slug and org are not accepted.
SpaceAssignSerializer  — assign a member slug to a space.
"""
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.organizations.models import Space
from apps.organizations.space_services import create_space, update_space


def _raise_django_validation(exc: DjangoValidationError):
    if hasattr(exc, "message_dict"):
        raise serializers.ValidationError(exc.message_dict) from exc
    raise serializers.ValidationError(exc.messages) from exc


class SpaceSerializer(serializers.ModelSerializer):
    """Read-only public representation of a space."""

    class Meta:
        model = Space
        fields = (
            "slug",
            "name",
            "location",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class SpaceCreateSerializer(serializers.Serializer):
    """Create a space in context['org']. Slug is generated, never accepted."""

    name = serializers.CharField(max_length=255)
    location = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default=""
    )

    def create(self, validated_data):
        try:
            return create_space(org=self.context["org"], **validated_data)
        except DjangoValidationError as exc:
            _raise_django_validation(exc)


class SpaceUpdateSerializer(serializers.Serializer):
    """Partial update. Slug, org, and is_active are not writable here."""

    name = serializers.CharField(max_length=255, required=False)
    location = serializers.CharField(max_length=255, required=False, allow_blank=True)

    def update(self, instance, validated_data):
        try:
            return update_space(space=instance, **validated_data)
        except DjangoValidationError as exc:
            _raise_django_validation(exc)


class SpaceAssignSerializer(serializers.Serializer):
    """Assign a space_incharge member (by profile slug) to a space."""

    member = serializers.SlugField()
