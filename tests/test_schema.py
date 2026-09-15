"""OpenAPI schema generation — every documented path must appear."""
import pytest
from drf_spectacular.generators import SchemaGenerator

EXPECTED_PATHS = [
    "/api/health/",
    "/api/auth/login/",
    "/api/auth/token/refresh/",
    "/api/auth/token/verify/",
    "/api/auth/me/",
    "/api/auth/logout/",
    "/api/auth/password/change/",
    "/api/auth/password/reset/",
    "/api/auth/password/reset/confirm/",
    "/api/auth/password/set/",
    "/api/schema/",
    "/api/docs/",
    "/api/redoc/",
]


@pytest.mark.django_db
def test_schema_generates_and_includes_documented_paths():
    """Spectacular must generate a schema that lists every public API path."""
    schema = SchemaGenerator().get_schema(request=None, public=True)
    assert schema is not None
    paths = schema["paths"]
    missing = [path for path in EXPECTED_PATHS if path not in paths]
    assert missing == [], f"Schema missing paths: {missing}"


@pytest.mark.django_db
def test_login_schema_documents_success_and_errors():
    """POST /api/auth/login/ must declare 200, 400, 401, 429."""
    schema = SchemaGenerator().get_schema(request=None, public=True)
    responses = schema["paths"]["/api/auth/login/"]["post"]["responses"]
    for code in ("200", "400", "401", "429"):
        assert code in responses, f"login missing response {code}"


@pytest.mark.django_db
def test_schema_endpoint_requires_admin(superuser_client):
    """GET /api/schema/ is superuser-only."""
    from rest_framework.test import APIClient

    denied = APIClient().get("/api/schema/")
    assert denied.status_code in (401, 403)

    allowed = superuser_client.get("/api/schema/")
    assert allowed.status_code == 200
