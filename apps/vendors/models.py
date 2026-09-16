"""
Vendor model.

A Vendor belongs to one Organisation.  Central admins and warehouse managers
of that org can create, update, and suspend vendors.  Vendors are never
deleted — is_active is flipped instead.

Public API identifier is slug (auto-generated from name), never UUID.
"""
from django.db import models

from apps.common.models import SlugMixin, UUIDModel


class Vendor(UUIDModel, SlugMixin):
    """A supplier registered against an organisation."""

    org = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="vendors",
    )
    name = models.CharField(max_length=255)
    contact_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=30)
    address = models.TextField()
    email = models.EmailField(blank=True)
    gst = models.CharField(max_length=50, blank=True)
    website = models.URLField(blank=True)
    is_active = models.BooleanField(
        default=True,
        help_text="Inactive vendors are hidden from purchasing flows.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Vendor"
        verbose_name_plural = "Vendors"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["org", "name"],
                name="vendors_vendor_org_name_uniq",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.org.org_suffix})"

    def get_slug_source(self) -> str:
        return self.name
