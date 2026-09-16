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
]
