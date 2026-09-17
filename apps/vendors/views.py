"""
API views for organisation vendors.

VendorListCreateView     GET/POST /api/orgs/vendors/
VendorRetrieveUpdateView GET/PATCH /api/orgs/vendors/{slug}/
VendorSuspendView        POST /api/orgs/vendors/{slug}/suspend/
VendorUnsuspendView      POST /api/orgs/vendors/{slug}/unsuspend/

Central admins and warehouse managers of an active org.  Identified by slug.
"""
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
from apps.organizations.permissions import IsVendorManager
from apps.vendors.models import Vendor
from apps.vendors.serializers import (
    VendorCreateSerializer,
    VendorSerializer,
    VendorUpdateSerializer,
)
from apps.vendors.services import (
    ALREADY_SUSPENDED,
    DUPLICATE_NAME,
    NOT_SUSPENDED,
    VENDOR_SUSPENDED,
    VENDOR_UNSUSPENDED,
    suspend_vendor,
    unsuspend_vendor,
)

VENDOR_STATUS_VALUES = ("active", "suspended")
INVALID_STATUS = 'Must be "active" or "suspended".'


def field_error_response(*examples):
    """OpenAPI 400 body for serializer field errors."""
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


_EXAMPLE_VENDOR = {
    "slug": "acme-supplies",
    "name": "Acme Supplies",
    "contact_name": "Jane Doe",
    "phone": "+15551234",
    "email": "jane@acme.com",
    "address": "12 Warehouse Rd",
    "gst": "22AAAAA0000A1Z5",
    "website": "https://acme.example",
    "is_active": True,
    "created_at": "2026-09-16T10:00:00Z",
    "updated_at": "2026-09-16T10:00:00Z",
}

_SLUG_PARAM = OpenApiParameter(
    name="slug",
    type=OpenApiTypes.STR,
    location=OpenApiParameter.PATH,
    description="Vendor slug.",
)

_NOT_FOUND = detail_response(
    "Unknown slug or vendor belongs to another organisation.",
    "Not found",
    {"detail": "Not found."},
    status_code="404",
)


@extend_schema_view(
    get=extend_schema(
        tags=["Vendors"],
        summary="List vendors",
        parameters=[
            OpenApiParameter(
                name="status",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=False,
                enum=list(VENDOR_STATUS_VALUES),
                description=(
                    "Filter by status. Omit to return all vendors. "
                    "Use `suspended` for inactive vendors."
                ),
            )
        ],
        responses={
            200: VendorSerializer(many=True),
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
        examples=[
            OpenApiExample(
                "Vendor list item",
                value=_EXAMPLE_VENDOR,
                response_only=True,
                status_codes=["200"],
            )
        ],
    ),
    post=extend_schema(
        tags=["Vendors"],
        summary="Add a vendor",
        request=VendorCreateSerializer,
        responses={
            201: OpenApiResponse(
                response=VendorSerializer,
                description="Vendor created.",
                examples=[
                    OpenApiExample(
                        "Created",
                        value=_EXAMPLE_VENDOR,
                        response_only=True,
                        status_codes=["201"],
                    )
                ],
            ),
            400: field_error_response(
                OpenApiExample(
                    "Duplicate name",
                    value={"name": [DUPLICATE_NAME]},
                    response_only=True,
                    status_codes=["400"],
                )
            ),
            **error_responses(401, 403),
        },
    ),
)
class VendorListCreateView(generics.ListCreateAPIView):
    """List vendors in the caller's org, or create one."""

    permission_classes = [permissions.IsAuthenticated, IsVendorManager]
    serializer_class = VendorSerializer

    def get_queryset(self):
        qs = Vendor.objects.filter(org=self.request.user.profile.org).order_by("name")
        vendor_status = self.request.query_params.get("status")
        if vendor_status == "active":
            return qs.filter(is_active=True)
        if vendor_status == "suspended":
            return qs.filter(is_active=False)
        return qs

    def list(self, request, *args, **kwargs):
        vendor_status = request.query_params.get("status")
        if vendor_status is not None and vendor_status not in VENDOR_STATUS_VALUES:
            return Response(
                {"status": [INVALID_STATUS]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().list(request, *args, **kwargs)

    def get_serializer_class(self):
        if self.request.method == "POST":
            return VendorCreateSerializer
        return VendorSerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["org"] = self.request.user.profile.org
        return ctx

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vendor = serializer.save()
        return Response(VendorSerializer(vendor).data, status=status.HTTP_201_CREATED)


@extend_schema_view(
    get=extend_schema(
        tags=["Vendors"],
        summary="Get a vendor",
        parameters=[_SLUG_PARAM],
        responses={
            200: OpenApiResponse(
                response=VendorSerializer,
                description="Vendor.",
                examples=[
                    OpenApiExample(
                        "Vendor",
                        value=_EXAMPLE_VENDOR,
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
        tags=["Vendors"],
        summary="Update a vendor",
        parameters=[_SLUG_PARAM],
        request=VendorUpdateSerializer,
        responses={
            200: OpenApiResponse(
                response=VendorSerializer,
                description="Updated vendor.",
                examples=[
                    OpenApiExample(
                        "Updated",
                        value=_EXAMPLE_VENDOR,
                        response_only=True,
                        status_codes=["200"],
                    )
                ],
            ),
            400: field_error_response(
                OpenApiExample(
                    "Duplicate name",
                    value={"name": [DUPLICATE_NAME]},
                    response_only=True,
                    status_codes=["400"],
                )
            ),
            404: _NOT_FOUND,
            **error_responses(401, 403),
        },
    ),
)
class VendorRetrieveUpdateView(generics.RetrieveUpdateAPIView):
    """Retrieve or partially update a vendor by slug."""

    permission_classes = [permissions.IsAuthenticated, IsVendorManager]
    serializer_class = VendorSerializer
    lookup_field = "slug"
    lookup_url_kwarg = "slug"
    http_method_names = ["get", "patch", "head", "options"]

    def get_queryset(self):
        return Vendor.objects.filter(org=self.request.user.profile.org)

    def get_serializer_class(self):
        if self.request.method == "PATCH":
            return VendorUpdateSerializer
        return VendorSerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["org"] = self.request.user.profile.org
        return ctx

    def update(self, request, *args, **kwargs):
        vendor = self.get_object()
        serializer = self.get_serializer(vendor, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        vendor = serializer.save()
        return Response(VendorSerializer(vendor).data)


class _VendorStatusView(generics.GenericAPIView):
    """Shared POST-by-slug machinery for suspend / unsuspend."""

    permission_classes = [permissions.IsAuthenticated, IsVendorManager]
    serializer_class = EmptySerializer
    lookup_field = "slug"
    lookup_url_kwarg = "slug"
    queryset = Vendor.objects.all()
    service = None
    success_detail = ""

    def get_queryset(self):
        return Vendor.objects.filter(org=self.request.user.profile.org)

    def post(self, request, *args, **kwargs):
        slug = self.kwargs[self.lookup_url_kwarg]
        try:
            self.service(org=request.user.profile.org, slug=slug)
        except Vendor.DoesNotExist:
            return Response(
                {"detail": "Not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        except DjangoValidationError as exc:
            return Response(
                {"detail": _detail_from_validation_error(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({"detail": self.success_detail})


@extend_schema(
    tags=["Vendors"],
    summary="Suspend a vendor",
    request=EmptySerializer,
    parameters=[_SLUG_PARAM],
    responses={
        200: detail_response(
            "Vendor suspended.",
            "Suspended",
            {"detail": VENDOR_SUSPENDED},
        ),
        400: detail_response(
            "Vendor is already suspended.",
            "Already suspended",
            {"detail": ALREADY_SUSPENDED},
            status_code="400",
        ),
        404: _NOT_FOUND,
        **error_responses(401, 403),
    },
)
class VendorSuspendView(_VendorStatusView):
    """Set is_active=False."""

    service = staticmethod(suspend_vendor)
    success_detail = VENDOR_SUSPENDED


@extend_schema(
    tags=["Vendors"],
    summary="Unsuspend a vendor",
    request=EmptySerializer,
    parameters=[_SLUG_PARAM],
    responses={
        200: detail_response(
            "Vendor unsuspended.",
            "Unsuspended",
            {"detail": VENDOR_UNSUSPENDED},
        ),
        400: detail_response(
            "Vendor is not suspended.",
            "Not suspended",
            {"detail": NOT_SUSPENDED},
            status_code="400",
        ),
        404: _NOT_FOUND,
        **error_responses(401, 403),
    },
)
class VendorUnsuspendView(_VendorStatusView):
    """Set is_active=True."""

    service = staticmethod(unsuspend_vendor)
    success_detail = VENDOR_UNSUSPENDED
