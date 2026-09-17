"""
Item catalog and warehouse stock.

Quantity on hand is not a free PATCH field — warehouse receiving updates it.
Public API identifier is slug (from name), never UUID.
"""
from django.db import models

from apps.common.models import SlugMixin, UUIDModel


class Item(UUIDModel, SlugMixin):
    """An org-scoped catalog item held in warehouse stock."""

    org = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="items",
    )
    name = models.CharField(max_length=255)
    sku = models.CharField(max_length=100, blank=True)
    unit = models.CharField(max_length=50)
    quantity_on_hand = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        default=0,
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Item"
        verbose_name_plural = "Items"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["org", "name"],
                name="inventory_item_org_name_uniq",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.org.org_suffix})"

    def get_slug_source(self) -> str:
        return self.name
