"""
Organization model.

An Organisation is registered by a super admin.  It may have one or more
org users (central admins and warehouse managers), represented by
UserProfile rows with org=<this organization>.

Fields
------
name         : display name — not unique (two orgs can share a name).
org_suffix   : globally unique, lowercase handle (e.g. "acme_west").
               Think of it as the org's "username".
slug         : auto-generated from name; stable once set.
location     : free-text location string.
is_active    : super admin can suspend an org without deleting it.
registered_on: timestamp set at creation.
"""
from django.core.validators import RegexValidator
from django.db import models

from apps.common.models import SlugMixin, UUIDModel

_org_suffix_validator = RegexValidator(
    regex=r"^[a-z0-9_]+$",
    message=(
        "org_suffix may only contain lowercase letters, digits, and underscores."
    ),
)


class Organization(UUIDModel, SlugMixin):
    """A customer organisation registered on the platform."""

    name = models.CharField(max_length=255)
    org_suffix = models.CharField(
        max_length=100,
        unique=True,
        validators=[_org_suffix_validator],
        help_text=(
            "Unique handle for this organisation "
            "(lowercase letters, digits, underscores)."
        ),
    )
    location = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(
        default=True,
        help_text="Inactive organisations cannot log in.",
    )
    registered_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Organization"
        verbose_name_plural = "Organizations"
        ordering = ["-registered_on"]

    def __str__(self):
        return f"{self.name} ({self.org_suffix})"

    def get_slug_source(self) -> str:
        return self.name or self.org_suffix

    def save(self, *args, **kwargs):
        # Normalise org_suffix to lowercase before saving
        if self.org_suffix:
            self.org_suffix = self.org_suffix.lower()
        super().save(*args, **kwargs)
