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
    "/api/orgs/members/{slug}/suspend/",
    "/api/orgs/members/{slug}/unsuspend/",
    "/api/orgs/spaces/",
    "/api/orgs/spaces/{slug}/",
    "/api/orgs/spaces/{slug}/suspend/",
    "/api/orgs/spaces/{slug}/unsuspend/",
    "/api/orgs/spaces/{slug}/incharges/",
    "/api/orgs/spaces/{slug}/incharges/{member}/unassign/",
    "/api/orgs/vendors/",
    "/api/orgs/vendors/{slug}/",
    "/api/orgs/vendors/{slug}/suspend/",
    "/api/orgs/vendors/{slug}/unsuspend/",
    "/api/orgs/warehouses/",
    "/api/orgs/warehouses/{slug}/",
    "/api/orgs/item-categories/",
    "/api/orgs/item-categories/{slug}/",
    "/api/orgs/items/",
    "/api/orgs/items/{slug}/",
    "/api/orgs/items/{slug}/suspend/",
    "/api/orgs/items/{slug}/unsuspend/",
    "/api/orgs/items/{slug}/photos/",
    "/api/orgs/items/{slug}/photos/{photo_slug}/",
    "/api/orgs/purchase-requests/",
    "/api/orgs/purchase-requests/{slug}/",
    "/api/orgs/purchase-requests/{slug}/submit/",
    "/api/orgs/purchase-requests/{slug}/approve/",
    "/api/orgs/purchase-requests/{slug}/decline/",
    "/api/orgs/purchase-requests/{slug}/request-revision/",
    "/api/orgs/purchase-requests/{slug}/trail/",
    "/api/orgs/purchase-requests/{slug}/export/",
    "/api/orgs/rfqs/",
    "/api/orgs/rfqs/{slug}/",
    "/api/orgs/rfqs/{slug}/vendors/",
    "/api/orgs/rfqs/{slug}/vendors/{vendor_slug}/reject/",
    "/api/orgs/rfqs/{slug}/quotes/",
    "/api/orgs/rfqs/{slug}/request-revision/",
    "/api/orgs/rfqs/{slug}/select-lines/",
    "/api/orgs/rfqs/{slug}/purchase-orders/",
    "/api/orgs/rfqs/{slug}/export/",
    "/api/orgs/purchase-orders/",
    "/api/orgs/purchase-orders/{slug}/",
    "/api/orgs/purchase-orders/{slug}/quality-check/",
    "/api/orgs/purchase-orders/{slug}/invoice/",
    "/api/orgs/purchase-orders/{slug}/export/",
    "/api/orgs/purchase-orders/{slug}/invoice/export/",
    "/api/orgs/warehouse/receipts/",
    "/api/orgs/warehouse/receipts/{slug}/",
    "/api/orgs/warehouse/receipts/{slug}/complete/",
    "/api/orgs/warehouse/receipts/{slug}/export/",
    "/api/orgs/process-events/verify/",
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
    refresh = schema["paths"]["/api/auth/token/refresh/"]["post"]["responses"]
    for code in ("200", "401", "429"):
        assert code in refresh, f"refresh missing response {code}"


@pytest.mark.django_db
def test_org_members_schema_documents_success_and_errors():
    """Member endpoints must declare success and auth/validation errors."""
    schema = SchemaGenerator().get_schema(request=None, public=True)
    post = schema["paths"]["/api/orgs/members/"]["post"]["responses"]
    for code in ("201", "400", "401", "403"):
        assert code in post, f"members POST missing response {code}"
    get = schema["paths"]["/api/orgs/members/"]["get"]["responses"]
    for code in ("200", "400", "401", "403"):
        assert code in get, f"members GET missing response {code}"
    resend = schema["paths"]["/api/orgs/members/{slug}/resend-welcome/"]["post"][
        "responses"
    ]
    for code in ("200", "400", "401", "403", "404"):
        assert code in resend, f"resend missing response {code}"
    suspend = schema["paths"]["/api/orgs/members/{slug}/suspend/"]["post"]["responses"]
    for code in ("200", "400", "401", "403", "404"):
        assert code in suspend, f"suspend missing response {code}"
    unsuspend = schema["paths"]["/api/orgs/members/{slug}/unsuspend/"]["post"][
        "responses"
    ]
    for code in ("200", "400", "401", "403", "404"):
        assert code in unsuspend, f"unsuspend missing response {code}"


@pytest.mark.django_db
def test_vendors_schema_documents_success_and_errors():
    """Vendor endpoints must declare success and auth/validation errors."""
    schema = SchemaGenerator().get_schema(request=None, public=True)
    post = schema["paths"]["/api/orgs/vendors/"]["post"]["responses"]
    for code in ("201", "400", "401", "403"):
        assert code in post, f"vendors POST missing response {code}"
    get = schema["paths"]["/api/orgs/vendors/"]["get"]["responses"]
    for code in ("200", "400", "401", "403"):
        assert code in get, f"vendors GET missing response {code}"
    detail = schema["paths"]["/api/orgs/vendors/{slug}/"]["get"]["responses"]
    for code in ("200", "401", "403", "404"):
        assert code in detail, f"vendor GET missing response {code}"
    patch = schema["paths"]["/api/orgs/vendors/{slug}/"]["patch"]["responses"]
    for code in ("200", "400", "401", "403", "404"):
        assert code in patch, f"vendor PATCH missing response {code}"
    suspend = schema["paths"]["/api/orgs/vendors/{slug}/suspend/"]["post"]["responses"]
    for code in ("200", "400", "401", "403", "404"):
        assert code in suspend, f"vendor suspend missing response {code}"


@pytest.mark.django_db
def test_spaces_schema_documents_success_and_errors():
    """Space endpoints must declare success and auth/validation errors."""
    schema = SchemaGenerator().get_schema(request=None, public=True)
    post = schema["paths"]["/api/orgs/spaces/"]["post"]["responses"]
    for code in ("201", "400", "401", "403"):
        assert code in post, f"spaces POST missing response {code}"
    get = schema["paths"]["/api/orgs/spaces/"]["get"]["responses"]
    for code in ("200", "400", "401", "403"):
        assert code in get, f"spaces GET missing response {code}"
    assign = schema["paths"]["/api/orgs/spaces/{slug}/incharges/"]["post"]["responses"]
    for code in ("200", "400", "401", "403", "404"):
        assert code in assign, f"space assign missing response {code}"


@pytest.mark.django_db
def test_items_schema_documents_success_and_errors():
    """Item catalog endpoints must declare success and auth/validation errors."""
    schema = SchemaGenerator().get_schema(request=None, public=True)
    post = schema["paths"]["/api/orgs/items/"]["post"]["responses"]
    for code in ("201", "400", "401", "403"):
        assert code in post, f"items POST missing response {code}"
    get = schema["paths"]["/api/orgs/items/"]["get"]["responses"]
    for code in ("200", "400", "401", "403"):
        assert code in get, f"items GET missing response {code}"
    photos = schema["paths"]["/api/orgs/items/{slug}/photos/"]["post"]["responses"]
    for code in ("201", "400", "401", "403", "404"):
        assert code in photos, f"item photos POST missing response {code}"
    warehouses = schema["paths"]["/api/orgs/warehouses/"]["post"]["responses"]
    for code in ("201", "400", "401", "403"):
        assert code in warehouses, f"warehouses POST missing response {code}"
    categories = schema["paths"]["/api/orgs/item-categories/"]["post"]["responses"]
    for code in ("201", "400", "401", "403"):
        assert code in categories, f"categories POST missing response {code}"


@pytest.mark.django_db
def test_purchases_schema_documents_success_and_errors():
    """Purchase-flow endpoints must declare success and auth/validation errors."""
    schema = SchemaGenerator().get_schema(request=None, public=True)
    pr_post = schema["paths"]["/api/orgs/purchase-requests/"]["post"]["responses"]
    for code in ("201", "400", "401", "403"):
        assert code in pr_post, f"PR POST missing response {code}"
    select = schema["paths"]["/api/orgs/rfqs/{slug}/select-lines/"]["post"]["responses"]
    for code in ("200", "400", "401", "403", "404"):
        assert code in select, f"select-lines missing response {code}"
    complete = schema["paths"]["/api/orgs/warehouse/receipts/{slug}/complete/"]["post"][
        "responses"
    ]
    for code in ("200", "400", "401", "403", "404"):
        assert code in complete, f"receipt complete missing response {code}"
    verify = schema["paths"]["/api/orgs/process-events/verify/"]["post"]["responses"]
    for code in ("200", "401", "403"):
        assert code in verify, f"verify missing response {code}"
    export = schema["paths"]["/api/orgs/purchase-requests/{slug}/export/"]["get"][
        "responses"
    ]
    for code in ("200", "400", "401", "403", "404"):
        assert code in export, f"PR export missing response {code}"


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

