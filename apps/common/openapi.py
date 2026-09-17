"""
Reusable OpenAPI serializers and error examples for drf-spectacular.

Every public API view should import these helpers so Swagger shows the same
success and error payloads documented in FRONTEND_API.md.
"""
from drf_spectacular.utils import OpenApiExample, OpenApiResponse
from rest_framework import serializers


class DetailSerializer(serializers.Serializer):
    """Standard `{ "detail": "..." }` body used by most auth success/error replies."""

    detail = serializers.CharField()


class HealthSerializer(serializers.Serializer):
    """GET /api/health/ payload."""

    status = serializers.CharField()
    db = serializers.CharField()
    redis = serializers.CharField()


class TokenPairSerializer(serializers.Serializer):
    """JWT access token returned by login and token refresh."""

    access = serializers.CharField()


class TokenVerifyRequestSerializer(serializers.Serializer):
    token = serializers.CharField()


class LoginRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField()


class EmptySerializer(serializers.Serializer):
    """Empty object — POST /api/auth/token/verify/ success body."""


# ---------------------------------------------------------------------------
# Shared examples
# ---------------------------------------------------------------------------

EXAMPLE_401_UNAUTH = OpenApiExample(
    "Not authenticated",
    value={"detail": "Authentication credentials were not provided."},
    response_only=True,
    status_codes=["401"],
)

EXAMPLE_401_EXPIRED_JWT = OpenApiExample(
    "Invalid or expired JWT",
    value={
        "detail": "Given token not valid for any token type",
        "code": "token_not_valid",
        "messages": [
            {
                "token_class": "AccessToken",
                "token_type": "access",
                "message": "Token is invalid or expired",
            }
        ],
    },
    response_only=True,
    status_codes=["401"],
)

EXAMPLE_403_FORBIDDEN = OpenApiExample(
    "Forbidden",
    value={"detail": "You do not have permission to perform this action."},
    response_only=True,
    status_codes=["403"],
)

EXAMPLE_429_THROTTLED = OpenApiExample(
    "Rate limited",
    value={"detail": "Request was throttled. Expected available in 42 seconds."},
    response_only=True,
    status_codes=["429"],
)


def error_responses(*status_codes: int) -> dict:
    """
    Build a spectacular `responses={...}` dict for shared error statuses.

    Supported codes: 401, 403, 429.
    """
    catalog = {
        401: OpenApiResponse(
            response=DetailSerializer,
            description="Not authenticated or token invalid/expired.",
            examples=[EXAMPLE_401_UNAUTH, EXAMPLE_401_EXPIRED_JWT],
        ),
        403: OpenApiResponse(
            response=DetailSerializer,
            description="Authenticated but not allowed (staff/superuser required).",
            examples=[EXAMPLE_403_FORBIDDEN],
        ),
        429: OpenApiResponse(
            response=DetailSerializer,
            description="Too many requests.",
            examples=[EXAMPLE_429_THROTTLED],
        ),
    }
    missing = [code for code in status_codes if code not in catalog]
    if missing:
        raise ValueError(f"Unsupported error status codes: {missing}")
    return {code: catalog[code] for code in status_codes}


def detail_response(description: str, example_name: str, value: dict, status_code: str = "200"):
    """OpenApiResponse wrapping DetailSerializer with a single example."""
    return OpenApiResponse(
        response=DetailSerializer,
        description=description,
        examples=[
            OpenApiExample(
                example_name,
                value=value,
                response_only=True,
                status_codes=[status_code],
            )
        ],
    )
