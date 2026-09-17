"""API views for the org item catalog."""
from django.core.exceptions import ValidationError as DjangoValidationError
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

from apps.common.openapi import EmptySerializer, detail_response, error_responses
from apps.inventory.models import Item
from apps.inventory.serializers import (
    ItemCreateSerializer,
    ItemSerializer,
    ItemUpdateSerializer,
)
from apps.inventory.services import (
    ALREADY_SUSPENDED,
    ITEM_SUSPENDED,
    ITEM_UNSUSPENDED,
    NOT_SUSPENDED,
    suspend_item,
    unsuspend_item,
)
from apps.organizations.permissions import IsItemReader, IsItemWriter

ITEM_STATUS_VALUES = ("active", "suspended")
INVALID_STATUS = 'Must be "active" or "suspended".'


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


def _detail_from_validation_error(exc: DjangoValidationError) -> str:
    if hasattr(exc, "message_dict") and "detail" in exc.message_dict:
        val = exc.message_dict["detail"]
        return val[0] if isinstance(val, list) else val
    if exc.messages:
        return exc.messages[0]
    return "Invalid."


_EXAMPLE_ITEM = {
    "slug": "a4-paper",
    "name": "A4 paper",
    "sku": "PAP-A4",
    "unit": "ream",
    "quantity_on_hand": "0.000",
    "is_active": True,
    "created_at": "2026-09-17T10:00:00Z",
    "updated_at": "2026-09-17T10:00:00Z",
}

_SLUG_PARAM = OpenApiParameter(
    name="slug",
    type=OpenApiTypes.STR,
    location=OpenApiParameter.PATH,
    description="Item slug.",
)

_NOT_FOUND = detail_response(
    "Unknown slug or item belongs to another organisation.",
    "Not found",
    {"detail": "Not found."},
    status_code="404",
)


@extend_schema_view(
    get=extend_schema(
        tags=["Items"],
        summary="List catalog items",
        parameters=[
            OpenApiParameter(
                name="status",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=False,
                enum=list(ITEM_STATUS_VALUES),
            )
        ],
        responses={
            200: ItemSerializer(many=True),
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
        tags=["Items"],
        summary="Create a catalog item",
        request=ItemCreateSerializer,
        responses={
            201: ItemSerializer,
            400: field_error_response(
                OpenApiExample(
                    "Duplicate name",
                    value={"name": ["An item with this name already exists."]},
                    response_only=True,
                    status_codes=["400"],
                ),
            ),
            **error_responses(401, 403),
        },
        examples=[
            OpenApiExample(
                "Created",
                value=_EXAMPLE_ITEM,
                response_only=True,
                status_codes=["201"],
            )
        ],
    ),
)
class ItemListCreateView(generics.ListCreateAPIView):
    """List items, or create one (warehouse / central admin)."""

    serializer_class = ItemSerializer

    def get_permissions(self):
        if self.request.method == "POST":
            return [permissions.IsAuthenticated(), IsItemWriter()]
        return [permissions.IsAuthenticated(), IsItemReader()]

    def get_queryset(self):
        qs = Item.objects.filter(org=self.request.user.profile.org).order_by("name")
        item_status = self.request.query_params.get("status")
        if item_status == "active":
            return qs.filter(is_active=True)
        if item_status == "suspended":
            return qs.filter(is_active=False)
        return qs

    def list(self, request, *args, **kwargs):
        item_status = request.query_params.get("status")
        if item_status is not None and item_status not in ITEM_STATUS_VALUES:
            return Response(
                {"status": [INVALID_STATUS]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().list(request, *args, **kwargs)

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ItemCreateSerializer
        return ItemSerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["org"] = self.request.user.profile.org
        return ctx

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = serializer.save()
        return Response(ItemSerializer(item).data, status=status.HTTP_201_CREATED)


@extend_schema_view(
    get=extend_schema(
        tags=["Items"],
        summary="Get a catalog item",
        parameters=[_SLUG_PARAM],
        responses={200: ItemSerializer, 404: _NOT_FOUND, **error_responses(401, 403)},
    ),
    patch=extend_schema(
        tags=["Items"],
        summary="Update a catalog item",
        parameters=[_SLUG_PARAM],
        request=ItemUpdateSerializer,
        responses={
            200: ItemSerializer,
            400: field_error_response(
                OpenApiExample(
                    "Duplicate name",
                    value={"name": ["An item with this name already exists."]},
                    response_only=True,
                    status_codes=["400"],
                ),
            ),
            404: _NOT_FOUND,
            **error_responses(401, 403),
        },
    ),
)
class ItemRetrieveUpdateView(generics.RetrieveUpdateAPIView):
    """Retrieve or patch catalog fields. quantity_on_hand is never writable."""

    serializer_class = ItemSerializer
    lookup_field = "slug"
    lookup_url_kwarg = "slug"
    http_method_names = ["get", "patch", "head", "options"]

    def get_permissions(self):
        if self.request.method == "PATCH":
            return [permissions.IsAuthenticated(), IsItemWriter()]
        return [permissions.IsAuthenticated(), IsItemReader()]

    def get_queryset(self):
        return Item.objects.filter(org=self.request.user.profile.org)

    def get_serializer_class(self):
        if self.request.method == "PATCH":
            return ItemUpdateSerializer
        return ItemSerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["org"] = self.request.user.profile.org
        return ctx

    def update(self, request, *args, **kwargs):
        item = self.get_object()
        serializer = self.get_serializer(item, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        item = serializer.save()
        return Response(ItemSerializer(item).data)


class _ItemStatusView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated, IsItemWriter]
    serializer_class = EmptySerializer
    lookup_field = "slug"
    lookup_url_kwarg = "slug"
    queryset = Item.objects.all()
    service = None
    success_detail = ""

    def get_queryset(self):
        return Item.objects.filter(org=self.request.user.profile.org)

    def post(self, request, *args, **kwargs):
        slug = self.kwargs[self.lookup_url_kwarg]
        try:
            self.service(org=request.user.profile.org, slug=slug)
        except Item.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        except DjangoValidationError as exc:
            return Response(
                {"detail": _detail_from_validation_error(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({"detail": self.success_detail})


@extend_schema(
    tags=["Items"],
    summary="Suspend a catalog item",
    request=EmptySerializer,
    parameters=[_SLUG_PARAM],
    responses={
        200: detail_response("Item suspended.", "Suspended", {"detail": ITEM_SUSPENDED}),
        400: detail_response(
            "Already suspended.",
            "Already suspended",
            {"detail": ALREADY_SUSPENDED},
            status_code="400",
        ),
        404: _NOT_FOUND,
        **error_responses(401, 403),
    },
)
class ItemSuspendView(_ItemStatusView):
    service = staticmethod(suspend_item)
    success_detail = ITEM_SUSPENDED


@extend_schema(
    tags=["Items"],
    summary="Unsuspend a catalog item",
    request=EmptySerializer,
    parameters=[_SLUG_PARAM],
    responses={
        200: detail_response(
            "Item unsuspended.", "Unsuspended", {"detail": ITEM_UNSUSPENDED}
        ),
        400: detail_response(
            "Not suspended.",
            "Not suspended",
            {"detail": NOT_SUSPENDED},
            status_code="400",
        ),
        404: _NOT_FOUND,
        **error_responses(401, 403),
    },
)
class ItemUnsuspendView(_ItemStatusView):
    service = staticmethod(unsuspend_item)
    success_detail = ITEM_UNSUSPENDED
