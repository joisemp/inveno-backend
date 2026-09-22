"""API views for warehouses and item categories."""
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)
from rest_framework import generics, permissions, status
from rest_framework.response import Response

from apps.common.openapi import error_responses
from apps.inventory.models import ItemCategory, Warehouse
from apps.inventory.serializers import (
    ItemCategoryCreateSerializer,
    ItemCategorySerializer,
    ItemCategoryUpdateSerializer,
    WarehouseCreateSerializer,
    WarehouseSerializer,
    WarehouseUpdateSerializer,
)
from apps.organizations.permissions import IsItemReader, IsItemWriter

INVALID_STATUS = 'Must be "active" or "suspended".'
STATUS_VALUES = ("active", "suspended")


def field_error_response(*examples):
    flat = []
    for item in examples:
        if isinstance(item, (list, tuple)):
            flat.extend(item)
        else:
            flat.append(item)
    return OpenApiResponse(
        response=OpenApiTypes.OBJECT,
        description="Validation error.",
        examples=flat,
    )


_EXAMPLE_WAREHOUSE = {
    "slug": "warehouse",
    "name": "Warehouse",
    "location": "",
    "is_active": True,
    "created_at": "2026-09-17T10:00:00Z",
    "updated_at": "2026-09-17T10:00:00Z",
}

_EXAMPLE_CATEGORY = {
    "slug": "stationery",
    "name": "Stationery",
    "is_active": True,
    "created_at": "2026-09-17T10:00:00Z",
    "updated_at": "2026-09-17T10:00:00Z",
}

_WH_SLUG = OpenApiParameter(
    name="slug",
    type=OpenApiTypes.STR,
    location=OpenApiParameter.PATH,
    description="Warehouse slug.",
)

_CAT_SLUG = OpenApiParameter(
    name="slug",
    type=OpenApiTypes.STR,
    location=OpenApiParameter.PATH,
    description="Category slug.",
)

_WH_NOT_FOUND = OpenApiResponse(
    response=OpenApiTypes.OBJECT,
    description="Not found.",
    examples=[
        OpenApiExample(
            "Not found",
            value={"detail": "Not found."},
            response_only=True,
            status_codes=["404"],
        )
    ],
)


def _status_filter(qs, request):
    value = request.query_params.get("status")
    if value == "active":
        return qs.filter(is_active=True)
    if value == "suspended":
        return qs.filter(is_active=False)
    return qs


@extend_schema_view(
    get=extend_schema(
        tags=["Warehouses"],
        summary="List warehouses",
        parameters=[
            OpenApiParameter(
                name="status",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=False,
                enum=list(STATUS_VALUES),
            )
        ],
        responses={
            200: WarehouseSerializer(many=True),
            400: field_error_response(
                OpenApiExample(
                    "Invalid status",
                    value={"status": [INVALID_STATUS]},
                    response_only=True,
                    status_codes=["400"],
                )
            ),
            **error_responses(401, 403),
        },
    ),
    post=extend_schema(
        tags=["Warehouses"],
        summary="Create a warehouse",
        request=WarehouseCreateSerializer,
        responses={
            201: WarehouseSerializer,
            400: field_error_response(
                OpenApiExample(
                    "Duplicate name",
                    value={"name": ["A warehouse with this name already exists."]},
                    response_only=True,
                    status_codes=["400"],
                ),
            ),
            **error_responses(401, 403),
        },
        examples=[
            OpenApiExample(
                "Created",
                value=_EXAMPLE_WAREHOUSE,
                response_only=True,
                status_codes=["201"],
            )
        ],
    ),
)
class WarehouseListCreateView(generics.ListCreateAPIView):
    """List warehouses, or create one (same writers as items)."""

    serializer_class = WarehouseSerializer

    def get_permissions(self):
        if self.request.method == "POST":
            return [permissions.IsAuthenticated(), IsItemWriter()]
        return [permissions.IsAuthenticated(), IsItemReader()]

    def get_queryset(self):
        qs = Warehouse.objects.filter(org=self.request.user.profile.org).order_by(
            "name"
        )
        return _status_filter(qs, self.request)

    def list(self, request, *args, **kwargs):
        value = request.query_params.get("status")
        if value is not None and value not in STATUS_VALUES:
            return Response(
                {"status": [INVALID_STATUS]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().list(request, *args, **kwargs)

    def get_serializer_class(self):
        if self.request.method == "POST":
            return WarehouseCreateSerializer
        return WarehouseSerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["org"] = self.request.user.profile.org
        return ctx

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        warehouse = serializer.save()
        return Response(
            WarehouseSerializer(warehouse).data, status=status.HTTP_201_CREATED
        )


@extend_schema_view(
    get=extend_schema(
        tags=["Warehouses"],
        summary="Get a warehouse",
        parameters=[_WH_SLUG],
        responses={
            200: WarehouseSerializer,
            404: _WH_NOT_FOUND,
            **error_responses(401, 403),
        },
    ),
    patch=extend_schema(
        tags=["Warehouses"],
        summary="Update a warehouse",
        parameters=[_WH_SLUG],
        request=WarehouseUpdateSerializer,
        responses={
            200: WarehouseSerializer,
            400: field_error_response(
                OpenApiExample(
                    "Duplicate name",
                    value={"name": ["A warehouse with this name already exists."]},
                    response_only=True,
                    status_codes=["400"],
                ),
            ),
            404: _WH_NOT_FOUND,
            **error_responses(401, 403),
        },
    ),
)
class WarehouseRetrieveUpdateView(generics.RetrieveUpdateAPIView):
    """Retrieve or patch a warehouse. is_active is writable here."""

    serializer_class = WarehouseSerializer
    lookup_field = "slug"
    lookup_url_kwarg = "slug"
    http_method_names = ["get", "patch", "head", "options"]

    def get_permissions(self):
        if self.request.method == "PATCH":
            return [permissions.IsAuthenticated(), IsItemWriter()]
        return [permissions.IsAuthenticated(), IsItemReader()]

    def get_queryset(self):
        return Warehouse.objects.filter(org=self.request.user.profile.org)

    def get_serializer_class(self):
        if self.request.method == "PATCH":
            return WarehouseUpdateSerializer
        return WarehouseSerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["org"] = self.request.user.profile.org
        return ctx

    def update(self, request, *args, **kwargs):
        warehouse = self.get_object()
        serializer = self.get_serializer(warehouse, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        warehouse = serializer.save()
        return Response(WarehouseSerializer(warehouse).data)


@extend_schema_view(
    get=extend_schema(
        tags=["Item categories"],
        summary="List item categories",
        responses={200: ItemCategorySerializer(many=True), **error_responses(401, 403)},
    ),
    post=extend_schema(
        tags=["Item categories"],
        summary="Create an item category",
        request=ItemCategoryCreateSerializer,
        responses={
            201: ItemCategorySerializer,
            400: field_error_response(
                OpenApiExample(
                    "Duplicate name",
                    value={"name": ["A category with this name already exists."]},
                    response_only=True,
                    status_codes=["400"],
                ),
            ),
            **error_responses(401, 403),
        },
        examples=[
            OpenApiExample(
                "Created",
                value=_EXAMPLE_CATEGORY,
                response_only=True,
                status_codes=["201"],
            )
        ],
    ),
)
class ItemCategoryListCreateView(generics.ListCreateAPIView):
    """List org categories, or create one."""

    serializer_class = ItemCategorySerializer

    def get_permissions(self):
        if self.request.method == "POST":
            return [permissions.IsAuthenticated(), IsItemWriter()]
        return [permissions.IsAuthenticated(), IsItemReader()]

    def get_queryset(self):
        return ItemCategory.objects.filter(org=self.request.user.profile.org).order_by(
            "name"
        )

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ItemCategoryCreateSerializer
        return ItemCategorySerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["org"] = self.request.user.profile.org
        return ctx

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        category = serializer.save()
        return Response(
            ItemCategorySerializer(category).data, status=status.HTTP_201_CREATED
        )


@extend_schema_view(
    get=extend_schema(
        tags=["Item categories"],
        summary="Get an item category",
        parameters=[_CAT_SLUG],
        responses={
            200: ItemCategorySerializer,
            404: _WH_NOT_FOUND,
            **error_responses(401, 403),
        },
    ),
    patch=extend_schema(
        tags=["Item categories"],
        summary="Update an item category",
        parameters=[_CAT_SLUG],
        request=ItemCategoryUpdateSerializer,
        responses={
            200: ItemCategorySerializer,
            400: field_error_response(
                OpenApiExample(
                    "Duplicate name",
                    value={"name": ["A category with this name already exists."]},
                    response_only=True,
                    status_codes=["400"],
                ),
            ),
            404: _WH_NOT_FOUND,
            **error_responses(401, 403),
        },
    ),
)
class ItemCategoryRetrieveUpdateView(generics.RetrieveUpdateAPIView):
    """Retrieve or patch a category."""

    serializer_class = ItemCategorySerializer
    lookup_field = "slug"
    lookup_url_kwarg = "slug"
    http_method_names = ["get", "patch", "head", "options"]

    def get_permissions(self):
        if self.request.method == "PATCH":
            return [permissions.IsAuthenticated(), IsItemWriter()]
        return [permissions.IsAuthenticated(), IsItemReader()]

    def get_queryset(self):
        return ItemCategory.objects.filter(org=self.request.user.profile.org)

    def get_serializer_class(self):
        if self.request.method == "PATCH":
            return ItemCategoryUpdateSerializer
        return ItemCategorySerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["org"] = self.request.user.profile.org
        return ctx

    def update(self, request, *args, **kwargs):
        category = self.get_object()
        serializer = self.get_serializer(category, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        category = serializer.save()
        return Response(ItemCategorySerializer(category).data)
