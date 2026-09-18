"""Purchase-flow API views."""
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)
from rest_framework import generics, permissions, status
from rest_framework.negotiation import BaseContentNegotiation
from rest_framework.response import Response

from apps.common.openapi import EmptySerializer, DetailSerializer, detail_response, error_responses
from apps.inventory.models import Warehouse
from apps.inventory.services import get_org_warehouse
from apps.organizations.permissions import (
    IsCentralAdminOrOps,
    IsPurchaseRequester,
    IsWarehouseReceiver,
)
from apps.purchases.exports import export_document
from apps.purchases.models import (
    PurchaseOrder,
    PurchaseRequest,
    QuoteRequest,
    WarehouseReceipt,
)
from apps.purchases.serializers import (
    CreatePOSerializer,
    InvoiceWriteSerializer,
    ProcessEventSerializer,
    PurchaseInvoiceSerializer,
    PurchaseOrderSerializer,
    PurchaseRequestCreateSerializer,
    PurchaseRequestSerializer,
    PurchaseRequestUpdateSerializer,
    QualityCheckWriteSerializer,
    QuoteRequestSerializer,
    QuoteWriteSerializer,
    RFQCreateSerializer,
    ReasonSerializer,
    ReceiptCompleteSerializer,
    RejectVendorSerializer,
    SelectLinesSerializer,
    VendorSlugSerializer,
    VerifyEventResultSerializer,
    VerifyEventSerializer,
    WarehouseReceiptSerializer,
)
from apps.purchases.services import (
    add_rfq_vendor,
    approve_purchase_request,
    complete_warehouse_receipt,
    create_purchase_order,
    decline_purchase_request,
    get_org_po,
    get_org_pr,
    get_org_receipt,
    get_org_rfq,
    list_pr_trail,
    record_invoice,
    record_quality_check,
    record_vendor_quote,
    reject_rfq_vendor,
    request_pr_revision,
    request_rfq_revision,
    select_lines,
    submit_purchase_request,
    verify_process_event,
)
from apps.users.models import UserProfile

_SLUG = OpenApiParameter(
    name="slug",
    type=OpenApiTypes.STR,
    location=OpenApiParameter.PATH,
    description="Resource slug.",
)
_NOT_FOUND = detail_response(
    "Unknown slug or wrong organisation.",
    "Not found",
    {"detail": "Not found."},
    status_code="404",
)
_FORMAT = OpenApiParameter(
    name="format",
    type=OpenApiTypes.STR,
    location=OpenApiParameter.QUERY,
    required=True,
    enum=["pdf", "xlsx"],
)


def _err(exc: DjangoValidationError):
    if hasattr(exc, "message_dict"):
        data = {
            key: (val[0] if isinstance(val, list) and len(val) == 1 else val)
            for key, val in exc.message_dict.items()
        }
        return Response(data, status=status.HTTP_400_BAD_REQUEST)
    return Response({"detail": exc.messages[0]}, status=status.HTTP_400_BAD_REQUEST)


def _org_actor(request):
    return request.user.profile.org, request.user.profile


class PurchaseRequestListCreateView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated, IsPurchaseRequester]
    serializer_class = PurchaseRequestSerializer

    def get_queryset(self):
        profile = self.request.user.profile
        qs = (
            PurchaseRequest.objects.filter(org=profile.org)
            .select_related("space", "created_by")
            .prefetch_related("lines")
            .order_by("-created_at")
        )
        if profile.user_type == UserProfile.UserType.SPACE_INCHARGE:
            if not profile.space_id:
                return qs.none()
            return qs.filter(space=profile.space)
        return qs

    def get_serializer_class(self):
        if self.request.method == "POST":
            return PurchaseRequestCreateSerializer
        return PurchaseRequestSerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["org"] = self.request.user.profile.org
        ctx["actor"] = self.request.user.profile
        return ctx

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        pr = serializer.save()
        pr = PurchaseRequest.objects.prefetch_related("lines").get(pk=pr.pk)
        return Response(
            PurchaseRequestSerializer(pr).data, status=status.HTTP_201_CREATED
        )


@extend_schema_view(
    get=extend_schema(tags=["Purchases"], parameters=[_SLUG], responses={200: PurchaseRequestSerializer, 404: _NOT_FOUND, **error_responses(401, 403)}),
    patch=extend_schema(tags=["Purchases"], parameters=[_SLUG], request=PurchaseRequestUpdateSerializer, responses={200: PurchaseRequestSerializer, 400: OpenApiResponse(DetailSerializer), 404: _NOT_FOUND, **error_responses(401, 403)}),
)
class PurchaseRequestDetailView(generics.RetrieveUpdateAPIView):
    permission_classes = [permissions.IsAuthenticated, IsPurchaseRequester]
    serializer_class = PurchaseRequestSerializer
    lookup_field = "slug"
    http_method_names = ["get", "patch", "head", "options"]

    def get_queryset(self):
        return PurchaseRequestListCreateView.get_queryset(self)

    def get_serializer_class(self):
        if self.request.method == "PATCH":
            return PurchaseRequestUpdateSerializer
        return PurchaseRequestSerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["org"] = self.request.user.profile.org
        ctx["actor"] = self.request.user.profile
        return ctx

    def update(self, request, *args, **kwargs):
        pr = self.get_object()
        serializer = self.get_serializer(pr, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        pr = serializer.save()
        pr = PurchaseRequest.objects.prefetch_related("lines").get(pk=pr.pk)
        return Response(PurchaseRequestSerializer(pr).data)


class _PRActionView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated, IsCentralAdminOrOps]
    lookup_field = "slug"
    serializer_class = EmptySerializer

    def get_queryset(self):
        return PurchaseRequest.objects.filter(org=self.request.user.profile.org)


@extend_schema(tags=["Purchases"], parameters=[_SLUG], request=EmptySerializer, responses={200: PurchaseRequestSerializer, 400: OpenApiResponse(DetailSerializer), 404: _NOT_FOUND, **error_responses(401, 403)})
class PurchaseRequestSubmitView(_PRActionView):
    permission_classes = [permissions.IsAuthenticated, IsPurchaseRequester]

    def post(self, request, *args, **kwargs):
        pr = self.get_object()
        profile = request.user.profile
        if profile.user_type == UserProfile.UserType.SPACE_INCHARGE:
            if pr.created_by_id != profile.pk:
                raise Http404()
        try:
            pr = submit_purchase_request(pr=pr, actor=profile)
        except DjangoValidationError as exc:
            return _err(exc)
        return Response(PurchaseRequestSerializer(pr).data)


@extend_schema(tags=["Purchases"], parameters=[_SLUG], request=EmptySerializer, responses={200: PurchaseRequestSerializer, 400: OpenApiResponse(DetailSerializer), 404: _NOT_FOUND, **error_responses(401, 403)})
class PurchaseRequestApproveView(_PRActionView):
    def post(self, request, *args, **kwargs):
        try:
            pr = approve_purchase_request(pr=self.get_object(), actor=request.user.profile)
        except DjangoValidationError as exc:
            return _err(exc)
        return Response(PurchaseRequestSerializer(pr).data)


@extend_schema(tags=["Purchases"], parameters=[_SLUG], request=ReasonSerializer, responses={200: PurchaseRequestSerializer, 400: OpenApiResponse(DetailSerializer), 404: _NOT_FOUND, **error_responses(401, 403)})
class PurchaseRequestDeclineView(_PRActionView):
    serializer_class = ReasonSerializer

    def post(self, request, *args, **kwargs):
        ser = ReasonSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            pr = decline_purchase_request(
                pr=self.get_object(), actor=request.user.profile, reason=ser.validated_data["reason"]
            )
        except DjangoValidationError as exc:
            return _err(exc)
        return Response(PurchaseRequestSerializer(pr).data)


@extend_schema(tags=["Purchases"], parameters=[_SLUG], request=ReasonSerializer, responses={200: PurchaseRequestSerializer, 400: OpenApiResponse(DetailSerializer), 404: _NOT_FOUND, **error_responses(401, 403)})
class PurchaseRequestRevisionView(_PRActionView):
    serializer_class = ReasonSerializer

    def post(self, request, *args, **kwargs):
        ser = ReasonSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            pr = request_pr_revision(
                pr=self.get_object(), actor=request.user.profile, reason=ser.validated_data["reason"]
            )
        except DjangoValidationError as exc:
            return _err(exc)
        return Response(PurchaseRequestSerializer(pr).data)


@extend_schema(tags=["Purchases"], parameters=[_SLUG], responses={200: ProcessEventSerializer(many=True), 404: _NOT_FOUND, **error_responses(401, 403)})
class PurchaseRequestTrailView(_PRActionView):
    def get(self, request, *args, **kwargs):
        pr = self.get_object()
        return Response(ProcessEventSerializer(list_pr_trail(pr=pr), many=True).data)


@extend_schema_view(
    get=extend_schema(tags=["Purchases"], responses={200: QuoteRequestSerializer, **error_responses(401, 403)}),
    post=extend_schema(tags=["Purchases"], request=RFQCreateSerializer, responses={201: QuoteRequestSerializer, 400: OpenApiResponse(DetailSerializer), **error_responses(401, 403)}),
)
class RFQListCreateView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated, IsCentralAdminOrOps]
    serializer_class = QuoteRequestSerializer

    def get_queryset(self):
        return (
            QuoteRequest.objects.filter(org=self.request.user.profile.org)
            .select_related("purchase_request")
            .prefetch_related("vendors__vendor", "purchase_request__lines")
            .order_by("-created_at")
        )

    def get_serializer_class(self):
        if self.request.method == "POST":
            return RFQCreateSerializer
        return QuoteRequestSerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["org"] = self.request.user.profile.org
        ctx["actor"] = self.request.user.profile
        return ctx

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        rfq = serializer.save()
        rfq = self.get_queryset().get(pk=rfq.pk)
        return Response(QuoteRequestSerializer(rfq).data, status=status.HTTP_201_CREATED)


@extend_schema(tags=["Purchases"], parameters=[_SLUG], responses={200: QuoteRequestSerializer, 404: _NOT_FOUND, **error_responses(401, 403)})
class RFQDetailView(generics.RetrieveAPIView):
    permission_classes = [permissions.IsAuthenticated, IsCentralAdminOrOps]
    serializer_class = QuoteRequestSerializer
    lookup_field = "slug"

    def get_queryset(self):
        return RFQListCreateView.get_queryset(self)


class _RFQActionView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated, IsCentralAdminOrOps]
    lookup_field = "slug"
    serializer_class = EmptySerializer

    def get_queryset(self):
        return QuoteRequest.objects.filter(org=self.request.user.profile.org)


@extend_schema(tags=["Purchases"], parameters=[_SLUG], request=VendorSlugSerializer, responses={200: QuoteRequestSerializer, 400: OpenApiResponse(DetailSerializer), 404: _NOT_FOUND, **error_responses(401, 403)})
class RFQAddVendorView(_RFQActionView):
    serializer_class = VendorSlugSerializer

    def post(self, request, *args, **kwargs):
        rfq = self.get_object()
        ser = VendorSlugSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            add_rfq_vendor(rfq=rfq, actor=request.user.profile, vendor_slug=ser.validated_data["vendor"])
        except DjangoValidationError as exc:
            return _err(exc)
        rfq = QuoteRequest.objects.prefetch_related("vendors__vendor", "purchase_request__lines").get(pk=rfq.pk)
        return Response(QuoteRequestSerializer(rfq).data)


@extend_schema(tags=["Purchases"], parameters=[_SLUG, OpenApiParameter("vendor_slug", OpenApiTypes.STR, OpenApiParameter.PATH)], request=RejectVendorSerializer, responses={200: QuoteRequestSerializer, 400: OpenApiResponse(DetailSerializer), 404: _NOT_FOUND, **error_responses(401, 403)})
class RFQRejectVendorView(_RFQActionView):
    serializer_class = RejectVendorSerializer

    def post(self, request, *args, **kwargs):
        rfq = self.get_object()
        ser = RejectVendorSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            reject_rfq_vendor(
                rfq=rfq,
                actor=request.user.profile,
                vendor_slug=self.kwargs["vendor_slug"],
                reason=ser.validated_data["reason"],
            )
        except DjangoValidationError as exc:
            return _err(exc)
        rfq = QuoteRequest.objects.prefetch_related("vendors__vendor", "purchase_request__lines").get(pk=rfq.pk)
        return Response(QuoteRequestSerializer(rfq).data)


@extend_schema(tags=["Purchases"], parameters=[_SLUG], request=QuoteWriteSerializer, responses={200: QuoteRequestSerializer, 400: OpenApiResponse(DetailSerializer), 404: _NOT_FOUND, **error_responses(401, 403)})
class RFQQuoteView(_RFQActionView):
    serializer_class = QuoteWriteSerializer

    def post(self, request, *args, **kwargs):
        rfq = self.get_object()
        ser = QuoteWriteSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            record_vendor_quote(
                rfq=rfq,
                actor=request.user.profile,
                vendor_slug=ser.validated_data["vendor"],
                lines=ser.validated_data["lines"],
                notes=ser.validated_data.get("notes") or "",
            )
        except DjangoValidationError as exc:
            return _err(exc)
        rfq = QuoteRequest.objects.prefetch_related("vendors__vendor", "purchase_request__lines").get(pk=rfq.pk)
        return Response(QuoteRequestSerializer(rfq).data)


@extend_schema(tags=["Purchases"], parameters=[_SLUG], request=EmptySerializer, responses={200: QuoteRequestSerializer, 404: _NOT_FOUND, **error_responses(401, 403)})
class RFQRevisionView(_RFQActionView):
    def post(self, request, *args, **kwargs):
        rfq = request_rfq_revision(rfq=self.get_object(), actor=request.user.profile)
        return Response(QuoteRequestSerializer(rfq).data)


@extend_schema(tags=["Purchases"], parameters=[_SLUG], request=SelectLinesSerializer, responses={200: QuoteRequestSerializer, 400: OpenApiResponse(DetailSerializer), 404: _NOT_FOUND, **error_responses(401, 403)})
class RFQSelectLinesView(_RFQActionView):
    serializer_class = SelectLinesSerializer

    def post(self, request, *args, **kwargs):
        rfq = self.get_object()
        ser = SelectLinesSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            select_lines(rfq=rfq, actor=request.user.profile, selections=ser.validated_data["selections"])
        except DjangoValidationError as exc:
            return _err(exc)
        rfq = QuoteRequest.objects.prefetch_related("vendors__vendor", "purchase_request__lines").get(pk=rfq.pk)
        return Response(QuoteRequestSerializer(rfq).data)


@extend_schema(tags=["Purchases"], parameters=[_SLUG], request=CreatePOSerializer, responses={201: PurchaseOrderSerializer, 400: OpenApiResponse(DetailSerializer), 404: _NOT_FOUND, **error_responses(401, 403)})
class RFQCreatePOView(_RFQActionView):
    serializer_class = CreatePOSerializer

    def post(self, request, *args, **kwargs):
        rfq = self.get_object()
        ser = CreatePOSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            po = create_purchase_order(
                rfq=rfq,
                actor=request.user.profile,
                vendor_slug=ser.validated_data["vendor"],
                create_purchase_order=ser.validated_data["create_purchase_order"],
            )
        except DjangoValidationError as exc:
            return _err(exc)
        po = PurchaseOrder.objects.prefetch_related("lines").get(pk=po.pk)
        return Response(PurchaseOrderSerializer(po).data, status=status.HTTP_201_CREATED)


@extend_schema(tags=["Purchases"], responses={200: PurchaseOrderSerializer, **error_responses(401, 403)})
class PurchaseOrderListView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated, IsCentralAdminOrOps]
    serializer_class = PurchaseOrderSerializer

    def get_queryset(self):
        return (
            PurchaseOrder.objects.filter(org=self.request.user.profile.org)
            .select_related("vendor", "purchase_request")
            .prefetch_related("lines")
            .order_by("-created_at")
        )


@extend_schema(tags=["Purchases"], parameters=[_SLUG], responses={200: PurchaseOrderSerializer, 404: _NOT_FOUND, **error_responses(401, 403)})
class PurchaseOrderDetailView(generics.RetrieveAPIView):
    permission_classes = [permissions.IsAuthenticated, IsCentralAdminOrOps]
    serializer_class = PurchaseOrderSerializer
    lookup_field = "slug"

    def get_queryset(self):
        return PurchaseOrderListView.get_queryset(self)


class _POActionView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated, IsCentralAdminOrOps]
    lookup_field = "slug"
    serializer_class = EmptySerializer

    def get_queryset(self):
        return PurchaseOrder.objects.filter(org=self.request.user.profile.org)


@extend_schema(tags=["Purchases"], parameters=[_SLUG], request=QualityCheckWriteSerializer, responses={200: PurchaseOrderSerializer, 400: OpenApiResponse(DetailSerializer), 404: _NOT_FOUND, **error_responses(401, 403)})
class PurchaseOrderQCView(_POActionView):
    serializer_class = QualityCheckWriteSerializer

    def post(self, request, *args, **kwargs):
        po = self.get_object()
        ser = QualityCheckWriteSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            record_quality_check(
                po=po,
                actor=request.user.profile,
                passed=ser.validated_data["passed"],
                reason=ser.validated_data.get("reason") or "",
                next_action=ser.validated_data.get("next") or "",
            )
        except DjangoValidationError as exc:
            return _err(exc)
        po = PurchaseOrder.objects.prefetch_related("lines").get(pk=po.pk)
        return Response(PurchaseOrderSerializer(po).data)


@extend_schema(tags=["Purchases"], parameters=[_SLUG], request=InvoiceWriteSerializer, responses={200: PurchaseInvoiceSerializer, 400: OpenApiResponse(DetailSerializer), 404: _NOT_FOUND, **error_responses(401, 403)})
class PurchaseOrderInvoiceView(_POActionView):
    serializer_class = InvoiceWriteSerializer

    def post(self, request, *args, **kwargs):
        po = self.get_object()
        ser = InvoiceWriteSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            invoice = record_invoice(
                po=po,
                actor=request.user.profile,
                notes=ser.validated_data.get("notes") or "",
                document_urls=ser.validated_data.get("document_urls") or [],
            )
        except DjangoValidationError as exc:
            return _err(exc)
        return Response(PurchaseInvoiceSerializer(invoice).data)


_RECEIPT_PREFETCH = (
    "lines__po_line__request_line__item",
)


@extend_schema_view(
    get=extend_schema(
        tags=["Purchases"],
        responses={200: WarehouseReceiptSerializer, **error_responses(401, 403)},
    ),
)
class WarehouseReceiptListView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated, IsWarehouseReceiver]
    serializer_class = WarehouseReceiptSerializer

    def get_queryset(self):
        qs = (
            WarehouseReceipt.objects.filter(org=self.request.user.profile.org)
            .select_related("purchase_order", "warehouse")
            .prefetch_related(*_RECEIPT_PREFETCH)
            .order_by("-created_at")
        )
        status_filter = self.request.query_params.get("status")
        if status_filter == "pending":
            return qs.filter(status=WarehouseReceipt.Status.PENDING)
        if status_filter == "completed":
            return qs.filter(status=WarehouseReceipt.Status.COMPLETED)
        return qs


_EXAMPLE_PENDING_RECEIPT = {
    "slug": "recv-po-split-buy-acme-supplies",
    "purchase_order": "po-split-buy-acme-supplies",
    "warehouse": "warehouse",
    "status": "pending",
    "lines": [
        {
            "slug": "recv-po-a4-paper",
            "description": "A4 paper",
            "quantity": "10.000",
            "unit": "ream",
            "item": None,
            "source_item": "a4-paper",
            "suggested_items": [
                {
                    "slug": "a4-paper",
                    "name": "A4 paper",
                    "part_number": "PAP-A4",
                    "unit": "ream",
                    "quantity_on_hand": "3.000",
                }
            ],
        }
    ],
    "created_at": "2026-09-18T10:00:00Z",
    "completed_at": None,
}


@extend_schema(
    tags=["Purchases"],
    parameters=[_SLUG],
    responses={
        200: WarehouseReceiptSerializer,
        404: _NOT_FOUND,
        **error_responses(401, 403),
    },
    examples=[
        OpenApiExample(
            "Pending receipt with catalog match",
            value=_EXAMPLE_PENDING_RECEIPT,
            response_only=True,
            status_codes=["200"],
        )
    ],
)
class WarehouseReceiptDetailView(generics.RetrieveAPIView):
    permission_classes = [permissions.IsAuthenticated, IsWarehouseReceiver]
    serializer_class = WarehouseReceiptSerializer
    lookup_field = "slug"

    def get_queryset(self):
        return (
            WarehouseReceipt.objects.filter(org=self.request.user.profile.org)
            .select_related("purchase_order", "warehouse")
            .prefetch_related(*_RECEIPT_PREFETCH)
        )


@extend_schema(tags=["Purchases"], parameters=[_SLUG], request=ReceiptCompleteSerializer, responses={200: WarehouseReceiptSerializer, 400: OpenApiResponse(DetailSerializer), 404: _NOT_FOUND, **error_responses(401, 403)})
class WarehouseReceiptCompleteView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated, IsWarehouseReceiver]
    serializer_class = ReceiptCompleteSerializer
    lookup_field = "slug"

    def get_queryset(self):
        return WarehouseReceipt.objects.filter(org=self.request.user.profile.org)

    def post(self, request, *args, **kwargs):
        receipt = self.get_object()
        ser = ReceiptCompleteSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        warehouse = None
        warehouse_slug = ser.validated_data.get("warehouse") or ""
        if warehouse_slug:
            try:
                warehouse = get_org_warehouse(org=receipt.org, slug=warehouse_slug)
            except Warehouse.DoesNotExist:
                return Response(
                    {"warehouse": "Unknown warehouse."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        try:
            receipt = complete_warehouse_receipt(
                receipt=receipt,
                actor=request.user.profile,
                lines=ser.validated_data["lines"],
                warehouse=warehouse,
            )
        except DjangoValidationError as exc:
            return _err(exc)
        receipt = WarehouseReceipt.objects.prefetch_related(*_RECEIPT_PREFETCH).get(
            pk=receipt.pk
        )
        return Response(WarehouseReceiptSerializer(receipt).data)


@extend_schema(
    tags=["Purchases"],
    request=VerifyEventSerializer,
    responses={200: VerifyEventResultSerializer, **error_responses(401, 403)},
)
class ProcessEventVerifyView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated, IsCentralAdminOrOps]
    serializer_class = VerifyEventSerializer

    def post(self, request, *args, **kwargs):
        ser = VerifyEventSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        valid = verify_process_event(
            content_hash=ser.validated_data["content_hash"],
            signature=ser.validated_data["signature"],
        )
        return Response({"valid": valid})


class _PassthroughNegotiation(BaseContentNegotiation):
    """Ignore ?format= so pdf/xlsx are not treated as DRF renderer suffixes."""

    def select_parser(self, request, parsers):
        return parsers[0]

    def select_renderer(self, request, renderers, format_suffix):
        return (renderers[0], renderers[0].media_type)


class _ExportMixin:
    """GET ?format=pdf|xlsx attachment."""

    export_kind = ""
    content_negotiation_class = _PassthroughNegotiation

    def get_export_object(self):
        return self.get_object()

    def get(self, request, *args, **kwargs):
        fmt = request.query_params.get("format")
        if fmt not in ("pdf", "xlsx"):
            return Response(
                {"format": ['Must be "pdf" or "xlsx".']},
                status=status.HTTP_400_BAD_REQUEST,
            )
        obj = self.get_export_object()
        return export_document(kind=self.export_kind, obj=obj, fmt=fmt)


@extend_schema(tags=["Purchases"], parameters=[_SLUG, _FORMAT], responses={200: OpenApiResponse(description="File download."), 400: OpenApiResponse(DetailSerializer), 404: _NOT_FOUND, **error_responses(401, 403)})
class PurchaseRequestExportView(_ExportMixin, generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated, IsPurchaseRequester]
    lookup_field = "slug"
    serializer_class = EmptySerializer
    export_kind = "purchase_request"

    def get_queryset(self):
        return PurchaseRequestListCreateView.get_queryset(self)


@extend_schema(tags=["Purchases"], parameters=[_SLUG, _FORMAT], responses={200: OpenApiResponse(description="File download."), 400: OpenApiResponse(DetailSerializer), 404: _NOT_FOUND, **error_responses(401, 403)})
class RFQExportView(_ExportMixin, generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated, IsCentralAdminOrOps]
    lookup_field = "slug"
    serializer_class = EmptySerializer
    export_kind = "rfq"

    def get_queryset(self):
        return QuoteRequest.objects.filter(org=self.request.user.profile.org)


@extend_schema(tags=["Purchases"], parameters=[_SLUG, _FORMAT], responses={200: OpenApiResponse(description="File download."), 400: OpenApiResponse(DetailSerializer), 404: _NOT_FOUND, **error_responses(401, 403)})
class PurchaseOrderExportView(_ExportMixin, generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated, IsCentralAdminOrOps]
    lookup_field = "slug"
    serializer_class = EmptySerializer
    export_kind = "purchase_order"

    def get_queryset(self):
        return PurchaseOrder.objects.filter(org=self.request.user.profile.org)


@extend_schema(tags=["Purchases"], parameters=[_SLUG, _FORMAT], responses={200: OpenApiResponse(description="File download."), 400: OpenApiResponse(DetailSerializer), 404: _NOT_FOUND, **error_responses(401, 403)})
class InvoiceExportView(_ExportMixin, generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated, IsCentralAdminOrOps]
    lookup_field = "slug"
    serializer_class = EmptySerializer
    export_kind = "invoice"

    def get_queryset(self):
        return PurchaseOrder.objects.filter(org=self.request.user.profile.org)

    def get_export_object(self):
        po = self.get_object()
        if not hasattr(po, "invoice"):
            raise Http404()
        return po.invoice


@extend_schema(tags=["Purchases"], parameters=[_SLUG, _FORMAT], responses={200: OpenApiResponse(description="File download."), 400: OpenApiResponse(DetailSerializer), 404: _NOT_FOUND, **error_responses(401, 403)})
class WarehouseReceiptExportView(_ExportMixin, generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated, IsWarehouseReceiver]
    lookup_field = "slug"
    serializer_class = EmptySerializer
    export_kind = "warehouse_receipt"

    def get_queryset(self):
        return WarehouseReceipt.objects.filter(org=self.request.user.profile.org)


# Bind list/create schema
PurchaseRequestListCreateView = extend_schema_view(
    get=extend_schema(tags=["Purchases"], responses={200: PurchaseRequestSerializer, **error_responses(401, 403)}),
    post=extend_schema(
        tags=["Purchases"],
        request=PurchaseRequestCreateSerializer,
        responses={201: PurchaseRequestSerializer, 400: OpenApiResponse(DetailSerializer), **error_responses(401, 403)},
    ),
)(PurchaseRequestListCreateView)
