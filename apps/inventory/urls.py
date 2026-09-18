"""Item catalog URLs, mounted under /api/orgs/."""
from django.urls import path

from apps.inventory.views import (
    ItemListCreateView,
    ItemPhotoCreateView,
    ItemPhotoDeleteView,
    ItemRetrieveUpdateView,
    ItemSuspendView,
    ItemUnsuspendView,
)
from apps.inventory.warehouse_views import (
    ItemCategoryListCreateView,
    ItemCategoryRetrieveUpdateView,
    WarehouseListCreateView,
    WarehouseRetrieveUpdateView,
)

app_name = "inventory"

urlpatterns = [
    path("warehouses/", WarehouseListCreateView.as_view(), name="warehouse-list"),
    path(
        "warehouses/<slug:slug>/",
        WarehouseRetrieveUpdateView.as_view(),
        name="warehouse-detail",
    ),
    path(
        "item-categories/",
        ItemCategoryListCreateView.as_view(),
        name="item-category-list",
    ),
    path(
        "item-categories/<slug:slug>/",
        ItemCategoryRetrieveUpdateView.as_view(),
        name="item-category-detail",
    ),
    path("items/", ItemListCreateView.as_view(), name="item-list"),
    path("items/<slug:slug>/", ItemRetrieveUpdateView.as_view(), name="item-detail"),
    path(
        "items/<slug:slug>/suspend/",
        ItemSuspendView.as_view(),
        name="item-suspend",
    ),
    path(
        "items/<slug:slug>/unsuspend/",
        ItemUnsuspendView.as_view(),
        name="item-unsuspend",
    ),
    path(
        "items/<slug:slug>/photos/",
        ItemPhotoCreateView.as_view(),
        name="item-photo-create",
    ),
    path(
        "items/<slug:slug>/photos/<slug:photo_slug>/",
        ItemPhotoDeleteView.as_view(),
        name="item-photo-delete",
    ),
]
