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
    "/api/orgs/members/",
    "/api/orgs/members/{slug}/resend-welcome/",
    "/api/schema/",
    "/api/docs/",
    "/api/docs/frontend/",
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
def test_org_members_schema_documents_success_and_errors():
    """Member endpoints must declare success and auth/validation errors."""
    schema = SchemaGenerator().get_schema(request=None, public=True)
    post = schema["paths"]["/api/orgs/members/"]["post"]["responses"]
    for code in ("201", "400", "401", "403"):
        assert code in post, f"members POST missing response {code}"
    get = schema["paths"]["/api/orgs/members/"]["get"]["responses"]
    for code in ("200", "401", "403"):
        assert code in get, f"members GET missing response {code}"
    resend = schema["paths"]["/api/orgs/members/{slug}/resend-welcome/"]["post"][
        "responses"
    ]
    for code in ("200", "400", "401", "403", "404"):
        assert code in resend, f"resend missing response {code}"


@pytest.mark.django_db
def test_schema_endpoint_requires_admin(superuser_client):
    """GET /api/schema/ is superuser-only."""
    from rest_framework.test import APIClient

    denied = APIClient().get("/api/schema/")
    assert denied.status_code in (401, 403)

    allowed = superuser_client.get("/api/schema/")
    assert allowed.status_code == 200


@pytest.mark.django_db
def test_schema_description_points_to_frontend_tab():
    """OpenAPI info.description must link the Frontend tab, not dump the guide."""
    schema = SchemaGenerator().get_schema(request=None, public=True)
    description = schema["info"]["description"]
    assert "/api/docs/frontend/" in description
    assert "VITE_API_URL" not in description


@pytest.mark.django_db
def test_frontend_guide_requires_admin(superuser_client, test_user):
    """GET /api/docs/frontend/ is staff-only."""
    from rest_framework.test import APIClient
    from rest_framework_simplejwt.tokens import RefreshToken

    denied = APIClient().get("/api/docs/frontend/")
    assert denied.status_code in (401, 403)

    member = APIClient()
    refresh = RefreshToken.for_user(test_user)
    member.credentials(HTTP_AUTHORIZATION=f"Bearer {str(refresh.access_token)}")
    assert member.get("/api/docs/frontend/").status_code == 403

    allowed = superuser_client.get("/api/docs/frontend/")
    assert allowed.status_code == 200
    html = allowed.content.decode()
    for marker in ("password/set", "user_type", "Bearer", "VITE_API_URL", "vite"):
        assert marker in html, f"frontend guide missing {marker}"


@pytest.mark.django_db
def test_frontend_guide_index_covers_schema_paths(superuser_client):
    """Live endpoint table must list every non-docs schema path."""
    from apps.common.frontend_docs import DOCS_PATHS, public_api_operations

    schema = SchemaGenerator().get_schema(request=None, public=True)
    ops = public_api_operations(schema)
    indexed = {row["path"] for row in ops}
    expected = set(schema["paths"]) - DOCS_PATHS
    missing = expected - indexed
    assert not missing, f"endpoint index missing paths: {missing}"

    html = superuser_client.get("/api/docs/frontend/").content.decode()
    for path in expected:
        assert path in html, f"guide HTML missing {path}"


def test_frontend_guide_markdown_renders_code_and_headings():
    """Stdlib markdown converter must keep TS fences and headings."""
    from apps.common.frontend_docs import load_frontend_guide, markdown_to_html

    html = markdown_to_html(load_frontend_guide())
    assert "<h1>" in html
    assert "<pre><code" in html
    assert "VITE_API_URL" in html
    assert "<script" not in html.lower()

