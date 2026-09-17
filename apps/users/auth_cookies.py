"""
HttpOnly JWT refresh cookie helpers.

Access tokens stay in JSON (Bearer header). Refresh tokens are never returned
in the body — they are set as a host-only cookie scoped to /api/auth/.
"""
from django.conf import settings
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)


def refresh_cookie_kwargs() -> dict:
    """Shared flags for set_cookie / delete_cookie on the refresh cookie."""
    return {
        "key": settings.REFRESH_TOKEN_COOKIE_NAME,
        "httponly": True,
        "secure": settings.REFRESH_TOKEN_COOKIE_SECURE,
        "samesite": settings.REFRESH_TOKEN_COOKIE_SAMESITE,
        "path": settings.REFRESH_TOKEN_COOKIE_PATH,
    }


def set_refresh_cookie(response, token: str) -> None:
    """Attach the rotating refresh token as an httpOnly cookie."""
    max_age = int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds())
    kwargs = refresh_cookie_kwargs()
    response.set_cookie(
        kwargs.pop("key"),
        token,
        max_age=max_age,
        **kwargs,
    )


def clear_refresh_cookie(response) -> None:
    """Expire the refresh cookie on logout or password change."""
    kwargs = refresh_cookie_kwargs()
    response.delete_cookie(
        kwargs["key"],
        path=kwargs["path"],
        samesite=kwargs["samesite"],
    )


def attach_rotated_refresh_cookie(response):
    """
    Move ``refresh`` from a 200 JWT JSON body onto the httpOnly cookie.

    Login and refresh serializers still emit both tokens internally; the
    public JSON body keeps only ``access``.
    """
    if response.status_code == 200 and isinstance(response.data, dict):
        refresh = response.data.pop("refresh", None)
        if refresh:
            set_refresh_cookie(response, refresh)
    return response


def blacklist_user_refresh_tokens(user) -> None:
    """Invalidate every outstanding refresh token for ``user``."""
    for outstanding in OutstandingToken.objects.filter(user=user):
        BlacklistedToken.objects.get_or_create(token=outstanding)
