"""
URL patterns for vendors.

Scoped to the caller's organisation. Vendors are identified by slug.
"""
from django.urls import path

from apps.vendors.views import (
    VendorListCreateView,
    VendorRetrieveUpdateView,
    VendorSuspendView,
    VendorUnsuspendView,
)

app_name = "vendors"

urlpatterns = [
    path("vendors/", VendorListCreateView.as_view(), name="vendor-list"),
    path(
        "vendors/<slug:slug>/",
        VendorRetrieveUpdateView.as_view(),
        name="vendor-detail",
    ),
    path(
        "vendors/<slug:slug>/suspend/",
        VendorSuspendView.as_view(),
        name="vendor-suspend",
    ),
    path(
        "vendors/<slug:slug>/unsuspend/",
        VendorUnsuspendView.as_view(),
        name="vendor-unsuspend",
    ),
]
