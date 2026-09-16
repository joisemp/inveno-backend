"""
Serializers for organisation member management.

OrgMemberSerializer       — public member JSON (slug, never UUID).
OrgMemberCreateSerializer — add a user to the caller's organisation.
"""
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.organizations.services import create_org_user
from apps.users.models import UserProfile

User = get_user_model()

_ASSIGNABLE_CHOICES = [
    (UserProfile.UserType.CENTRAL_ADMIN, "Central Admin"),
    (UserProfile.UserType.WAREHOUSE_MANAGER, "Warehouse Manager"),
]


class OrgMemberSerializer(serializers.ModelSerializer):
    """Read-only public representation of an organisation member."""

    email = serializers.EmailField(source="user.email", read_only=True)
    is_active = serializers.BooleanField(source="user.is_active", read_only=True)
    has_usable_password = serializers.SerializerMethodField()
    date_joined = serializers.DateTimeField(source="user.date_joined", read_only=True)
    full_name = serializers.CharField(read_only=True)

    class Meta:
        model = UserProfile
        fields = (
            "slug",
            "email",
            "user_type",
            "first_name",
            "last_name",
            "phone",
            "full_name",
            "is_active",
            "has_usable_password",
            "date_joined",
        )
        read_only_fields = fields

    def get_has_usable_password(self, obj) -> bool:
        return obj.user.has_usable_password()


class OrgMemberCreateSerializer(serializers.Serializer):
    """
    Create a User + UserProfile in the organisation from the view context.

    Slug is generated on save and is not accepted in the request body.
    """

    email = serializers.EmailField()
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    phone = serializers.CharField(
        max_length=30, required=False, allow_blank=True, default=""
    )
    user_type = serializers.ChoiceField(choices=_ASSIGNABLE_CHOICES)

    def validate_email(self, value: str) -> str:
        email = User.objects.normalize_email(value)
        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError(
                "A user with this email already exists."
            )
        return email

    def create(self, validated_data):
        """Provision the user in context['org'] and return their UserProfile."""
        try:
            user = create_org_user(org=self.context["org"], **validated_data)
        except DjangoValidationError as exc:
            if hasattr(exc, "message_dict"):
                raise serializers.ValidationError(exc.message_dict) from exc
            raise serializers.ValidationError(exc.messages) from exc
        return user.profile
