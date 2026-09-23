"""API views for the org item catalog and photos."""
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
from apps.inventory.models import Item, ItemActivity, ItemPhoto, Warehouse
from apps.inventory.serializers import (
    ItemActivityDetailSerializer,
    ItemActivitySerializer,
    ItemCreateSerializer,
    ItemPhotoCreateSerializer,
    ItemPhotoSerializer,
    ItemSerializer,
    ItemStockAdjustSerializer,
    ItemUpdateSerializer,
)
from apps.inventory.services import (
    ALREADY_SUSPENDED,
    INSUFFICIENT_STOCK,
    ITEM_SUSPENDED,
    ITEM_UNSUSPENDED,
    NOT_SUSPENDED,
    PHOTO_LIMIT,
    STOCK_ACTION_INVALID,
    STOCK_QTY_POSITIVE,
    STOCK_REASON_REQUIRED,
    add_item_photo,
    delete_item_photo,
    suspend_item,
    unsuspend_item,
)
from apps.organizations.permissions import IsItemReader, IsItemWriter

ITEM_STATUS_VALUES = ("active", "suspended")
INVALID_STATUS = 'Must be "active" or "suspended".'
UNKNOWN_WAREHOUSE = "Unknown warehouse."
ACTIVITY_KIND_VALUES = (
    ItemActivity.Kind.INCOMING,
    ItemActivity.Kind.OUTGOING,
    ItemActivity.Kind.ITEM_EDIT,
)
INVALID_KIND = 'Must be "incoming", "outgoing", or "item_edit".'


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


_EXAMPLE_PHOTO = {
    "slug": "aisle-bin",
    "url": "http://localhost:8000/media/items/2026/09/aisle-bin.webp",
}

_EXAMPLE_ITEM = {
    "slug": "a4-paper",
    "warehouse": "warehouse",
    "name": "A4 paper",
    "description": "80gsm copier paper",
    "part_number": "PAP-A4",
    "alternate_part_number": "",
    "unit": "ream",
    "category": "stationery",
    "location": "Aisle 2 / Bin 4",
    "remarks": "",
    "quantity_on_hand": "0.000",
    "balance_in_stock": "0.000",
    "last_purchase_date": None,
    "last_purchase_quantity": None,
    "photos": [_EXAMPLE_PHOTO],
    "is_active": True,
    "created_at": "2026-09-17T10:00:00Z",
    "updated_at": "2026-09-17T10:00:00Z",
}

_EXAMPLE_ITEM_CREATE = {
    "warehouse": "warehouse",
    "name": "A4 paper",
    "unit": "ream",
    "description": "80gsm copier paper",
    "part_number": "PAP-A4",
    "alternate_part_number": "",
    "category": "stationery",
    "location": "Aisle 2 / Bin 4",
    "remarks": "",
}

_EXAMPLE_ITEM_UPDATE = {
    "warehouse": "warehouse",
    "name": "A4 copier paper",
    "unit": "ream",
    "description": "80gsm copier paper",
    "part_number": "PAP-A4",
    "alternate_part_number": "PAP-A4-ALT",
    "category": "stationery",
    "location": "Aisle 3 / Bin 1",
    "remarks": "Keep dry",
    "last_purchase_date": "2026-09-18",
    "last_purchase_quantity": "10.000",
}

_EXAMPLE_ITEM_AFTER_STOCK = {
    **_EXAMPLE_ITEM,
    "quantity_on_hand": "12.000",
    "balance_in_stock": "12.000",
    "updated_at": "2026-09-22T10:00:00Z",
}

_EXAMPLE_RECORDED_BY = {
    "slug": "jefin-james",
    "full_name": "Jefin James",
    "user_type": "warehouse_manager",
}

_EXAMPLE_ACTIVITY_ADDED = {
    "slug": "a4-paper-added",
    "kind": "incoming",
    "action": "added",
    "previous_quantity": "0.000",
    "quantity": "12.000",
    "delta": "12.000",
    "recorded_on": "2026-09-22T10:00:00Z",
    "recorded_by": _EXAMPLE_RECORDED_BY,
    "remarks": "Opening balance",
    "reference": {"type": "item_activity", "slug": "a4-paper-added"},
}

_EXAMPLE_ACTIVITY_REMOVED = {
    "slug": "a4-paper-removed",
    "kind": "outgoing",
    "action": "removed",
    "previous_quantity": "12.000",
    "quantity": "10.000",
    "delta": "-2.000",
    "recorded_on": "2026-09-22T10:05:00Z",
    "recorded_by": _EXAMPLE_RECORDED_BY,
    "remarks": "Damaged",
    "reference": {"type": "item_activity", "slug": "a4-paper-removed"},
}

_EXAMPLE_ACTIVITY_CREATED = {
    "slug": "a4-paper-created",
    "kind": "item_edit",
    "action": "created",
    "previous_quantity": None,
    "quantity": None,
    "delta": None,
    "recorded_on": "2026-09-22T09:55:00Z",
    "recorded_by": _EXAMPLE_RECORDED_BY,
    "remarks": "Item created",
    "reference": {"type": "item_activity", "slug": "a4-paper-created"},
}

_EXAMPLE_ACTIVITY_DETAIL_ADDED = {
    **_EXAMPLE_ACTIVITY_ADDED,
    "payload": {
        "action": "add",
        "amount": "12.000",
        "previous_quantity": "0.000",
        "quantity": "12.000",
        "reason": "Opening balance",
    },
}

_EXAMPLE_ACTIVITY_DETAIL_REMOVED = {
    **_EXAMPLE_ACTIVITY_REMOVED,
    "payload": {
        "action": "remove",
        "amount": "2.000",
        "previous_quantity": "12.000",
        "quantity": "10.000",
        "reason": "Damaged",
    },
}

_EXAMPLE_ACTIVITY_DETAIL_CREATED = {
    **_EXAMPLE_ACTIVITY_CREATED,
    "payload": {
        "warehouse": "warehouse",
        "name": "A4 paper",
        "unit": "ream",
        "description": "80gsm copier paper",
        "part_number": "PAP-A4",
        "alternate_part_number": "",
        "category": "stationery",
        "location": "Aisle 2 / Bin 4",
        "remarks": "",
    },
}

_EXAMPLE_ACTIVITY_DETAIL_UPDATED = {
    "slug": "a4-paper-updated",
    "kind": "item_edit",
    "action": "updated",
    "previous_quantity": None,
    "quantity": None,
    "delta": None,
    "recorded_on": "2026-09-22T10:10:00Z",
    "recorded_by": _EXAMPLE_RECORDED_BY,
    "remarks": "Item updated",
    "reference": {"type": "item_activity", "slug": "a4-paper-updated"},
    "payload": {
        "changes": {
            "name": {"from": "A4 paper", "to": "A4 copier paper"},
            "location": {"from": "Aisle 2 / Bin 4", "to": "Aisle 3 / Bin 1"},
        }
    },
}

_EXAMPLE_ACTIVITY_DETAIL_RECEIVED = {
    "slug": "a4-paper-received",
    "kind": "incoming",
    "action": "received",
    "previous_quantity": "10.000",
    "quantity": "20.000",
    "delta": "10.000",
    "recorded_on": "2026-09-22T11:00:00Z",
    "recorded_by": _EXAMPLE_RECORDED_BY,
    "remarks": "Warehouse receipt recv-po-a4-paper",
    "reference": {"type": "warehouse_receipt", "slug": "recv-po-a4-paper"},
    "payload": {
        "amount": "10.000",
        "previous_quantity": "10.000",
        "quantity": "20.000",
        "receipt": "recv-po-a4-paper",
        "line": "a4-receipt-line",
    },
}

_EXAMPLE_ACTIVITY_DETAIL_SUSPENDED = {
    "slug": "a4-paper-suspended",
    "kind": "item_edit",
    "action": "suspended",
    "previous_quantity": None,
    "quantity": None,
    "delta": None,
    "recorded_on": "2026-09-22T12:00:00Z",
    "recorded_by": _EXAMPLE_RECORDED_BY,
    "remarks": "Item suspended",
    "reference": {"type": "item_activity", "slug": "a4-paper-suspended"},
    "payload": {
        "is_active": {"from": True, "to": False},
        "actor": _EXAMPLE_RECORDED_BY,
    },
}

_EXAMPLE_ACTIVITY_DETAIL_PHOTO = {
    "slug": "a4-paper-photo-added",
    "kind": "item_edit",
    "action": "photo_added",
    "previous_quantity": None,
    "quantity": None,
    "delta": None,
    "recorded_on": "2026-09-22T10:15:00Z",
    "recorded_by": _EXAMPLE_RECORDED_BY,
    "remarks": "Photo added",
    "reference": {"type": "item_activity", "slug": "a4-paper-photo-added"},
    "payload": {"photo": "aisle-bin"},
}

_EXAMPLE_ACTIVITY_DETAIL_PHOTO_DELETED = {
    "slug": "a4-paper-photo-deleted",
    "kind": "item_edit",
    "action": "photo_deleted",
    "previous_quantity": None,
    "quantity": None,
    "delta": None,
    "recorded_on": "2026-09-22T10:16:00Z",
    "recorded_by": _EXAMPLE_RECORDED_BY,
    "remarks": "Photo deleted",
    "reference": {"type": "item_activity", "slug": "a4-paper-photo-deleted"},
    "payload": {"photo": "aisle-bin"},
}

_EXAMPLE_ACTIVITY_DETAIL_UNSUSPENDED = {
    "slug": "a4-paper-unsuspended",
    "kind": "item_edit",
    "action": "unsuspended",
    "previous_quantity": None,
    "quantity": None,
    "delta": None,
    "recorded_on": "2026-09-22T12:05:00Z",
    "recorded_by": _EXAMPLE_RECORDED_BY,
    "remarks": "Item unsuspended",
    "reference": {"type": "item_activity", "slug": "a4-paper-unsuspended"},
    "payload": {
        "is_active": {"from": False, "to": True},
        "actor": _EXAMPLE_RECORDED_BY,
    },
}

_EXAMPLE_ACTIVITY_LIST = {
    "count": 3,
    "next": None,
    "previous": None,
    "results": [
        _EXAMPLE_ACTIVITY_REMOVED,
        _EXAMPLE_ACTIVITY_ADDED,
        _EXAMPLE_ACTIVITY_CREATED,
    ],
}

_EXAMPLE_ITEM_LIST = {
    "count": 1,
    "next": None,
    "previous": None,
    "results": [_EXAMPLE_ITEM],
}

_SLUG_PARAM = OpenApiParameter(
    name="slug",
    type=OpenApiTypes.STR,
    location=OpenApiParameter.PATH,
    description="Item slug.",
)

_PHOTO_SLUG_PARAM = OpenApiParameter(
    name="photo_slug",
    type=OpenApiTypes.STR,
    location=OpenApiParameter.PATH,
    description="Photo slug.",
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
            ),
            OpenApiParameter(
                name="warehouse",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Filter by warehouse slug.",
            ),
        ],
        responses={
            200: OpenApiResponse(
                response=ItemSerializer(many=True),
                description="Paginated item list. Every item field is included.",
                examples=[
                    OpenApiExample(
                        "Item list",
                        value=_EXAMPLE_ITEM_LIST,
                        response_only=True,
                        status_codes=["200"],
                    )
                ],
            ),
            400: field_error_response(
                OpenApiExample(
                    "Invalid status",
                    value={"status": [INVALID_STATUS]},
                    response_only=True,
                    status_codes=["400"],
                ),
                OpenApiExample(
                    "Unknown warehouse",
                    value={"warehouse": [UNKNOWN_WAREHOUSE]},
                    response_only=True,
                    status_codes=["400"],
                ),
            ),
            **error_responses(401, 403),
        },
    ),
    post=extend_schema(
        tags=["Items"],
        summary="Create a catalog item",
        request=ItemCreateSerializer,
        examples=[
            OpenApiExample(
                "Create item (all fields)",
                value=_EXAMPLE_ITEM_CREATE,
                request_only=True,
            )
        ],
        responses={
            201: OpenApiResponse(
                response=ItemSerializer,
                description="Created item. Stock starts at 0. No id.",
                examples=[
                    OpenApiExample(
                        "Created item",
                        value={**_EXAMPLE_ITEM, "photos": []},
                        response_only=True,
                        status_codes=["201"],
                    )
                ],
            ),
            400: field_error_response(
                OpenApiExample(
                    "Duplicate name",
                    value={"name": ["An item with this name already exists."]},
                    response_only=True,
                    status_codes=["400"],
                ),
                OpenApiExample(
                    "Warehouse required",
                    value={"warehouse": ["This field is required."]},
                    response_only=True,
                    status_codes=["400"],
                ),
                OpenApiExample(
                    "Unknown warehouse",
                    value={"warehouse": ["Unknown warehouse."]},
                    response_only=True,
                    status_codes=["400"],
                ),
            ),
            **error_responses(401, 403),
        },
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
        org = self.request.user.profile.org
        qs = (
            Item.objects.filter(org=org)
            .select_related("warehouse", "category")
            .prefetch_related("photos")
            .order_by("name")
        )
        item_status = self.request.query_params.get("status")
        if item_status == "active":
            qs = qs.filter(is_active=True)
        elif item_status == "suspended":
            qs = qs.filter(is_active=False)
        warehouse_slug = self.request.query_params.get("warehouse")
        if warehouse_slug:
            qs = qs.filter(warehouse__slug=warehouse_slug)
        return qs

    def list(self, request, *args, **kwargs):
        item_status = request.query_params.get("status")
        if item_status is not None and item_status not in ITEM_STATUS_VALUES:
            return Response(
                {"status": [INVALID_STATUS]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        warehouse_slug = request.query_params.get("warehouse")
        if warehouse_slug:
            org = request.user.profile.org
            if not Warehouse.objects.filter(org=org, slug=warehouse_slug).exists():
                return Response(
                    {"warehouse": [UNKNOWN_WAREHOUSE]},
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
        ctx["actor"] = self.request.user.profile
        return ctx

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = serializer.save()
        return Response(
            ItemSerializer(item, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )


@extend_schema_view(
    get=extend_schema(
        tags=["Items"],
        summary="Get a catalog item",
        parameters=[_SLUG_PARAM],
        responses={
            200: OpenApiResponse(
                response=ItemSerializer,
                description="Full item object. No id.",
                examples=[
                    OpenApiExample(
                        "Item",
                        value=_EXAMPLE_ITEM,
                        response_only=True,
                        status_codes=["200"],
                    )
                ],
            ),
            404: _NOT_FOUND,
            **error_responses(401, 403),
        },
    ),
    patch=extend_schema(
        tags=["Items"],
        summary="Update a catalog item",
        parameters=[_SLUG_PARAM],
        request=ItemUpdateSerializer,
        examples=[
            OpenApiExample(
                "Update item (all writable fields)",
                value=_EXAMPLE_ITEM_UPDATE,
                request_only=True,
            )
        ],
        responses={
            200: OpenApiResponse(
                response=ItemSerializer,
                description="Updated item. quantity_on_hand is unchanged.",
                examples=[
                    OpenApiExample(
                        "Updated item",
                        value={
                            **_EXAMPLE_ITEM,
                            "name": "A4 copier paper",
                            "alternate_part_number": "PAP-A4-ALT",
                            "location": "Aisle 3 / Bin 1",
                            "remarks": "Keep dry",
                            "last_purchase_date": "2026-09-18",
                            "last_purchase_quantity": "10.000",
                        },
                        response_only=True,
                        status_codes=["200"],
                    )
                ],
            ),
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
        return (
            Item.objects.filter(org=self.request.user.profile.org)
            .select_related("warehouse", "category")
            .prefetch_related("photos")
        )

    def get_serializer_class(self):
        if self.request.method == "PATCH":
            return ItemUpdateSerializer
        return ItemSerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["org"] = self.request.user.profile.org
        ctx["actor"] = self.request.user.profile
        return ctx

    def update(self, request, *args, **kwargs):
        item = self.get_object()
        serializer = self.get_serializer(item, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        item = serializer.save()
        return Response(ItemSerializer(item, context=self.get_serializer_context()).data)


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
            self.service(
                org=request.user.profile.org,
                slug=slug,
                actor=request.user.profile,
            )
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


@extend_schema(
    tags=["Items"],
    summary="Upload an item photo",
    parameters=[_SLUG_PARAM],
    request=ItemPhotoCreateSerializer,
    examples=[
        OpenApiExample(
            "Uploaded photo",
            value=_EXAMPLE_PHOTO,
            response_only=True,
            status_codes=["201"],
        )
    ],
    responses={
        201: OpenApiResponse(
            response=ItemPhotoSerializer,
            description="Stored photo. JPEG/PNG/GIF/WebP in; WebP out.",
            examples=[
                OpenApiExample(
                    "Uploaded photo",
                    value=_EXAMPLE_PHOTO,
                    response_only=True,
                    status_codes=["201"],
                )
            ],
        ),
        400: field_error_response(
            OpenApiExample(
                "Photo limit",
                value={"detail": PHOTO_LIMIT},
                response_only=True,
                status_codes=["400"],
            ),
            OpenApiExample(
                "Invalid image",
                value={"image": ["Upload a valid image."]},
                response_only=True,
                status_codes=["400"],
            ),
        ),
        404: _NOT_FOUND,
        **error_responses(401, 403),
    },
)
class ItemPhotoCreateView(generics.GenericAPIView):
    """Multipart photo upload. Stored as WebP; maximum five per item."""

    permission_classes = [permissions.IsAuthenticated, IsItemWriter]
    serializer_class = ItemPhotoCreateSerializer
    lookup_field = "slug"
    lookup_url_kwarg = "slug"

    def get_queryset(self):
        return Item.objects.filter(org=self.request.user.profile.org)

    def post(self, request, *args, **kwargs):
        item = self.get_object()
        serializer = self.get_serializer(
            data=request.data,
            context={
                "item": item,
                "request": request,
                "actor": request.user.profile,
            },
        )
        serializer.is_valid(raise_exception=True)
        try:
            photo = add_item_photo(
                item=item,
                uploaded_file=serializer.validated_data["image"],
                actor=request.user.profile,
            )
        except DjangoValidationError as exc:
            return Response(
                {"detail": _detail_from_validation_error(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            ItemPhotoSerializer(photo, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


@extend_schema(
    tags=["Items"],
    summary="Delete an item photo",
    parameters=[_SLUG_PARAM, _PHOTO_SLUG_PARAM],
    request=EmptySerializer,
    responses={
        204: OpenApiResponse(description="Photo deleted."),
        404: _NOT_FOUND,
        **error_responses(401, 403),
    },
)
class ItemPhotoDeleteView(generics.GenericAPIView):
    """Delete one photo from an item."""

    permission_classes = [permissions.IsAuthenticated, IsItemWriter]
    serializer_class = EmptySerializer
    lookup_field = "slug"
    lookup_url_kwarg = "slug"

    def get_queryset(self):
        return Item.objects.filter(org=self.request.user.profile.org)

    def delete(self, request, *args, **kwargs):
        item = self.get_object()
        photo_slug = kwargs["photo_slug"]
        try:
            delete_item_photo(
                item=item, photo_slug=photo_slug, actor=request.user.profile
            )
        except ItemPhoto.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)


_ACTIVITY_SLUG_PARAM = OpenApiParameter(
    name="activity_slug",
    type=OpenApiTypes.STR,
    location=OpenApiParameter.PATH,
    description="Item activity slug.",
)


@extend_schema(
    tags=["Items"],
    summary="Add or remove item stock",
    parameters=[_SLUG_PARAM],
    request=ItemStockAdjustSerializer,
    examples=[
        OpenApiExample(
            "Add stock",
            value={
                "action": "add",
                "quantity": "12.000",
                "reason": "Opening balance",
            },
            request_only=True,
        ),
        OpenApiExample(
            "Remove stock",
            value={"action": "remove", "quantity": "2.000", "reason": "Damaged"},
            request_only=True,
        ),
    ],
    responses={
        200: OpenApiResponse(
            response=ItemSerializer,
            description="Item after the stock change. All item fields. No id.",
            examples=[
                OpenApiExample(
                    "After add",
                    value=_EXAMPLE_ITEM_AFTER_STOCK,
                    response_only=True,
                    status_codes=["200"],
                )
            ],
        ),
        400: field_error_response(
            OpenApiExample(
                "Insufficient stock",
                value={"quantity": [INSUFFICIENT_STOCK]},
                response_only=True,
                status_codes=["400"],
            ),
            OpenApiExample(
                "Reason required",
                value={"reason": [STOCK_REASON_REQUIRED]},
                response_only=True,
                status_codes=["400"],
            ),
            OpenApiExample(
                "Invalid action",
                value={"action": [STOCK_ACTION_INVALID]},
                response_only=True,
                status_codes=["400"],
            ),
            OpenApiExample(
                "Quantity not positive",
                value={"quantity": [STOCK_QTY_POSITIVE]},
                response_only=True,
                status_codes=["400"],
            ),
        ),
        404: _NOT_FOUND,
        **error_responses(401, 403),
    },
)
class ItemStockAdjustView(generics.GenericAPIView):
    """Add or remove a positive quantity. Does not stamp last-purchase."""

    permission_classes = [permissions.IsAuthenticated, IsItemWriter]
    serializer_class = ItemStockAdjustSerializer
    lookup_field = "slug"
    lookup_url_kwarg = "slug"

    def get_queryset(self):
        return Item.objects.filter(org=self.request.user.profile.org)

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["item"] = self.get_object()
        ctx["actor"] = self.request.user.profile
        return ctx

    def post(self, request, *args, **kwargs):
        item = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = serializer.save()
        return Response(ItemSerializer(item, context=self.get_serializer_context()).data)


@extend_schema(
    tags=["Items"],
    summary="List item activity",
    parameters=[
        _SLUG_PARAM,
        OpenApiParameter(
            name="kind",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            required=False,
            enum=list(ACTIVITY_KIND_VALUES),
        ),
    ],
    responses={
        200: OpenApiResponse(
            response=ItemActivitySerializer(many=True),
            description="Paginated history. Each row includes every list field.",
            examples=[
                OpenApiExample(
                    "Activity list",
                    value=_EXAMPLE_ACTIVITY_LIST,
                    response_only=True,
                    status_codes=["200"],
                )
            ],
        ),
        400: field_error_response(
            OpenApiExample(
                "Invalid kind",
                value={"kind": [INVALID_KIND]},
                response_only=True,
                status_codes=["400"],
            ),
        ),
        404: _NOT_FOUND,
        **error_responses(401, 403),
    },
)
class ItemActivityListView(generics.ListAPIView):
    """Paginated history for one item, newest first."""

    permission_classes = [permissions.IsAuthenticated, IsItemReader]
    serializer_class = ItemActivitySerializer
    lookup_field = "slug"
    lookup_url_kwarg = "slug"

    def get_item(self):
        return generics.get_object_or_404(
            Item.objects.filter(org=self.request.user.profile.org),
            slug=self.kwargs["slug"],
        )

    def get_queryset(self):
        item = self.get_item()
        return ItemActivity.objects.filter(item=item).order_by("-created_at")

    def list(self, request, *args, **kwargs):
        kind = request.query_params.get("kind")
        if kind is not None and kind not in ACTIVITY_KIND_VALUES:
            return Response(
                {"kind": [INVALID_KIND]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        self.get_item()
        qs = self.get_queryset()
        if kind:
            qs = qs.filter(kind=kind)
        page = self.paginate_queryset(qs)
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data)


@extend_schema(
    tags=["Items"],
    summary="Get item activity details",
    parameters=[_SLUG_PARAM, _ACTIVITY_SLUG_PARAM],
    responses={
        200: OpenApiResponse(
            response=ItemActivityDetailSerializer,
            description="Activity row plus payload. Examples cover each action.",
            examples=[
                OpenApiExample(
                    "Created",
                    value=_EXAMPLE_ACTIVITY_DETAIL_CREATED,
                    response_only=True,
                    status_codes=["200"],
                ),
                OpenApiExample(
                    "Updated",
                    value=_EXAMPLE_ACTIVITY_DETAIL_UPDATED,
                    response_only=True,
                    status_codes=["200"],
                ),
                OpenApiExample(
                    "Stock added",
                    value=_EXAMPLE_ACTIVITY_DETAIL_ADDED,
                    response_only=True,
                    status_codes=["200"],
                ),
                OpenApiExample(
                    "Stock removed",
                    value=_EXAMPLE_ACTIVITY_DETAIL_REMOVED,
                    response_only=True,
                    status_codes=["200"],
                ),
                OpenApiExample(
                    "Warehouse receipt",
                    value=_EXAMPLE_ACTIVITY_DETAIL_RECEIVED,
                    response_only=True,
                    status_codes=["200"],
                ),
                OpenApiExample(
                    "Suspended",
                    value=_EXAMPLE_ACTIVITY_DETAIL_SUSPENDED,
                    response_only=True,
                    status_codes=["200"],
                ),
                OpenApiExample(
                    "Photo added",
                    value=_EXAMPLE_ACTIVITY_DETAIL_PHOTO,
                    response_only=True,
                    status_codes=["200"],
                ),
                OpenApiExample(
                    "Photo deleted",
                    value=_EXAMPLE_ACTIVITY_DETAIL_PHOTO_DELETED,
                    response_only=True,
                    status_codes=["200"],
                ),
                OpenApiExample(
                    "Unsuspended",
                    value=_EXAMPLE_ACTIVITY_DETAIL_UNSUSPENDED,
                    response_only=True,
                    status_codes=["200"],
                ),
            ],
        ),
        404: _NOT_FOUND,
        **error_responses(401, 403),
    },
)
class ItemActivityDetailView(generics.RetrieveAPIView):
    """One activity row plus payload. Identified by item and activity slugs."""

    permission_classes = [permissions.IsAuthenticated, IsItemReader]
    serializer_class = ItemActivityDetailSerializer
    lookup_field = "slug"
    lookup_url_kwarg = "activity_slug"

    def get_queryset(self):
        return ItemActivity.objects.filter(
            org=self.request.user.profile.org,
            item__slug=self.kwargs["slug"],
        )
