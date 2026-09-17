"""
URL patterns for the organisations app.

Member management is scoped to the caller's organisation; the org is never
passed in the URL.  Members are identified by UserProfile.slug.
"""
from django.urls import path

from apps.organizations.views import (
    OrgMemberListCreateView,
    OrgMemberResendWelcomeView,
    OrgMemberSuspendView,
    OrgMemberUnsuspendView,
)
from apps.organizations.space_views import (
    SpaceInchargeListCreateView,
    SpaceInchargeUnassignView,
    SpaceListCreateView,
    SpaceRetrieveUpdateView,
    SpaceSuspendView,
    SpaceUnsuspendView,
)

app_name = "organizations"

urlpatterns = [
    path("members/", OrgMemberListCreateView.as_view(), name="member-list"),
    path(
        "members/<slug:slug>/resend-welcome/",
        OrgMemberResendWelcomeView.as_view(),
        name="member-resend-welcome",
    ),
    path(
        "members/<slug:slug>/suspend/",
        OrgMemberSuspendView.as_view(),
        name="member-suspend",
    ),
    path(
        "members/<slug:slug>/unsuspend/",
        OrgMemberUnsuspendView.as_view(),
        name="member-unsuspend",
    ),
    path("spaces/", SpaceListCreateView.as_view(), name="space-list"),
    path("spaces/<slug:slug>/", SpaceRetrieveUpdateView.as_view(), name="space-detail"),
    path(
        "spaces/<slug:slug>/suspend/",
        SpaceSuspendView.as_view(),
        name="space-suspend",
    ),
    path(
        "spaces/<slug:slug>/unsuspend/",
        SpaceUnsuspendView.as_view(),
        name="space-unsuspend",
    ),
    path(
        "spaces/<slug:slug>/incharges/",
        SpaceInchargeListCreateView.as_view(),
        name="space-incharge-list",
    ),
    path(
        "spaces/<slug:slug>/incharges/<slug:member>/unassign/",
        SpaceInchargeUnassignView.as_view(),
        name="space-incharge-unassign",
    ),
]
