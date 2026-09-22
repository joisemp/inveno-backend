"""Django admin for warehouses, categories, items, photos, and activity."""
from django.contrib import admin

from apps.inventory.models import Item, ItemActivity, ItemCategory, ItemPhoto, Warehouse


class ItemPhotoInline(admin.TabularInline):
    """Photos on the item change form. Slug is generated, never edited."""

    model = ItemPhoto
    extra = 0
    readonly_fields = ("slug",)


class ItemActivityInline(admin.TabularInline):
    """Read-only activity trail on the item change form."""

    model = ItemActivity
    extra = 0
    can_delete = False
    readonly_fields = (
        "slug",
        "kind",
        "action",
        "actor_full_name",
        "remarks",
        "created_at",
    )

    def has_add_permission(self, request, obj=None):
        return False


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
    inlines = [ItemPhotoInline, ItemActivityInline]


@admin.register(ItemActivity)
class ItemActivityAdmin(admin.ModelAdmin):
    """Append-only item history. Slug and snapshots are never edited."""

    list_display = (
        "slug",
        "item",
        "kind",
        "action",
        "actor_full_name",
        "created_at",
    )
    list_filter = ("kind", "action")
    search_fields = ("slug", "item__name", "actor_slug", "item__org__org_suffix")
    readonly_fields = (
        "slug",
        "org",
        "item",
        "actor",
        "actor_slug",
        "actor_full_name",
        "actor_user_type",
        "kind",
        "action",
        "remarks",
        "previous_quantity",
        "quantity",
        "delta",
        "reference_type",
        "reference_slug",
        "payload",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
