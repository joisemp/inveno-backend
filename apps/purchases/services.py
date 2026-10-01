"""
Purchase-flow business rules.

Views call these functions. Every mutating function records a process event
in the same atomic transaction.
"""
import logging
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.inventory.models import Item
from apps.inventory.services import (
    WAREHOUSE_REQUIRED,
    create_item,
    default_receipt_warehouse,
    increment_stock,
)
from apps.organizations.models import Organization, Space
from apps.purchases.models import (
    ProcessEvent,
    PurchaseInvoice,
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseRequest,
    PurchaseRequestLine,
    QualityCheck,
    QuoteRequest,
    QuoteRequestVendor,
    VendorQuote,
    VendorQuoteLine,
    WarehouseReceipt,
    WarehouseReceiptLine,
)
from apps.purchases.signing import record_process_event, verify_signature
from apps.users.models import UserProfile
from apps.vendors.models import Vendor

logger = logging.getLogger(__name__)

NO_LINES = "A purchase request must include at least one line."
NOT_ASSIGNED_TO_SPACE = "Assign this space incharge to a space before creating a request."
SPACE_INACTIVE = "This space is suspended."
SPACE_REQUIRED = "Space incharges cannot omit a space."
CANNOT_SET_SPACE = "Space incharges cannot choose a different space."
INVALID_STATUS = "This action is not allowed in the current status."
REASON_REQUIRED = "A reason is required."
NEED_VENDORS = "Choose at least one existing active vendor, or add vendors first."
VENDOR_INACTIVE = "This vendor is not active."
VENDOR_NOT_ON_RFQ = "This vendor is not on the quote request."
LINE_ALREADY_AWARDED = "This line is already awarded."
NO_QUOTE_FOR_LINE = "This vendor has no recorded quote for that line."
NO_AWARDED_LINES = "This vendor has no awarded lines."
RECEIPT_NOT_PENDING = "This receipt is already completed."
ALL_LINES_REQUIRED = "Every receipt line must be included."
ITEM_REQUIRED = "An existing item slug is required to add to stock."
ITEM_WRONG_WAREHOUSE = "This item is not in the receipt warehouse."
UNKNOWN_ACTION = "Action must be new_item or add_to_existing."
PR_NOT_APPROVED = "The purchase request must be approved first."
SUGGESTED_ITEM_LIMIT = 5


def _actor_payload(profile: UserProfile) -> dict:
    return {"slug": profile.slug, "user_type": profile.user_type}


def get_org_pr(*, org: Organization, slug: str) -> PurchaseRequest:
    return PurchaseRequest.objects.select_related("space", "created_by").get(
        org=org, slug=slug
    )


def get_org_rfq(*, org: Organization, slug: str) -> QuoteRequest:
    return QuoteRequest.objects.select_related("purchase_request").get(org=org, slug=slug)


def get_org_po(*, org: Organization, slug: str) -> PurchaseOrder:
    return PurchaseOrder.objects.select_related("vendor", "purchase_request").get(
        org=org, slug=slug
    )


def get_org_receipt(*, org: Organization, slug: str) -> WarehouseReceipt:
    return WarehouseReceipt.objects.select_related("purchase_order").get(
        org=org, slug=slug
    )


def receipt_source_item(*, line: WarehouseReceiptLine):
    """Return the PR catalog item when it still lives in the receipt warehouse."""
    warehouse_id = line.receipt.warehouse_id
    if not warehouse_id:
        return None
    request_line = getattr(line.po_line, "request_line", None)
    item = getattr(request_line, "item", None)
    if item is None or item.warehouse_id != warehouse_id:
        return None
    return item


def suggest_receipt_line_items(*, line: WarehouseReceiptLine) -> list[Item]:
    """Warehouse items the UI can offer as add-to-existing for this line."""
    warehouse_id = line.receipt.warehouse_id
    if not warehouse_id:
        return []
    ordered = []
    seen = set()
    source = receipt_source_item(line=line)
    if source is not None and source.is_active:
        ordered.append(source)
        seen.add(source.pk)
    matches = Item.objects.filter(
        warehouse_id=warehouse_id,
        is_active=True,
        name__iexact=line.description,
    ).order_by("name")[:SUGGESTED_ITEM_LIMIT]
    for item in matches:
        if item.pk in seen:
            continue
        ordered.append(item)
        seen.add(item.pk)
        if len(ordered) >= SUGGESTED_ITEM_LIMIT:
            break
    return ordered


def _replace_lines(pr: PurchaseRequest, lines: list[dict], org: Organization) -> None:
    if not lines:
        raise ValidationError({"lines": NO_LINES})
    pr.lines.all().delete()
    for row in lines:
        item = None
        item_slug = row.get("item") or ""
        if item_slug:
            try:
                item = Item.objects.get(org=org, slug=item_slug, is_active=True)
            except Item.DoesNotExist as exc:
                raise ValidationError(
                    {"item": f'Unknown item "{item_slug}".'}
                ) from exc
        PurchaseRequestLine.objects.create(
            request=pr,
            item=item,
            description=row["description"],
            quantity=row["quantity"],
            unit=row["unit"],
        )


def _resolve_space(*, org, actor: UserProfile, space_slug: str | None):
    if actor.user_type == UserProfile.UserType.SPACE_INCHARGE:
        if space_slug:
            raise ValidationError({"space": CANNOT_SET_SPACE})
        if not actor.space_id:
            raise ValidationError({"space": NOT_ASSIGNED_TO_SPACE})
        if not actor.space.is_active:
            raise ValidationError({"space": SPACE_INACTIVE})
        return actor.space
    if not space_slug:
        return None
    try:
        space = Space.objects.get(org=org, slug=space_slug)
    except Space.DoesNotExist as exc:
        raise ValidationError({"space": "Unknown space."}) from exc
    if not space.is_active:
        raise ValidationError({"space": SPACE_INACTIVE})
    return space


@transaction.atomic
def create_purchase_request(
    *,
    org: Organization,
    actor: UserProfile,
    title: str,
    notes: str = "",
    space: str | None = None,
    lines: list[dict],
) -> PurchaseRequest:
    """Create a draft PR with nested lines."""
    resolved = _resolve_space(org=org, actor=actor, space_slug=space)
    if not lines:
        raise ValidationError({"lines": NO_LINES})
    pr = PurchaseRequest.objects.create(
        org=org,
        space=resolved,
        created_by=actor,
        title=title,
        notes=notes,
        status=PurchaseRequest.Status.DRAFT,
    )
    _replace_lines(pr, lines, org)
    record_process_event(
        org=org,
        purchase_request=pr,
        resource_type="purchase_request",
        resource_slug=pr.slug,
        action="create",
        actor=actor,
        payload={"title": title, "status": pr.status},
    )
    return pr


@transaction.atomic
def update_purchase_request(
    *,
    pr: PurchaseRequest,
    actor: UserProfile,
    **fields,
) -> PurchaseRequest:
    """Update a draft or revision_requested PR."""
    if pr.status not in (
        PurchaseRequest.Status.DRAFT,
        PurchaseRequest.Status.REVISION_REQUESTED,
    ):
        raise ValidationError({"detail": INVALID_STATUS})
    lines = fields.pop("lines", None)
    if "title" in fields:
        pr.title = fields["title"]
    if "notes" in fields:
        pr.notes = fields["notes"]
    pr.save()
    if lines is not None:
        _replace_lines(pr, lines, pr.org)
    record_process_event(
        org=pr.org,
        purchase_request=pr,
        resource_type="purchase_request",
        resource_slug=pr.slug,
        action="update",
        actor=actor,
        payload={"status": pr.status},
    )
    return pr


@transaction.atomic
def submit_purchase_request(*, pr: PurchaseRequest, actor: UserProfile) -> PurchaseRequest:
    """Submit a PR. Ops-raised PRs are auto-approved."""
    if pr.status not in (
        PurchaseRequest.Status.DRAFT,
        PurchaseRequest.Status.REVISION_REQUESTED,
    ):
        raise ValidationError({"detail": INVALID_STATUS})
    if pr.lines.count() < 1:
        raise ValidationError({"lines": NO_LINES})
    if pr.is_ops_raised:
        pr.status = PurchaseRequest.Status.APPROVED
        pr.reviewed_by = actor
        pr.reviewed_at = timezone.now()
        action = "submit_auto_approved"
    else:
        pr.status = PurchaseRequest.Status.SUBMITTED
        action = "submit"
    pr.save()
    record_process_event(
        org=pr.org,
        purchase_request=pr,
        resource_type="purchase_request",
        resource_slug=pr.slug,
        action=action,
        actor=actor,
        payload={"status": pr.status},
    )
    return pr


@transaction.atomic
def approve_purchase_request(*, pr: PurchaseRequest, actor: UserProfile) -> PurchaseRequest:
    """Approve a space-raised submitted PR."""
    if pr.status != PurchaseRequest.Status.SUBMITTED:
        raise ValidationError({"detail": INVALID_STATUS})
    pr.status = PurchaseRequest.Status.APPROVED
    pr.reviewed_by = actor
    pr.reviewed_at = timezone.now()
    pr.save()
    record_process_event(
        org=pr.org,
        purchase_request=pr,
        resource_type="purchase_request",
        resource_slug=pr.slug,
        action="approve",
        actor=actor,
        payload={"status": pr.status},
    )
    return pr


@transaction.atomic
def decline_purchase_request(
    *, pr: PurchaseRequest, actor: UserProfile, reason: str
) -> PurchaseRequest:
    """Archive a submitted or approved PR with a reason."""
    if pr.status not in (
        PurchaseRequest.Status.SUBMITTED,
        PurchaseRequest.Status.APPROVED,
        PurchaseRequest.Status.DRAFT,
    ):
        raise ValidationError({"detail": INVALID_STATUS})
    if not (reason or "").strip():
        raise ValidationError({"reason": REASON_REQUIRED})
    pr.status = PurchaseRequest.Status.DECLINED
    pr.review_reason = reason.strip()
    pr.reviewed_by = actor
    pr.reviewed_at = timezone.now()
    pr.save()
    record_process_event(
        org=pr.org,
        purchase_request=pr,
        resource_type="purchase_request",
        resource_slug=pr.slug,
        action="decline",
        actor=actor,
        payload={"status": pr.status, "reason": pr.review_reason},
    )
    return pr


@transaction.atomic
def request_pr_revision(
    *, pr: PurchaseRequest, actor: UserProfile, reason: str
) -> PurchaseRequest:
    if pr.status != PurchaseRequest.Status.SUBMITTED:
        raise ValidationError({"detail": INVALID_STATUS})
    if not (reason or "").strip():
        raise ValidationError({"reason": REASON_REQUIRED})
    pr.status = PurchaseRequest.Status.REVISION_REQUESTED
    pr.review_reason = reason.strip()
    pr.reviewed_by = actor
    pr.reviewed_at = timezone.now()
    pr.save()
    record_process_event(
        org=pr.org,
        purchase_request=pr,
        resource_type="purchase_request",
        resource_slug=pr.slug,
        action="request_revision",
        actor=actor,
        payload={"status": pr.status, "reason": pr.review_reason},
    )
    return pr


@transaction.atomic
def create_rfq(
    *,
    org: Organization,
    actor: UserProfile,
    purchase_request: str,
    vendor_slugs: list[str],
) -> QuoteRequest:
    pr = get_org_pr(org=org, slug=purchase_request)
    if pr.status != PurchaseRequest.Status.APPROVED:
        raise ValidationError({"purchase_request": PR_NOT_APPROVED})
    if not vendor_slugs:
        raise ValidationError({"vendor_slugs": NEED_VENDORS})
    vendors = list(Vendor.objects.filter(org=org, slug__in=vendor_slugs, is_active=True))
    if len(vendors) != len(set(vendor_slugs)):
        raise ValidationError({"vendor_slugs": NEED_VENDORS})
    rfq = QuoteRequest.objects.create(
        org=org,
        purchase_request=pr,
        status=QuoteRequest.Status.PREPARING,
    )
    for vendor in vendors:
        QuoteRequestVendor.objects.create(quote_request=rfq, vendor=vendor)
    record_process_event(
        org=org,
        purchase_request=pr,
        resource_type="quote_request",
        resource_slug=rfq.slug,
        action="create_rfq",
        actor=actor,
        payload={"vendors": vendor_slugs},
    )
    return rfq


@transaction.atomic
def add_rfq_vendor(*, rfq: QuoteRequest, actor: UserProfile, vendor_slug: str):
    try:
        vendor = Vendor.objects.get(org=rfq.org, slug=vendor_slug, is_active=True)
    except Vendor.DoesNotExist as exc:
        raise ValidationError({"vendor": VENDOR_INACTIVE}) from exc
    obj, created = QuoteRequestVendor.objects.get_or_create(
        quote_request=rfq, vendor=vendor
    )
    if not created and obj.status == QuoteRequestVendor.Status.REJECTED:
        obj.status = QuoteRequestVendor.Status.INVITED
        obj.reject_reason = ""
        obj.save()
    record_process_event(
        org=rfq.org,
        purchase_request=rfq.purchase_request,
        resource_type="quote_request",
        resource_slug=rfq.slug,
        action="add_vendor",
        actor=actor,
        payload={"vendor": vendor_slug},
    )
    return obj


@transaction.atomic
def reject_rfq_vendor(
    *, rfq: QuoteRequest, actor: UserProfile, vendor_slug: str, reason: str
):
    if not (reason or "").strip():
        raise ValidationError({"reason": REASON_REQUIRED})
    try:
        qrv = QuoteRequestVendor.objects.get(
            quote_request=rfq, vendor__slug=vendor_slug
        )
    except QuoteRequestVendor.DoesNotExist as exc:
        raise ValidationError({"vendor": VENDOR_NOT_ON_RFQ}) from exc
    qrv.status = QuoteRequestVendor.Status.REJECTED
    qrv.reject_reason = reason.strip()
    qrv.save()
    PurchaseRequestLine.objects.filter(
        request=rfq.purchase_request, awarded_vendor=qrv.vendor
    ).update(awarded_vendor=None)
    record_process_event(
        org=rfq.org,
        purchase_request=rfq.purchase_request,
        resource_type="quote_request",
        resource_slug=rfq.slug,
        action="reject_vendor",
        actor=actor,
        payload={"vendor": vendor_slug, "reason": qrv.reject_reason},
    )
    return qrv


@transaction.atomic
def request_rfq_revision(*, rfq: QuoteRequest, actor: UserProfile) -> QuoteRequest:
    rfq.status = QuoteRequest.Status.PREPARING
    rfq.save(update_fields=["status", "updated_at"])
    record_process_event(
        org=rfq.org,
        purchase_request=rfq.purchase_request,
        resource_type="quote_request",
        resource_slug=rfq.slug,
        action="request_revision",
        actor=actor,
        payload={"status": rfq.status},
    )
    return rfq


@transaction.atomic
def record_vendor_quote(
    *,
    rfq: QuoteRequest,
    actor: UserProfile,
    vendor_slug: str,
    lines: list[dict],
    notes: str = "",
) -> VendorQuote:
    try:
        qrv = QuoteRequestVendor.objects.select_related("vendor").get(
            quote_request=rfq, vendor__slug=vendor_slug
        )
    except QuoteRequestVendor.DoesNotExist as exc:
        raise ValidationError({"vendor": VENDOR_NOT_ON_RFQ}) from exc
    if qrv.status == QuoteRequestVendor.Status.REJECTED:
        raise ValidationError({"vendor": VENDOR_NOT_ON_RFQ})
    quote, _ = VendorQuote.objects.get_or_create(
        quote_request_vendor=qrv, defaults={"notes": notes}
    )
    if notes:
        quote.notes = notes
        quote.save(update_fields=["notes"])
    for row in lines:
        try:
            req_line = PurchaseRequestLine.objects.get(
                request=rfq.purchase_request, slug=row["line"]
            )
        except PurchaseRequestLine.DoesNotExist as exc:
            raise ValidationError({"line": "Unknown request line."}) from exc
        VendorQuoteLine.objects.update_or_create(
            quote=quote,
            request_line=req_line,
            defaults={"unit_price": row["unit_price"]},
        )
    qrv.status = QuoteRequestVendor.Status.QUOTED
    qrv.save(update_fields=["status"])
    rfq.status = QuoteRequest.Status.IN_REVIEW
    rfq.save(update_fields=["status", "updated_at"])
    record_process_event(
        org=rfq.org,
        purchase_request=rfq.purchase_request,
        resource_type="quote_request",
        resource_slug=rfq.slug,
        action="record_quote",
        actor=actor,
        payload={"vendor": vendor_slug},
    )
    return quote


@transaction.atomic
def select_lines(
    *, rfq: QuoteRequest, actor: UserProfile, selections: list[dict]
) -> QuoteRequest:
    """Ops picks one quoted vendor per request line."""
    rfq.status = QuoteRequest.Status.AWARDING
    rfq.save(update_fields=["status", "updated_at"])
    for row in selections:
        try:
            req_line = PurchaseRequestLine.objects.get(
                request=rfq.purchase_request, slug=row["line"]
            )
        except PurchaseRequestLine.DoesNotExist as exc:
            raise ValidationError({"line": "Unknown request line."}) from exc
        if req_line.awarded_vendor_id:
            raise ValidationError({"line": LINE_ALREADY_AWARDED})
        vendor_slug = row["vendor"]
        try:
            qrv = QuoteRequestVendor.objects.select_related("vendor").get(
                quote_request=rfq, vendor__slug=vendor_slug
            )
        except QuoteRequestVendor.DoesNotExist as exc:
            raise ValidationError({"vendor": VENDOR_NOT_ON_RFQ}) from exc
        has_quote = VendorQuoteLine.objects.filter(
            quote__quote_request_vendor=qrv, request_line=req_line
        ).exists()
        if not has_quote:
            raise ValidationError({"vendor": NO_QUOTE_FOR_LINE})
        req_line.awarded_vendor = qrv.vendor
        req_line.save(update_fields=["awarded_vendor"])
        qrv.status = QuoteRequestVendor.Status.AWARDED
        qrv.save(update_fields=["status"])
    record_process_event(
        org=rfq.org,
        purchase_request=rfq.purchase_request,
        resource_type="quote_request",
        resource_slug=rfq.slug,
        action="select_lines",
        actor=actor,
        payload={"selections": selections},
    )
    return rfq


@transaction.atomic
def create_purchase_order(
    *,
    rfq: QuoteRequest,
    actor: UserProfile,
    vendor_slug: str,
    create_purchase_order: bool = True,
) -> PurchaseOrder:
    """Record a PO for one vendor's awarded lines."""
    try:
        vendor = Vendor.objects.get(org=rfq.org, slug=vendor_slug)
    except Vendor.DoesNotExist as exc:
        raise ValidationError({"vendor": VENDOR_NOT_ON_RFQ}) from exc
    awarded = list(
        PurchaseRequestLine.objects.filter(
            request=rfq.purchase_request, awarded_vendor=vendor
        )
    )
    if not awarded:
        raise ValidationError({"vendor": NO_AWARDED_LINES})
    po = PurchaseOrder.objects.create(
        org=rfq.org,
        purchase_request=rfq.purchase_request,
        vendor=vendor,
        is_new_order=create_purchase_order,
        status=PurchaseOrder.Status.ISSUED,
    )
    for line in awarded:
        quote_line = VendorQuoteLine.objects.filter(
            request_line=line,
            quote__quote_request_vendor__vendor=vendor,
        ).first()
        unit_price = quote_line.unit_price if quote_line else Decimal("0")
        PurchaseOrderLine.objects.create(
            purchase_order=po,
            request_line=line,
            description=line.description,
            quantity=line.quantity,
            unit=line.unit,
            unit_price=unit_price,
        )
    record_process_event(
        org=rfq.org,
        purchase_request=rfq.purchase_request,
        resource_type="purchase_order",
        resource_slug=po.slug,
        action="create_po",
        actor=actor,
        payload={"vendor": vendor_slug, "is_new_order": create_purchase_order},
    )
    return po


def _unaward_po_lines(po: PurchaseOrder) -> None:
    PurchaseRequestLine.objects.filter(po_lines__purchase_order=po).update(
        awarded_vendor=None
    )


@transaction.atomic
def record_quality_check(
    *,
    po: PurchaseOrder,
    actor: UserProfile,
    passed: bool,
    reason: str = "",
    next_action: str = "",
) -> QualityCheck:
    if po.status not in (
        PurchaseOrder.Status.ISSUED,
        PurchaseOrder.Status.QC_PENDING,
        PurchaseOrder.Status.QC_FAILED,
    ):
        raise ValidationError({"detail": INVALID_STATUS})
    if not passed and not (reason or "").strip():
        raise ValidationError({"reason": REASON_REQUIRED})
    qc = QualityCheck.objects.create(
        purchase_order=po,
        passed=passed,
        reason=(reason or "").strip(),
        next_action=next_action or "",
        checked_by=actor,
    )
    if passed:
        po.status = PurchaseOrder.Status.RECEIVED
        po.save(update_fields=["status", "updated_at"])
        warehouse = default_receipt_warehouse(org=po.org)
        receipt = WarehouseReceipt.objects.create(
            org=po.org, purchase_order=po, warehouse=warehouse
        )
        for line in po.lines.all():
            WarehouseReceiptLine.objects.create(
                receipt=receipt,
                po_line=line,
                description=line.description,
                quantity=line.quantity,
                unit=line.unit,
            )
    else:
        po.status = PurchaseOrder.Status.QC_FAILED
        po.save(update_fields=["status", "updated_at"])
        if next_action == "choose_vendors":
            _unaward_po_lines(po)
            po.status = PurchaseOrder.Status.CANCELLED
            po.save(update_fields=["status", "updated_at"])
        elif next_action == "reorder_same":
            pass
    record_process_event(
        org=po.org,
        purchase_request=po.purchase_request,
        resource_type="purchase_order",
        resource_slug=po.slug,
        action="quality_check",
        actor=actor,
        payload={"passed": passed, "next": next_action, "reason": qc.reason},
    )
    return qc


@transaction.atomic
def record_invoice(
    *,
    po: PurchaseOrder,
    actor: UserProfile,
    notes: str = "",
    document_urls: list | None = None,
) -> PurchaseInvoice:
    if po.status not in (
        PurchaseOrder.Status.RECEIVED,
        PurchaseOrder.Status.INVOICED,
    ):
        raise ValidationError({"detail": INVALID_STATUS})
    invoice, created = PurchaseInvoice.objects.get_or_create(
        purchase_order=po,
        defaults={
            "notes": notes,
            "document_urls": document_urls or [],
        },
    )
    if not created:
        invoice.notes = notes
        invoice.document_urls = document_urls or invoice.document_urls
        invoice.save()
    po.status = PurchaseOrder.Status.INVOICED
    po.save(update_fields=["status", "updated_at"])
    record_process_event(
        org=po.org,
        purchase_request=po.purchase_request,
        resource_type="purchase_invoice",
        resource_slug=invoice.slug,
        action="invoice",
        actor=actor,
        payload={"notes": notes},
    )
    return invoice


@transaction.atomic
def complete_warehouse_receipt(
    *,
    receipt: WarehouseReceipt,
    actor: UserProfile,
    lines: list[dict],
    warehouse=None,
) -> WarehouseReceipt:
    if receipt.status != WarehouseReceipt.Status.PENDING:
        raise ValidationError({"detail": RECEIPT_NOT_PENDING})
    if receipt.warehouse_id is None:
        if warehouse is None:
            raise ValidationError({"warehouse": WAREHOUSE_REQUIRED})
        if warehouse.org_id != receipt.org_id:
            raise ValidationError({"warehouse": WAREHOUSE_REQUIRED})
        receipt.warehouse = warehouse
        receipt.save(update_fields=["warehouse"])
    receipt_lines = {line.slug: line for line in receipt.lines.select_related("po_line")}
    if set(row["line"] for row in lines) != set(receipt_lines):
        raise ValidationError({"lines": ALL_LINES_REQUIRED})
    for row in lines:
        rec_line = receipt_lines[row["line"]]
        action = row["action"]
        qty = rec_line.quantity
        if action == "add_to_existing":
            item_slug = row.get("item") or ""
            if not item_slug:
                raise ValidationError({"item": ITEM_REQUIRED})
            try:
                item = Item.objects.get(
                    org=receipt.org, slug=item_slug, is_active=True
                )
            except Item.DoesNotExist as exc:
                raise ValidationError({"item": ITEM_REQUIRED}) from exc
            if item.warehouse_id != receipt.warehouse_id:
                raise ValidationError({"item": ITEM_WRONG_WAREHOUSE})
            increment_stock(
                item=item,
                quantity=qty,
                actor=actor,
                receipt_slug=receipt.slug,
                line_slug=rec_line.slug,
            )
            rec_line.item = item
            rec_line.save(update_fields=["item"])
        elif action == "new_item":
            item = create_item(
                org=receipt.org,
                warehouse=receipt.warehouse,
                name=row.get("name") or rec_line.description,
                unit=row.get("unit") or rec_line.unit,
                part_number=row.get("part_number") or "",
                actor=actor,
            )
            increment_stock(
                item=item,
                quantity=qty,
                actor=actor,
                receipt_slug=receipt.slug,
                line_slug=rec_line.slug,
            )
            rec_line.item = item
            rec_line.save(update_fields=["item"])
        else:
            raise ValidationError({"action": UNKNOWN_ACTION})
    receipt.status = WarehouseReceipt.Status.COMPLETED
    receipt.completed_at = timezone.now()
    receipt.save(update_fields=["status", "completed_at"])
    record_process_event(
        org=receipt.org,
        purchase_request=receipt.purchase_order.purchase_request,
        resource_type="warehouse_receipt",
        resource_slug=receipt.slug,
        action="warehouse_complete",
        actor=actor,
        payload={"status": receipt.status},
    )
    return receipt


def list_pr_trail(*, pr: PurchaseRequest):
    return ProcessEvent.objects.filter(purchase_request=pr).order_by("created_at")


def verify_process_event(*, content_hash: str, signature: str) -> bool:
    if not ProcessEvent.objects.filter(
        content_hash=content_hash, signature=signature
    ).exists():
        return False
    return verify_signature(content_hash=content_hash, signature=signature)
