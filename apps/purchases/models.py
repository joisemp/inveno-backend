"""
Purchase-flow models.

Public identifiers are slugs. Vendors are contact records, not users.
Line items stay on one PurchaseRequest and are awarded per vendor after quotes.
"""
from django.db import models

from apps.common.models import SlugMixin, UUIDModel


class PurchaseRequest(UUIDModel, SlugMixin):
    """A multi-line purchase request from a space or from operations."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        APPROVED = "approved", "Approved"
        REVISION_REQUESTED = "revision_requested", "Revision requested"
        DECLINED = "declined", "Declined"

    org = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="purchase_requests",
    )
    space = models.ForeignKey(
        "organizations.Space",
        on_delete=models.SET_NULL,
        related_name="purchase_requests",
        null=True,
        blank=True,
    )
    created_by = models.ForeignKey(
        "users.UserProfile",
        on_delete=models.PROTECT,
        related_name="purchase_requests",
    )
    title = models.CharField(max_length=255)
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    notes = models.TextField(blank=True)
    review_reason = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        "users.UserProfile",
        on_delete=models.SET_NULL,
        related_name="reviewed_purchase_requests",
        null=True,
        blank=True,
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Purchase request"
        verbose_name_plural = "Purchase requests"
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    def get_slug_source(self) -> str:
        return self.title

    @property
    def is_ops_raised(self) -> bool:
        from apps.users.models import UserProfile

        return self.created_by.user_type in UserProfile.PURCHASE_OPERATOR_TYPES


class PurchaseRequestLine(UUIDModel, SlugMixin):
    """One item row on a purchase request."""

    request = models.ForeignKey(
        PurchaseRequest,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    item = models.ForeignKey(
        "inventory.Item",
        on_delete=models.SET_NULL,
        related_name="purchase_request_lines",
        null=True,
        blank=True,
    )
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    unit = models.CharField(max_length=50)
    awarded_vendor = models.ForeignKey(
        "vendors.Vendor",
        on_delete=models.SET_NULL,
        related_name="awarded_request_lines",
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = "Purchase request line"
        verbose_name_plural = "Purchase request lines"
        ordering = ["description"]

    def get_slug_source(self) -> str:
        return f"{self.request.slug}-{self.description}"


class QuoteRequest(UUIDModel, SlugMixin):
    """RFQ record-keeping for an approved purchase request."""

    class Status(models.TextChoices):
        PREPARING = "preparing", "Preparing"
        IN_REVIEW = "in_review", "In review"
        AWARDING = "awarding", "Awarding"
        CANCELLED = "cancelled", "Cancelled"

    org = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="quote_requests",
    )
    purchase_request = models.ForeignKey(
        PurchaseRequest,
        on_delete=models.CASCADE,
        related_name="quote_requests",
    )
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.PREPARING,
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Quote request"
        verbose_name_plural = "Quote requests"
        ordering = ["-created_at"]

    def get_slug_source(self) -> str:
        return f"rfq-{self.purchase_request.slug}"


class QuoteRequestVendor(UUIDModel, SlugMixin):
    """A vendor record being considered on an RFQ."""

    class Status(models.TextChoices):
        INVITED = "invited", "Invited"
        QUOTED = "quoted", "Quoted"
        REJECTED = "rejected", "Rejected"
        AWARDED = "awarded", "Awarded"

    quote_request = models.ForeignKey(
        QuoteRequest,
        on_delete=models.CASCADE,
        related_name="vendors",
    )
    vendor = models.ForeignKey(
        "vendors.Vendor",
        on_delete=models.PROTECT,
        related_name="quote_request_vendors",
    )
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.INVITED,
    )
    reject_reason = models.TextField(blank=True)

    class Meta:
        verbose_name = "RFQ vendor"
        constraints = [
            models.UniqueConstraint(
                fields=["quote_request", "vendor"],
                name="purchases_rfq_vendor_uniq",
            ),
        ]

    def get_slug_source(self) -> str:
        return f"{self.quote_request.slug}-{self.vendor.slug}"


class VendorQuote(UUIDModel, SlugMixin):
    """Prices ops recorded from one vendor against an RFQ."""

    quote_request_vendor = models.OneToOneField(
        QuoteRequestVendor,
        on_delete=models.CASCADE,
        related_name="quote",
    )
    notes = models.TextField(blank=True)
    quoted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Vendor quote"

    def get_slug_source(self) -> str:
        return f"quote-{self.quote_request_vendor.slug}"


class VendorQuoteLine(UUIDModel, SlugMixin):
    """One recorded unit price for a request line from a vendor."""

    quote = models.ForeignKey(
        VendorQuote,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    request_line = models.ForeignKey(
        PurchaseRequestLine,
        on_delete=models.CASCADE,
        related_name="quotes",
    )
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        verbose_name = "Vendor quote line"
        constraints = [
            models.UniqueConstraint(
                fields=["quote", "request_line"],
                name="purchases_quote_line_uniq",
            ),
        ]

    def get_slug_source(self) -> str:
        return f"{self.quote.slug}-{self.request_line.slug}"


class PurchaseOrder(UUIDModel, SlugMixin):
    """One PO per winning vendor, covering only that vendor's awarded lines."""

    class Status(models.TextChoices):
        ISSUED = "issued", "Issued"
        QC_PENDING = "qc_pending", "QC pending"
        QC_FAILED = "qc_failed", "QC failed"
        RECEIVED = "received", "Received"
        INVOICED = "invoiced", "Invoiced"
        CANCELLED = "cancelled", "Cancelled"

    org = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="purchase_orders",
    )
    purchase_request = models.ForeignKey(
        PurchaseRequest,
        on_delete=models.CASCADE,
        related_name="purchase_orders",
    )
    vendor = models.ForeignKey(
        "vendors.Vendor",
        on_delete=models.PROTECT,
        related_name="purchase_orders",
    )
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.ISSUED,
    )
    is_new_order = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Purchase order"
        verbose_name_plural = "Purchase orders"
        ordering = ["-created_at"]

    def get_slug_source(self) -> str:
        return f"po-{self.purchase_request.slug}-{self.vendor.slug}"


class PurchaseOrderLine(UUIDModel, SlugMixin):
    """A PO line copied from an awarded request line."""

    purchase_order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    request_line = models.ForeignKey(
        PurchaseRequestLine,
        on_delete=models.PROTECT,
        related_name="po_lines",
    )
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    unit = models.CharField(max_length=50)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        verbose_name = "Purchase order line"

    def get_slug_source(self) -> str:
        return f"{self.purchase_order.slug}-{self.request_line.slug}"


class QualityCheck(UUIDModel, SlugMixin):
    """Delivery QC against one PO / vendor."""

    purchase_order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.CASCADE,
        related_name="quality_checks",
    )
    passed = models.BooleanField()
    reason = models.TextField(blank=True)
    next_action = models.CharField(max_length=32, blank=True)
    checked_by = models.ForeignKey(
        "users.UserProfile",
        on_delete=models.PROTECT,
        related_name="quality_checks",
    )
    checked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Quality check"
        ordering = ["-checked_at"]

    def get_slug_source(self) -> str:
        return f"qc-{self.purchase_order.slug}"


class PurchaseInvoice(UUIDModel, SlugMixin):
    """Internal record of an invoice forwarded for payment."""

    class Status(models.TextChoices):
        PENDING_PAYMENT = "pending_payment", "Pending payment"

    purchase_order = models.OneToOneField(
        PurchaseOrder,
        on_delete=models.CASCADE,
        related_name="invoice",
    )
    notes = models.TextField(blank=True)
    document_urls = models.JSONField(default=list, blank=True)
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.PENDING_PAYMENT,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Purchase invoice"

    def get_slug_source(self) -> str:
        return f"inv-{self.purchase_order.slug}"


class WarehouseReceipt(UUIDModel, SlugMixin):
    """Inbound handoff created when QC on a PO passes."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        COMPLETED = "completed", "Completed"

    org = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="warehouse_receipts",
    )
    purchase_order = models.OneToOneField(
        PurchaseOrder,
        on_delete=models.CASCADE,
        related_name="warehouse_receipt",
    )
    warehouse = models.ForeignKey(
        "inventory.Warehouse",
        on_delete=models.PROTECT,
        related_name="receipts",
        null=True,
        blank=True,
    )
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.PENDING,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Warehouse receipt"
        ordering = ["-created_at"]

    def get_slug_source(self) -> str:
        return f"recv-{self.purchase_order.slug}"


class WarehouseReceiptLine(UUIDModel, SlugMixin):
    """One inbound row; warehouse chooses new_item or add_to_existing."""

    receipt = models.ForeignKey(
        WarehouseReceipt,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    po_line = models.ForeignKey(
        PurchaseOrderLine,
        on_delete=models.PROTECT,
        related_name="receipt_lines",
    )
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    unit = models.CharField(max_length=50)
    item = models.ForeignKey(
        "inventory.Item",
        on_delete=models.SET_NULL,
        related_name="receipt_lines",
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = "Warehouse receipt line"

    def get_slug_source(self) -> str:
        return f"{self.receipt.slug}-{self.po_line.slug}"


class ProcessEvent(UUIDModel, SlugMixin):
    """Append-only hash-chained HMAC record of a purchase-flow movement."""

    org = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="process_events",
    )
    purchase_request = models.ForeignKey(
        PurchaseRequest,
        on_delete=models.CASCADE,
        related_name="process_events",
        null=True,
        blank=True,
    )
    resource_type = models.CharField(max_length=64)
    resource_slug = models.SlugField(max_length=255)
    action = models.CharField(max_length=64)
    actor_slug = models.SlugField(max_length=255)
    actor_user_type = models.CharField(max_length=32)
    payload = models.JSONField(default=dict)
    prev_hash = models.CharField(max_length=64)
    content_hash = models.CharField(max_length=64, db_index=True)
    signature = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Process event"
        ordering = ["created_at"]

    def get_slug_source(self) -> str:
        return self.content_hash
