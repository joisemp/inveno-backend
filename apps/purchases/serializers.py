"""Public serializers for the purchase flow. Slugs only, never UUID."""
from decimal import Decimal

from rest_framework import serializers

from apps.purchases.models import (
    ProcessEvent,
    PurchaseInvoice,
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseRequest,
    PurchaseRequestLine,
    QuoteRequest,
    QuoteRequestVendor,
    VendorQuoteLine,
    WarehouseReceipt,
    WarehouseReceiptLine,
)
from apps.purchases.services import (
    create_purchase_request,
    create_rfq,
    receipt_source_item,
    suggest_receipt_line_items,
    update_purchase_request,
)
from django.core.exceptions import ValidationError as DjangoValidationError


def _raise(exc: DjangoValidationError):
    if hasattr(exc, "message_dict"):
        raise serializers.ValidationError(exc.message_dict) from exc
    raise serializers.ValidationError(exc.messages) from exc


class LineAwardSerializer(serializers.Serializer):
    """Compact vendor + quantity for a single award row on a request line."""

    vendor = serializers.CharField()
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3)


class PurchaseRequestLineSerializer(serializers.ModelSerializer):
    item = serializers.SlugRelatedField(read_only=True, slug_field="slug")
    awarded_vendor = serializers.SlugRelatedField(read_only=True, slug_field="slug")
    awards = serializers.SerializerMethodField()
    quantity_remaining = serializers.SerializerMethodField()

    class Meta:
        model = PurchaseRequestLine
        fields = (
            "slug",
            "description",
            "quantity",
            "unit",
            "item",
            "awarded_vendor",
            "awards",
            "quantity_remaining",
        )
        read_only_fields = fields

    def get_awards(self, obj):
        return [
            {"vendor": a.vendor.slug, "quantity": str(a.quantity)}
            for a in obj.awards.select_related("vendor").all()
        ]

    def get_quantity_remaining(self, obj):
        total = sum(a.quantity for a in obj.awards.all())
        return str(obj.quantity - total)


class LineWriteSerializer(serializers.Serializer):
    description = serializers.CharField(max_length=255)
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3)
    unit = serializers.CharField(max_length=50)
    item = serializers.SlugField(required=False, allow_blank=True, default="")


class PurchaseRequestSerializer(serializers.ModelSerializer):
    space = serializers.SlugRelatedField(read_only=True, slug_field="slug")
    created_by = serializers.SlugRelatedField(read_only=True, slug_field="slug")
    created_by_user_type = serializers.CharField(
        source="created_by.user_type", read_only=True
    )
    active_rfq = serializers.SerializerMethodField()
    lines = PurchaseRequestLineSerializer(many=True, read_only=True)

    class Meta:
        model = PurchaseRequest
        fields = (
            "slug",
            "title",
            "status",
            "notes",
            "space",
            "created_by",
            "created_by_user_type",
            "review_reason",
            "active_rfq",
            "lines",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_active_rfq(self, obj):
        """Slug of the newest non-cancelled RFQ, or null if none."""
        from apps.purchases.models import QuoteRequest

        if hasattr(obj, "active_quote_requests"):
            rows = obj.active_quote_requests
            return rows[0].slug if rows else None
        rfq = (
            obj.quote_requests.exclude(status=QuoteRequest.Status.CANCELLED)
            .order_by("-created_at", "-id")
            .first()
        )
        return rfq.slug if rfq else None


class PurchaseRequestCreateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255)
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    space = serializers.SlugField(required=False, allow_null=True, allow_blank=True)
    lines = LineWriteSerializer(many=True)

    def create(self, validated_data):
        space = validated_data.get("space") or None
        if space == "":
            space = None
        try:
            return create_purchase_request(
                org=self.context["org"],
                actor=self.context["actor"],
                title=validated_data["title"],
                notes=validated_data.get("notes") or "",
                space=space,
                lines=validated_data["lines"],
            )
        except DjangoValidationError as exc:
            _raise(exc)


class PurchaseRequestUpdateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255, required=False)
    notes = serializers.CharField(required=False, allow_blank=True)
    lines = LineWriteSerializer(many=True, required=False)

    def update(self, instance, validated_data):
        try:
            return update_purchase_request(
                pr=instance,
                actor=self.context["actor"],
                **validated_data,
            )
        except DjangoValidationError as exc:
            _raise(exc)


class ReasonSerializer(serializers.Serializer):
    reason = serializers.CharField()


class QuoteLineSerializer(serializers.Serializer):
    vendor = serializers.CharField()
    unit_price = serializers.DecimalField(max_digits=12, decimal_places=2)


class RFQLineSerializer(serializers.Serializer):
    slug = serializers.CharField()
    description = serializers.CharField()
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3)
    unit = serializers.CharField()
    awarded_vendor = serializers.CharField(allow_null=True)
    awards = LineAwardSerializer(many=True)
    quantity_remaining = serializers.DecimalField(max_digits=12, decimal_places=3)
    quotes = QuoteLineSerializer(many=True)


class RFQVendorSerializer(serializers.ModelSerializer):
    vendor = serializers.SlugRelatedField(read_only=True, slug_field="slug")

    class Meta:
        model = QuoteRequestVendor
        fields = ("vendor", "status", "reject_reason")
        read_only_fields = fields


class QuoteRequestSerializer(serializers.ModelSerializer):
    purchase_request = serializers.SlugRelatedField(read_only=True, slug_field="slug")
    vendors = RFQVendorSerializer(many=True, read_only=True)
    lines = serializers.SerializerMethodField()

    class Meta:
        model = QuoteRequest
        fields = (
            "slug",
            "purchase_request",
            "status",
            "notes",
            "vendors",
            "lines",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_lines(self, obj):
        result = []
        for line in obj.purchase_request.lines.all():
            quotes = VendorQuoteLine.objects.filter(request_line=line).select_related(
                "quote__quote_request_vendor__vendor"
            )
            awards_qs = list(line.awards.select_related("vendor").all())
            total_awarded = sum(a.quantity for a in awards_qs)
            result.append(
                {
                    "slug": line.slug,
                    "description": line.description,
                    "quantity": line.quantity,
                    "unit": line.unit,
                    "awarded_vendor": (
                        line.awarded_vendor.slug if line.awarded_vendor_id else None
                    ),
                    "awards": [
                        {"vendor": a.vendor.slug, "quantity": a.quantity}
                        for a in awards_qs
                    ],
                    "quantity_remaining": line.quantity - total_awarded,
                    "quotes": [
                        {
                            "vendor": q.quote.quote_request_vendor.vendor.slug,
                            "unit_price": q.unit_price,
                        }
                        for q in quotes
                    ],
                }
            )
        return result


class RFQCreateSerializer(serializers.Serializer):
    purchase_request = serializers.SlugField()
    vendor_slugs = serializers.ListField(child=serializers.SlugField(), allow_empty=False)

    def create(self, validated_data):
        try:
            return create_rfq(
                org=self.context["org"],
                actor=self.context["actor"],
                **validated_data,
            )
        except DjangoValidationError as exc:
            _raise(exc)


class VendorSlugSerializer(serializers.Serializer):
    vendor = serializers.SlugField()


class RejectVendorSerializer(serializers.Serializer):
    reason = serializers.CharField()


class QuoteWriteSerializer(serializers.Serializer):
    vendor = serializers.SlugField()
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    lines = serializers.ListField(child=serializers.DictField(), allow_empty=False)


class SelectionSerializer(serializers.Serializer):
    line = serializers.SlugField()
    vendor = serializers.SlugField()
    quantity = serializers.DecimalField(
        max_digits=12,
        decimal_places=3,
        required=False,
        allow_null=True,
        min_value=Decimal("0.001"),
    )


class SelectLinesSerializer(serializers.Serializer):
    selections = SelectionSerializer(many=True)


class SetAwardSerializer(serializers.Serializer):
    """Replace quantity on an existing unplaced award."""

    line = serializers.SlugField()
    vendor = serializers.SlugField()
    quantity = serializers.DecimalField(
        max_digits=12,
        decimal_places=3,
        min_value=Decimal("0.001"),
    )


class ClearAwardSerializer(serializers.Serializer):
    """Remove an unplaced award for a line + vendor."""

    line = serializers.SlugField()
    vendor = serializers.SlugField()


class CreatePOSerializer(serializers.Serializer):
    vendor = serializers.SlugField()
    create_purchase_order = serializers.BooleanField(default=True)


class POLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = PurchaseOrderLine
        fields = ("slug", "description", "quantity", "unit", "unit_price")
        read_only_fields = fields


class PurchaseOrderSerializer(serializers.ModelSerializer):
    vendor = serializers.SlugRelatedField(read_only=True, slug_field="slug")
    purchase_request = serializers.SlugRelatedField(read_only=True, slug_field="slug")
    lines = POLineSerializer(many=True, read_only=True)

    class Meta:
        model = PurchaseOrder
        fields = (
            "slug",
            "vendor",
            "purchase_request",
            "status",
            "is_new_order",
            "lines",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class QualityCheckWriteSerializer(serializers.Serializer):
    passed = serializers.BooleanField()
    reason = serializers.CharField(required=False, allow_blank=True, default="")
    next = serializers.ChoiceField(
        choices=["return", "reorder_same", "choose_vendors"],
        required=False,
        allow_blank=True,
        default="",
    )


class InvoiceWriteSerializer(serializers.Serializer):
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    document_urls = serializers.ListField(
        child=serializers.URLField(), required=False, default=list
    )


class PurchaseInvoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = PurchaseInvoice
        fields = ("slug", "notes", "document_urls", "status", "created_at")
        read_only_fields = fields


class ReceiptSuggestedItemSerializer(serializers.Serializer):
    """Catalog row the UI can offer when prompting add-to-existing vs new item."""

    slug = serializers.SlugField()
    name = serializers.CharField()
    part_number = serializers.CharField()
    unit = serializers.CharField()
    quantity_on_hand = serializers.DecimalField(max_digits=12, decimal_places=3)


class ReceiptLineSerializer(serializers.ModelSerializer):
    item = serializers.SlugRelatedField(read_only=True, slug_field="slug")
    source_item = serializers.SerializerMethodField()
    suggested_items = serializers.SerializerMethodField()

    class Meta:
        model = WarehouseReceiptLine
        fields = (
            "slug",
            "description",
            "quantity",
            "unit",
            "item",
            "source_item",
            "suggested_items",
        )
        read_only_fields = fields

    def get_source_item(self, obj) -> str | None:
        item = receipt_source_item(line=obj)
        return item.slug if item is not None else None

    def get_suggested_items(self, obj):
        return ReceiptSuggestedItemSerializer(
            suggest_receipt_line_items(line=obj), many=True
        ).data


class WarehouseReceiptSerializer(serializers.ModelSerializer):
    purchase_order = serializers.SlugRelatedField(read_only=True, slug_field="slug")
    warehouse = serializers.SlugRelatedField(read_only=True, slug_field="slug")
    lines = ReceiptLineSerializer(many=True, read_only=True)

    class Meta:
        model = WarehouseReceipt
        fields = (
            "slug",
            "purchase_order",
            "warehouse",
            "status",
            "lines",
            "created_at",
            "completed_at",
        )
        read_only_fields = fields


class ReceiptCompleteLineSerializer(serializers.Serializer):
    line = serializers.SlugField()
    action = serializers.ChoiceField(choices=["new_item", "add_to_existing"])
    item = serializers.SlugField(required=False, allow_blank=True)
    name = serializers.CharField(required=False, allow_blank=True)
    part_number = serializers.CharField(required=False, allow_blank=True)
    unit = serializers.CharField(required=False, allow_blank=True)


class ReceiptCompleteSerializer(serializers.Serializer):
    warehouse = serializers.SlugField(required=False, allow_blank=True)
    lines = ReceiptCompleteLineSerializer(many=True)


class ProcessEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProcessEvent
        fields = (
            "slug",
            "action",
            "actor_slug",
            "actor_user_type",
            "resource_type",
            "resource_slug",
            "content_hash",
            "signature",
            "prev_hash",
            "created_at",
        )
        read_only_fields = fields


class VerifyEventSerializer(serializers.Serializer):
    content_hash = serializers.CharField()
    signature = serializers.CharField()


class VerifyEventResultSerializer(serializers.Serializer):
    """HMAC check result for a process-event hash."""

    valid = serializers.BooleanField()
