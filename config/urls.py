from django.contrib import admin
from django.urls import include, path
from drf_spectacular.utils import extend_schema
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)
from rest_framework.permissions import IsAdminUser

from apps.common.openapi import error_responses


class DocumentedSchemaView(SpectacularAPIView):
    """Raw OpenAPI schema — superuser only."""

    permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["System"],
        summary="OpenAPI schema",
        exclude=False,
        responses={
            200: {"description": "OpenAPI 3 schema (JSON or YAML)."},
            **error_responses(401, 403),
        },
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class DocumentedSwaggerView(SpectacularSwaggerView):
    """Swagger UI — superuser only (log in at /admin/ first)."""

    permission_classes = [IsAdminUser]
    url_name = "schema"

    @extend_schema(
        tags=["System"],
        summary="Swagger UI",
        exclude=False,
        responses={
            200: {"description": "Interactive Swagger UI HTML."},
            **error_responses(401, 403),
        },
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class DocumentedRedocView(SpectacularRedocView):
    """ReDoc — superuser only."""

    permission_classes = [IsAdminUser]
    url_name = "schema"

    @extend_schema(
        tags=["System"],
        summary="ReDoc",
        exclude=False,
        responses={
            200: {"description": "ReDoc HTML."},
            **error_responses(401, 403),
        },
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


urlpatterns = [
    # Django admin
    path("admin/", admin.site.urls),

    # API v1
    path("api/", include("apps.healthcheck.urls")),
    path("api/auth/", include("apps.users.urls")),

    # API Documentation — superuser only (log in at /admin/ first)
    path("api/schema/", DocumentedSchemaView.as_view(), name="schema"),
    path("api/docs/", DocumentedSwaggerView.as_view(), name="swagger-ui"),
    path("api/redoc/", DocumentedRedocView.as_view(), name="redoc"),
]
