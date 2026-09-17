"""
User authentication model and UserProfile for identity and org membership.

User        — email-based login model.  No personal name fields; those live on
              UserProfile.  No slug — User is explicitly exempt from the slug
              convention.

UserProfile — display identity (name, phone), user role, and org FK.
              One-to-one with User.

Org link rule (enforced in UserProfile.clean):
  - staff / superuser  → org must be None  (user_type = super_admin)
  - non-staff          → org is required (org-assignable user_type)
"""
import uuid

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import SlugMixin, UUIDModel


# ---------------------------------------------------------------------------
# User manager
# ---------------------------------------------------------------------------

class UserManager(BaseUserManager):
    """Custom manager that uses email instead of username."""

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("An email address is required.")
        email = self.normalize_email(email)
        extra_fields.setdefault("is_active", True)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if not extra_fields.get("is_staff"):
            raise ValueError("Superuser must have is_staff=True.")
        if not extra_fields.get("is_superuser"):
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(email, password, **extra_fields)


# ---------------------------------------------------------------------------
# User (login + account security — no personal name fields, no slug)
# ---------------------------------------------------------------------------

class User(AbstractBaseUser, PermissionsMixin):
    """
    Login and account security model.

    Uses email as the unique identifier (USERNAME_FIELD).
    Personal info (first name, last name, phone) and org membership are on
    the related UserProfile.  This model is exempt from the slug convention.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, db_index=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    date_joined = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"
        ordering = ["-date_joined"]

    def __str__(self):
        return self.email

    @property
    def full_name(self) -> str:
        """Delegate to UserProfile; fall back to email when no profile exists."""
        try:
            return self.profile.full_name
        except UserProfile.DoesNotExist:
            return self.email


# ---------------------------------------------------------------------------
# UserProfile (identity, classification, org membership)
# ---------------------------------------------------------------------------

class UserProfile(UUIDModel, SlugMixin):
    """
    Identity and org membership record for a User.

    Every User has at most one UserProfile (one-to-one).

    Org link rule:
      - Staff / superusers   → user_type = SUPER_ADMIN,  org = None
      - Non-staff users      → org is required; user_type is an org-assignable
                               role (central_admin, operation_incharge,
                               warehouse_manager, space_incharge)
    """

    class UserType(models.TextChoices):
        SUPER_ADMIN = "super_admin", _("Super Admin")
        CENTRAL_ADMIN = "central_admin", _("Central Admin")
        OPERATION_INCHARGE = "operation_incharge", _("Operation Incharge")
        WAREHOUSE_MANAGER = "warehouse_manager", _("Warehouse Manager")
        SPACE_INCHARGE = "space_incharge", _("Space Incharge")

    # Roles a central admin may assign when adding an org user.
    # super_admin is platform-only and is never in this set.
    ORG_ASSIGNABLE_TYPES = frozenset(
        {
            UserType.CENTRAL_ADMIN,
            UserType.OPERATION_INCHARGE,
            UserType.WAREHOUSE_MANAGER,
            UserType.SPACE_INCHARGE,
        }
    )
    VENDOR_ACCESS_TYPES = frozenset(
        {
            UserType.CENTRAL_ADMIN,
            UserType.OPERATION_INCHARGE,
            UserType.WAREHOUSE_MANAGER,
        }
    )
    PURCHASE_OPERATOR_TYPES = frozenset(
        {
            UserType.CENTRAL_ADMIN,
            UserType.OPERATION_INCHARGE,
        }
    )
    ITEM_READ_TYPES = frozenset(
        {
            UserType.CENTRAL_ADMIN,
            UserType.OPERATION_INCHARGE,
            UserType.WAREHOUSE_MANAGER,
        }
    )
    ITEM_WRITE_TYPES = frozenset(
        {
            UserType.CENTRAL_ADMIN,
            UserType.WAREHOUSE_MANAGER,
        }
    )
    SPACE_VIEW_TYPES = frozenset(
        {
            UserType.CENTRAL_ADMIN,
            UserType.OPERATION_INCHARGE,
            UserType.SPACE_INCHARGE,
        }
    )

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    user_type = models.CharField(
        max_length=20,
        choices=UserType.choices,
        default=UserType.CENTRAL_ADMIN,
    )
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    phone = models.CharField(max_length=30, blank=True)

    # Nullable at DB level; application-level validation enforces the rule.
    org = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.SET_NULL,
        related_name="profiles",
        null=True,
        blank=True,
    )
    space = models.ForeignKey(
        "organizations.Space",
        on_delete=models.SET_NULL,
        related_name="incharges",
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"

    def __str__(self):
        return f"{self.full_name} ({self.user.email})"

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip() or self.user.email

    def get_slug_source(self) -> str:
        return self.full_name or self.user.email

    def clean(self):
        """Enforce the org link rule."""
        if not self.user_id:
            return  # unsaved user — skip validation
        if self.user.is_staff and self.org is not None:
            raise ValidationError(
                {"org": "Staff / superusers must not be linked to an organisation."}
            )
        if not self.user.is_staff and self.org is None:
            raise ValidationError(
                {"org": "Non-staff users must be linked to an organisation."}
            )
        if self.space_id:
            if self.user_type != self.UserType.SPACE_INCHARGE:
                raise ValidationError(
                    {"space": "Only a space incharge may be assigned to a space."}
                )
            if self.space.org_id != self.org_id:
                raise ValidationError(
                    {"space": "Space must belong to the same organisation."}
                )
