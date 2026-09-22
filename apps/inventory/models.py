"""
Item catalog and warehouse stock.

Quantity on hand is not a free PATCH field — warehouse receiving updates it.
Public API identifiers are slugs (from name), never UUID.
"""
from django.db import models
from django.db.models import Q

from apps.common.models import SlugMixin, UUIDModel


class Warehouse(UUIDModel, SlugMixin):
    """An org storage location. Spaces stay demand-side; stock lands here first."""

    org = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="warehouses",
    )
    name = models.CharField(max_length=255)
    location = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Warehouse"
        verbose_name_plural = "Warehouses"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["org", "name"],
                name="inventory_warehouse_org_name_uniq",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.org.org_suffix})"

    def get_slug_source(self) -> str:
        return self.name


class ItemCategory(UUIDModel, SlugMixin):
    """Reusable org-wide category that catalog items can share."""

    org = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="item_categories",
    )
    name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Item category"
        verbose_name_plural = "Item categories"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["org", "name"],
                name="inventory_itemcategory_org_name_uniq",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.org.org_suffix})"

    def get_slug_source(self) -> str:
        return self.name


class Item(UUIDModel, SlugMixin):
    """A catalog item held in one warehouse. Stock changes only via receiving."""

    org = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="items",
    )
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name="items",
    )
    category = models.ForeignKey(
        ItemCategory,
        on_delete=models.SET_NULL,
        related_name="items",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    part_number = models.CharField(max_length=100, blank=True)
    alternate_part_number = models.CharField(max_length=100, blank=True)
    unit = models.CharField(max_length=50)
    location = models.CharField(max_length=255, blank=True)
    remarks = models.TextField(blank=True)
    quantity_on_hand = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        default=0,
    )
    last_purchase_date = models.DateField(null=True, blank=True)
    last_purchase_quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        null=True,
        blank=True,
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
                fields=["warehouse", "name"],
                name="inventory_item_warehouse_name_uniq",
            ),
            models.UniqueConstraint(
                fields=["warehouse", "part_number"],
                condition=~Q(part_number=""),
                name="inventory_item_warehouse_part_uniq",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.org.org_suffix})"

    def get_slug_source(self) -> str:
        return self.name


class ItemPhoto(UUIDModel, SlugMixin):
    """One catalog photo. Files on disk are always WebP; max five per item."""

    item = models.ForeignKey(
        Item,
        on_delete=models.CASCADE,
        related_name="photos",
    )
    image = models.ImageField(upload_to="items/%Y/%m/")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Item photo"
        verbose_name_plural = "Item photos"
        ordering = ["created_at"]

    def __str__(self):
        return self.slug

    def get_slug_source(self) -> str:
        return getattr(self, "_slug_source", "") or "photo"
