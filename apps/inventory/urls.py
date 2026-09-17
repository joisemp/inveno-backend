"""Item catalog URLs, mounted under /api/orgs/."""
from django.urls import path

from apps.inventory.views import (
    ItemListCreateView,
    ItemRetrieveUpdateView,
    ItemSuspendView,
    ItemUnsuspendView,
)

app_name = "inventory"

urlpatterns = [
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
]
