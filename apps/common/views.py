"""Frontend guide page — same chrome as Swagger UI, staff-only."""
from django.shortcuts import render
from drf_spectacular.generators import SchemaGenerator
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAdminUser
from rest_framework.views import APIView

from apps.common.frontend_docs import (
    load_frontend_guide,
    markdown_to_html,
    public_api_operations,
    spectacular_favicon,
)
from apps.common.openapi import error_responses


class FrontendGuideView(APIView):
    """React + Vite guide rendered in the Swagger docs chrome."""

    permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["System"],
        summary="Frontend guide",
        exclude=False,
        responses={
            200: {"description": "Frontend integration guide HTML."},
            **error_responses(401, 403),
        },
    )
    def get(self, request, *args, **kwargs):
        schema = SchemaGenerator().get_schema(request=None, public=True) or {}
        return render(
            request,
            "drf_spectacular/frontend_guide.html",
            {
                "title": "Inveno API",
                "favicon_href": spectacular_favicon(),
                "docs_nav": "frontend",
                "guide_html": markdown_to_html(load_frontend_guide()),
                "operations": public_api_operations(schema),
            },
        )
