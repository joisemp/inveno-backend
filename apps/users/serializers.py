"""
Serializers for the users app.

Auth serializers
----------------
CustomTokenObtainPairSerializer — adds user_type / org_id / org_suffix JWT
                                  claims and checks account + org is_active
                                  on login.
CustomTokenRefreshSerializer    — rejects refresh when the user is inactive.
MeSerializer                   — read + patch view for the authenticated user.
ChangePasswordSerializer        — change password (requires old password).
PasswordResetRequestSerializer  — request a forgot-password email.
PasswordResetConfirmSerializer  — confirm forgot-password with uid + token.
PasswordSetupSerializer         — set password from the welcome-email link.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from rest_framework import serializers
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer
from rest_framework_simplejwt.settings import api_settings as jwt_settings
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()

ACCOUNT_SUSPENDED = (
    "Your account has been suspended. Please contact your administrator."
)


# ---------------------------------------------------------------------------
# JWT — custom claims + org-active gate
# ---------------------------------------------------------------------------

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Extends the default JWT pair serializer with:
    - user_type, org_id, org_suffix claims in the token.
    - Login rejection when the user account or their org is inactive.
    """

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        try:
            profile = user.profile
            token["user_type"] = profile.user_type
            if profile.org:
                token["org_id"] = str(profile.org.id)
                token["org_suffix"] = profile.org.org_suffix
            else:
                token["org_id"] = None
                token["org_suffix"] = None
        except Exception:  # no profile yet
            token["user_type"] = None
            token["org_id"] = None
            token["org_suffix"] = None
        return token

    def validate(self, attrs):
        email = attrs.get(self.username_field)
        password = attrs.get("password")
        if email and password:
            try:
                pending = User.objects.get(
                    **{self.username_field: User.objects.normalize_email(email)}
                )
            except User.DoesNotExist:
                pending = None
            if (
                pending is not None
                and not pending.is_staff
                and not pending.is_active
                and pending.check_password(password)
            ):
                raise serializers.ValidationError(ACCOUNT_SUSPENDED)

        data = super().validate(attrs)
        user = self.user

        # Block login for non-staff users whose org has been suspended.
        if not user.is_staff:
            try:
                if user.profile.org and not user.profile.org.is_active:
                    raise serializers.ValidationError(
                        "Your organisation has been suspended. "
                        "Please contact your administrator."
                    )
            except user.__class__.profile.RelatedObjectDoesNotExist:
                pass

        return data


class CustomTokenRefreshSerializer(TokenRefreshSerializer):
    """Refuse a new token pair when the user account is inactive."""

    def validate(self, attrs):
        try:
            refresh = RefreshToken(attrs["refresh"])
        except Exception:
            return super().validate(attrs)

        user_id = refresh.payload.get(jwt_settings.USER_ID_CLAIM)
        user = User.objects.filter(pk=user_id).first()
        if user is not None and not user.is_active:
            raise InvalidToken("User is inactive")
        return super().validate(attrs)


# ---------------------------------------------------------------------------
# /me — read + patch
# ---------------------------------------------------------------------------

class MeSerializer(serializers.ModelSerializer):
    """
    Read / update view for the authenticated user.

    GET  — returns user info + nested profile + org.
    PATCH — accepts first_name, last_name, phone to update the UserProfile.
    """

    profile = serializers.SerializerMethodField()
    org = serializers.SerializerMethodField()

    # Write-only fields that map to UserProfile (excluded from GET output
    # because they appear inside the nested `profile` object).
    first_name = serializers.CharField(
        max_length=150, required=False, allow_blank=True, write_only=True
    )
    last_name = serializers.CharField(
        max_length=150, required=False, allow_blank=True, write_only=True
    )
    phone = serializers.CharField(
        max_length=30, required=False, allow_blank=True, write_only=True
    )

    class Meta:
        model = User
        fields = (
            "id", "email", "date_joined", "updated_at",
            "profile", "org",
            # write-only profile fields:
            "first_name", "last_name", "phone",
        )
        read_only_fields = ("id", "email", "date_joined", "updated_at", "profile", "org")

    def get_profile(self, obj):
        try:
            p = obj.profile
            return {
                "user_type": p.user_type,
                "first_name": p.first_name,
                "last_name": p.last_name,
                "phone": p.phone,
                "full_name": p.full_name,
            }
        except Exception:
            return None

    def get_org(self, obj):
        try:
            org = obj.profile.org
            if org is None:
                return None
            return {
                "id": str(org.id),
                "name": org.name,
                "org_suffix": org.org_suffix,
                "location": org.location,
                "is_active": org.is_active,
                "registered_on": org.registered_on,
            }
        except Exception:
            return None

    def update(self, instance, validated_data):
        """Apply profile-related write-only fields to UserProfile."""
        profile_fields = {}
        for field in ("first_name", "last_name", "phone"):
            if field in validated_data:
                profile_fields[field] = validated_data.pop(field)

        if profile_fields:
            try:
                profile = instance.profile
                for key, value in profile_fields.items():
                    setattr(profile, key, value)
                profile.save()
            except Exception:
                pass

        return super().update(instance, validated_data)


# ---------------------------------------------------------------------------
# Change password
# ---------------------------------------------------------------------------

class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, validators=[validate_password])
    new_password2 = serializers.CharField(write_only=True, label="Confirm new password")

    def validate(self, attrs):
        if attrs["new_password"] != attrs["new_password2"]:
            raise serializers.ValidationError({"new_password2": "Passwords do not match."})
        return attrs

    def validate_old_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Old password is incorrect.")
        return value


# ---------------------------------------------------------------------------
# Password reset (forgot-password flow)
# ---------------------------------------------------------------------------

class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, validators=[validate_password])
    new_password2 = serializers.CharField(write_only=True, label="Confirm new password")

    def validate(self, attrs):
        if attrs["new_password"] != attrs["new_password2"]:
            raise serializers.ValidationError({"new_password2": "Passwords do not match."})

        try:
            uid = force_str(urlsafe_base64_decode(attrs["uid"]))
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            raise serializers.ValidationError({"uid": "Invalid reset link."})

        if not default_token_generator.check_token(user, attrs["token"]):
            raise serializers.ValidationError({"token": "Reset link is invalid or has expired."})

        attrs["user"] = user
        return attrs


# ---------------------------------------------------------------------------
# Password setup (welcome-email get-started flow)
# ---------------------------------------------------------------------------

class PasswordSetupSerializer(serializers.Serializer):
    """
    Validate the uid + token from the welcome email and accept the new password.

    Uses PasswordSetupTokenGenerator (7-day TTL), not the default reset generator.
    """

    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, validators=[validate_password])
    new_password2 = serializers.CharField(write_only=True, label="Confirm new password")

    def validate(self, attrs):
        if attrs["new_password"] != attrs["new_password2"]:
            raise serializers.ValidationError({"new_password2": "Passwords do not match."})

        try:
            uid = force_str(urlsafe_base64_decode(attrs["uid"]))
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            raise serializers.ValidationError({"uid": "Invalid link."})

        from apps.users.tokens import password_setup_token_generator

        if not password_setup_token_generator.check_token(user, attrs["token"]):
            raise serializers.ValidationError(
                {"token": "Link is invalid or has expired. Request a new welcome email."}
            )

        attrs["user"] = user
        return attrs
