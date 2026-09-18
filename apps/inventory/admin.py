"""Django admin for warehouses, categories, items, and photos."""
from django.contrib import admin

from apps.inventory.models import Item, ItemCategory, ItemPhoto, Warehouse


class ItemPhotoInline(admin.TabularInline):
    """Photos on the item change form. Slug is generated, never edited."""

    model = ItemPhoto
    extra = 0
    readonly_fields = ("slug",)


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    """Org warehouses. Slug is generated from name."""

    list_display = ("name", "org", "location", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "slug", "org__org_suffix")
    readonly_fields = ("slug", "created_at", "updated_at")


@admin.register(ItemCategory)
class ItemCategoryAdmin(admin.ModelAdmin):
    """Org-wide item categories. Slug is generated from name."""

    list_display = ("name", "org", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "slug", "org__org_suffix")
    readonly_fields = ("slug", "created_at", "updated_at")


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    """Warehouse catalog items. Slug and stock are not free-edited here."""

    list_display = (
        "name",
        "part_number",
        "warehouse",
        "org",
        "quantity_on_hand",
        "is_active",
    )
    list_filter = ("is_active", "warehouse")
    search_fields = ("name", "slug", "part_number", "org__org_suffix")
    readonly_fields = ("slug", "quantity_on_hand", "created_at", "updated_at")
    inlines = [ItemPhotoInline]
