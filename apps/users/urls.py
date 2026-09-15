"""
URL patterns for the users app.

Public registration (POST /api/auth/register/) has been removed.
Accounts are created through Django Admin via the organisation registration flow.
"""
from django.urls import path

from .views import (
    ChangePasswordView,
    LoginView,
    LogoutView,
    MeView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    PasswordSetView,
    TokenRefreshView,
    TokenVerifyView,
)

app_name = "users"

urlpatterns = [
    # JWT token endpoints
    path("login/", LoginView.as_view(), name="token-obtain"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("token/verify/", TokenVerifyView.as_view(), name="token-verify"),

    # Profile
    path("me/", MeView.as_view(), name="me"),

    # Auth actions
    path("logout/", LogoutView.as_view(), name="logout"),
    path("password/change/", ChangePasswordView.as_view(), name="password-change"),

    # Forgot-password flow
    path("password/reset/", PasswordResetRequestView.as_view(), name="password-reset"),
    path("password/reset/confirm/", PasswordResetConfirmView.as_view(), name="password-reset-confirm"),

    # Welcome-email get-started flow (set password for the first time)
    path("password/set/", PasswordSetView.as_view(), name="password-set"),
]
