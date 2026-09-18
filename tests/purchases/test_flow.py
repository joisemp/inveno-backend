"""Purchase-flow tests: PR, RFQ, per-line vendor select, PO, QC, warehouse, trail."""
import pytest

from apps.inventory.models import Item, Warehouse
from apps.vendors.models import Vendor

PR = "/api/orgs/purchase-requests/"
RFQ = "/api/orgs/rfqs/"
PO = "/api/orgs/purchase-orders/"
RECV = "/api/orgs/warehouse/receipts/"


def _lines():
    return [
        {"description": "A4 paper", "quantity": "10", "unit": "ream"},
        {"description": "Blue pens", "quantity": "50", "unit": "pcs"},
    ]


@pytest.fixture
def vendor_a(db, test_org):
    return Vendor.objects.create(
        org=test_org,
        name="Acme Supplies",
        contact_name="A",
        phone="1",
        address="A",
    )


@pytest.fixture
def vendor_b(db, test_org):
    return Vendor.objects.create(
        org=test_org,
        name="Office Mart",
        contact_name="B",
        phone="2",
        address="B",
    )


@pytest.mark.django_db
class TestPurchaseRequestPermissions:
    def test_unassigned_space_incharge_cannot_create(self, space_incharge_client):
        response = space_incharge_client.post(
            PR,
            {"title": "Need stock", "lines": _lines()},
            format="json",
        )
        assert response.status_code == 400
        assert "space" in response.json()

    def test_assigned_space_incharge_creates(self, assigned_space_client, space):
        response = assigned_space_client.post(
            PR,
            {"title": "Pantry restock", "lines": _lines()},
            format="json",
        )
        assert response.status_code == 201
        data = response.json()
        assert data["space"] == space.slug
        assert data["status"] == "draft"
        assert len(data["lines"]) == 2
        assert "id" not in data

    def test_ops_creates_without_space(self, ops_client):
        response = ops_client.post(
            PR,
            {"title": "Org-level buy", "lines": _lines()},
            format="json",
        )
        assert response.status_code == 201
        assert response.json()["space"] is None

    def test_warehouse_forbidden(self, warehouse_client):
        assert warehouse_client.get(PR).status_code == 403

    def test_space_incharge_does_not_see_org_level(self, ops_client, assigned_space_client):
        ops_client.post(PR, {"title": "Hidden", "lines": _lines()}, format="json")
        listed = assigned_space_client.get(PR)
        slugs = [row["slug"] for row in listed.json()["results"]]
        assert "hidden" not in slugs


@pytest.mark.django_db
class TestSubmitAndApprove:
    def test_ops_submit_auto_approves(self, ops_client):
        created = ops_client.post(
            PR, {"title": "Ops buy", "lines": _lines()}, format="json"
        ).json()
        submitted = ops_client.post(f"{PR}{created['slug']}/submit/", format="json")
        assert submitted.status_code == 200
        assert submitted.json()["status"] == "approved"

    def test_space_submit_needs_approve(
        self, assigned_space_client, ops_client
    ):
        created = assigned_space_client.post(
            PR, {"title": "Space buy", "lines": _lines()}, format="json"
        ).json()
        submitted = assigned_space_client.post(
            f"{PR}{created['slug']}/submit/", format="json"
        )
        assert submitted.json()["status"] == "submitted"
        approved = ops_client.post(f"{PR}{created['slug']}/approve/", format="json")
        assert approved.json()["status"] == "approved"

    def test_decline_archives(self, assigned_space_client, ops_client):
        created = assigned_space_client.post(
            PR, {"title": "No", "lines": _lines()}, format="json"
        ).json()
        assigned_space_client.post(f"{PR}{created['slug']}/submit/", format="json")
        declined = ops_client.post(
            f"{PR}{created['slug']}/decline/",
            {"reason": "Over budget"},
            format="json",
        )
        assert declined.status_code == 200
        assert declined.json()["status"] == "declined"
        assert declined.json()["review_reason"] == "Over budget"

    def test_space_incharge_cannot_approve(self, assigned_space_client):
        created = assigned_space_client.post(
            PR, {"title": "X", "lines": _lines()}, format="json"
        ).json()
        assigned_space_client.post(f"{PR}{created['slug']}/submit/", format="json")
        assert (
            assigned_space_client.post(
                f"{PR}{created['slug']}/approve/", format="json"
            ).status_code
            == 403
        )


@pytest.mark.django_db
class TestSplitAwardAndWarehouse:
    def test_two_vendors_two_pos(
        self, ops_client, warehouse_client, vendor_a, vendor_b, test_org
    ):
        created = ops_client.post(
            PR, {"title": "Split buy", "lines": _lines()}, format="json"
        ).json()
        ops_client.post(f"{PR}{created['slug']}/submit/", format="json")
        rfq = ops_client.post(
            RFQ,
            {
                "purchase_request": created["slug"],
                "vendor_slugs": [vendor_a.slug, vendor_b.slug],
            },
            format="json",
        )
        assert rfq.status_code == 201
        rfq_slug = rfq.json()["slug"]
        line_slugs = [row["slug"] for row in rfq.json()["lines"]]
        assert len(line_slugs) == 2
        for vendor in (vendor_a, vendor_b):
            quoted = ops_client.post(
                f"{RFQ}{rfq_slug}/quotes/",
                {
                    "vendor": vendor.slug,
                    "lines": [
                        {"line": line_slugs[0], "unit_price": "12.50"},
                        {"line": line_slugs[1], "unit_price": "0.80"},
                    ],
                },
                format="json",
            )
            assert quoted.status_code == 200
        selected = ops_client.post(
            f"{RFQ}{rfq_slug}/select-lines/",
            {
                "selections": [
                    {"line": line_slugs[0], "vendor": vendor_a.slug},
                    {"line": line_slugs[1], "vendor": vendor_b.slug},
                ]
            },
            format="json",
        )
        assert selected.status_code == 200
        po_a = ops_client.post(
            f"{RFQ}{rfq_slug}/purchase-orders/",
            {"vendor": vendor_a.slug, "create_purchase_order": True},
            format="json",
        )
        po_b = ops_client.post(
            f"{RFQ}{rfq_slug}/purchase-orders/",
            {"vendor": vendor_b.slug, "create_purchase_order": True},
            format="json",
        )
        assert po_a.status_code == 201
        assert po_b.status_code == 201
        assert len(po_a.json()["lines"]) == 1
        assert len(po_b.json()["lines"]) == 1

        qc = ops_client.post(
            f"{PO}{po_a.json()['slug']}/quality-check/",
            {"passed": True},
            format="json",
        )
        assert qc.status_code == 200
        receipts = warehouse_client.get(f"{RECV}?status=pending")
        assert receipts.status_code == 200
        receipt = receipts.json()["results"][0]
        complete_payload = {
            "lines": [
                {
                    "line": receipt["lines"][0]["slug"],
                    "action": "new_item",
                    "name": "A4 paper stock",
                    "unit": "ream",
                }
            ]
        }
        done = warehouse_client.post(
            f"{RECV}{receipt['slug']}/complete/",
            complete_payload,
            format="json",
        )
        assert done.status_code == 200
        assert done.json()["status"] == "completed"
        item = Item.objects.get(org=test_org, name="A4 paper stock")
        assert item.quantity_on_hand == 10
        assert item.last_purchase_quantity == 10
        assert item.last_purchase_date is not None
        assert item.warehouse_id is not None

        inv = ops_client.post(
            f"{PO}{po_a.json()['slug']}/invoice/",
            {"notes": "Filed offline", "document_urls": ["https://example.com/inv.pdf"]},
            format="json",
        )
        assert inv.status_code == 200

        trail = ops_client.get(f"{PR}{created['slug']}/trail/")
        assert trail.status_code == 200
        actions = [row["action"] for row in trail.json()]
        assert "submit_auto_approved" in actions
        assert "select_lines" in actions
        assert "quality_check" in actions
        event = trail.json()[-1]
        verified = ops_client.post(
            "/api/orgs/process-events/verify/",
            {"content_hash": event["content_hash"], "signature": event["signature"]},
            format="json",
        )
        assert verified.json()["valid"] is True
        tampered = ops_client.post(
            "/api/orgs/process-events/verify/",
            {"content_hash": event["content_hash"], "signature": "0" * 64},
            format="json",
        )
        assert tampered.json()["valid"] is False

        pdf = ops_client.get(f"{PR}{created['slug']}/export/?format=pdf")
        assert pdf.status_code == 200
        assert pdf["Content-Type"] == "application/pdf"
        assert pdf.content[:4] == b"%PDF"
        xlsx = ops_client.get(f"{PR}{created['slug']}/export/?format=xlsx")
        assert xlsx.status_code == 200
        assert xlsx.content[:2] == b"PK"

    def test_select_without_quote_fails(self, ops_client, vendor_a, vendor_b):
        created = ops_client.post(
            PR, {"title": "Need quotes", "lines": _lines()}, format="json"
        ).json()
        ops_client.post(f"{PR}{created['slug']}/submit/", format="json")
        rfq = ops_client.post(
            RFQ,
            {
                "purchase_request": created["slug"],
                "vendor_slugs": [vendor_a.slug, vendor_b.slug],
            },
            format="json",
        ).json()
        line = rfq["lines"][0]["slug"]
        ops_client.post(
            f"{RFQ}{rfq['slug']}/quotes/",
            {
                "vendor": vendor_a.slug,
                "lines": [{"line": line, "unit_price": "1.00"}],
            },
            format="json",
        )
        bad = ops_client.post(
            f"{RFQ}{rfq['slug']}/select-lines/",
            {"selections": [{"line": line, "vendor": vendor_b.slug}]},
            format="json",
        )
        assert bad.status_code == 400

    def test_space_incharge_export_other_space_404(
        self, ops_client, assigned_space_client
    ):
        created = ops_client.post(
            PR, {"title": "Ops only", "lines": _lines()}, format="json"
        ).json()
        response = assigned_space_client.get(
            f"{PR}{created['slug']}/export/?format=pdf"
        )
        assert response.status_code == 404


@pytest.mark.django_db
class TestEmptyVendors:
    def test_rfq_without_vendors(self, ops_client):
        created = ops_client.post(
            PR, {"title": "No vendors", "lines": _lines()}, format="json"
        ).json()
        ops_client.post(f"{PR}{created['slug']}/submit/", format="json")
        rfq = ops_client.post(
            RFQ,
            {"purchase_request": created["slug"], "vendor_slugs": []},
            format="json",
        )
        assert rfq.status_code == 400


def _submit_quoted_rfq(ops_client, vendor_a, vendor_b):
    """Create an approved PR with two competing quotes on both lines."""
    created = ops_client.post(
        PR, {"title": "Quoted buy", "lines": _lines()}, format="json"
    ).json()
    ops_client.post(f"{PR}{created['slug']}/submit/", format="json")
    rfq = ops_client.post(
        RFQ,
        {
            "purchase_request": created["slug"],
            "vendor_slugs": [vendor_a.slug, vendor_b.slug],
        },
        format="json",
    ).json()
    line_slugs = [row["slug"] for row in rfq["lines"]]
    for vendor in (vendor_a, vendor_b):
        ops_client.post(
            f"{RFQ}{rfq['slug']}/quotes/",
            {
                "vendor": vendor.slug,
                "lines": [
                    {"line": line_slugs[0], "unit_price": "12.50"},
                    {"line": line_slugs[1], "unit_price": "0.80"},
                ],
            },
            format="json",
        )
    return created, rfq, line_slugs


@pytest.mark.django_db
class TestRevisionRejectAndQc:
    def test_request_revision_then_resubmit(self, assigned_space_client, ops_client):
        created = assigned_space_client.post(
            PR, {"title": "Need more info", "lines": _lines()}, format="json"
        ).json()
        assigned_space_client.post(f"{PR}{created['slug']}/submit/", format="json")
        revised = ops_client.post(
            f"{PR}{created['slug']}/request-revision/",
            {"reason": "Add quantities"},
            format="json",
        )
        assert revised.status_code == 200
        assert revised.json()["status"] == "revision_requested"
        patched = assigned_space_client.patch(
            f"{PR}{created['slug']}/",
            {"notes": "Qty confirmed", "lines": _lines()},
            format="json",
        )
        assert patched.status_code == 200
        submitted = assigned_space_client.post(
            f"{PR}{created['slug']}/submit/", format="json"
        )
        assert submitted.json()["status"] == "submitted"

    def test_empty_lines_rejected(self, ops_client):
        response = ops_client.post(
            PR, {"title": "Empty", "lines": []}, format="json"
        )
        assert response.status_code == 400

    def test_double_select_fails(self, ops_client, vendor_a, vendor_b):
        _created, rfq, line_slugs = _submit_quoted_rfq(ops_client, vendor_a, vendor_b)
        first = ops_client.post(
            f"{RFQ}{rfq['slug']}/select-lines/",
            {"selections": [{"line": line_slugs[0], "vendor": vendor_a.slug}]},
            format="json",
        )
        assert first.status_code == 200
        second = ops_client.post(
            f"{RFQ}{rfq['slug']}/select-lines/",
            {"selections": [{"line": line_slugs[0], "vendor": vendor_b.slug}]},
            format="json",
        )
        assert second.status_code == 400

    def test_reject_vendor_unawards(self, ops_client, vendor_a, vendor_b):
        _created, rfq, line_slugs = _submit_quoted_rfq(ops_client, vendor_a, vendor_b)
        ops_client.post(
            f"{RFQ}{rfq['slug']}/select-lines/",
            {"selections": [{"line": line_slugs[0], "vendor": vendor_a.slug}]},
            format="json",
        )
        rejected = ops_client.post(
            f"{RFQ}{rfq['slug']}/vendors/{vendor_a.slug}/reject/",
            {"reason": "Too expensive"},
            format="json",
        )
        assert rejected.status_code == 200
        vendor_row = next(
            row for row in rejected.json()["vendors"] if row["vendor"] == vendor_a.slug
        )
        assert vendor_row["status"] == "rejected"
        line = next(
            row for row in rejected.json()["lines"] if row["slug"] == line_slugs[0]
        )
        assert line["awarded_vendor"] is None

    def test_create_po_without_new_order(self, ops_client, vendor_a, vendor_b):
        _created, rfq, line_slugs = _submit_quoted_rfq(ops_client, vendor_a, vendor_b)
        ops_client.post(
            f"{RFQ}{rfq['slug']}/select-lines/",
            {"selections": [{"line": line_slugs[0], "vendor": vendor_a.slug}]},
            format="json",
        )
        po = ops_client.post(
            f"{RFQ}{rfq['slug']}/purchase-orders/",
            {"vendor": vendor_a.slug, "create_purchase_order": False},
            format="json",
        )
        assert po.status_code == 201
        assert po.json()["is_new_order"] is False

    def test_qc_fail_return_stays_on_vendor(self, ops_client, vendor_a, vendor_b):
        _created, rfq, line_slugs = _submit_quoted_rfq(ops_client, vendor_a, vendor_b)
        ops_client.post(
            f"{RFQ}{rfq['slug']}/select-lines/",
            {"selections": [{"line": line_slugs[0], "vendor": vendor_a.slug}]},
            format="json",
        )
        po = ops_client.post(
            f"{RFQ}{rfq['slug']}/purchase-orders/",
            {"vendor": vendor_a.slug, "create_purchase_order": True},
            format="json",
        ).json()
        qc = ops_client.post(
            f"{PO}{po['slug']}/quality-check/",
            {"passed": False, "reason": "Damaged", "next": "return"},
            format="json",
        )
        assert qc.status_code == 200
        assert qc.json()["status"] == "qc_failed"
        receipts = ops_client.get(RECV)
        assert receipts.status_code == 403

    def test_qc_choose_vendors_unawards(self, ops_client, vendor_a, vendor_b):
        created, rfq, line_slugs = _submit_quoted_rfq(ops_client, vendor_a, vendor_b)
        ops_client.post(
            f"{RFQ}{rfq['slug']}/select-lines/",
            {"selections": [{"line": line_slugs[0], "vendor": vendor_a.slug}]},
            format="json",
        )
        po = ops_client.post(
            f"{RFQ}{rfq['slug']}/purchase-orders/",
            {"vendor": vendor_a.slug, "create_purchase_order": True},
            format="json",
        ).json()
        qc = ops_client.post(
            f"{PO}{po['slug']}/quality-check/",
            {
                "passed": False,
                "reason": "Wrong spec",
                "next": "choose_vendors",
            },
            format="json",
        )
        assert qc.status_code == 200
        assert qc.json()["status"] == "cancelled"
        detail = ops_client.get(f"{PR}{created['slug']}/").json()
        line = next(row for row in detail["lines"] if row["slug"] == line_slugs[0])
        assert line["awarded_vendor"] is None

    def test_add_to_existing_stock(
        self, ops_client, warehouse_client, vendor_a, vendor_b, test_org, warehouse
    ):
        existing = Item.objects.create(
            org=test_org,
            warehouse=warehouse,
            name="A4 paper stock",
            unit="ream",
            quantity_on_hand=3,
        )
        _created, rfq, line_slugs = _submit_quoted_rfq(ops_client, vendor_a, vendor_b)
        ops_client.post(
            f"{RFQ}{rfq['slug']}/select-lines/",
            {"selections": [{"line": line_slugs[0], "vendor": vendor_a.slug}]},
            format="json",
        )
        po = ops_client.post(
            f"{RFQ}{rfq['slug']}/purchase-orders/",
            {"vendor": vendor_a.slug, "create_purchase_order": True},
            format="json",
        ).json()
        ops_client.post(f"{PO}{po['slug']}/quality-check/", {"passed": True}, format="json")
        receipt = warehouse_client.get(f"{RECV}?status=pending").json()["results"][0]
        done = warehouse_client.post(
            f"{RECV}{receipt['slug']}/complete/",
            {
                "lines": [
                    {
                        "line": receipt["lines"][0]["slug"],
                        "action": "add_to_existing",
                        "item": existing.slug,
                    }
                ]
            },
            format="json",
        )
        assert done.status_code == 200
        existing.refresh_from_db()
        assert existing.quantity_on_hand == 13
        pdf = warehouse_client.get(f"{RECV}{receipt['slug']}/export/?format=pdf")
        assert pdf.status_code == 200
        assert pdf.content[:4] == b"%PDF"

    def test_add_to_existing_rejects_other_warehouse(
        self, ops_client, warehouse_client, vendor_a, vendor_b, test_org, warehouse
    ):
        other = Warehouse.objects.create(org=test_org, name="South store")
        stray = Item.objects.create(
            org=test_org, warehouse=other, name="A4 paper stock", unit="ream"
        )
        _created, rfq, line_slugs = _submit_quoted_rfq(ops_client, vendor_a, vendor_b)
        ops_client.post(
            f"{RFQ}{rfq['slug']}/select-lines/",
            {"selections": [{"line": line_slugs[0], "vendor": vendor_a.slug}]},
            format="json",
        )
        po = ops_client.post(
            f"{RFQ}{rfq['slug']}/purchase-orders/",
            {"vendor": vendor_a.slug, "create_purchase_order": True},
            format="json",
        ).json()
        ops_client.post(f"{PO}{po['slug']}/quality-check/", {"passed": True}, format="json")
        receipt = warehouse_client.get(f"{RECV}?status=pending").json()["results"][0]
        done = warehouse_client.post(
            f"{RECV}{receipt['slug']}/complete/",
            {
                "warehouse": warehouse.slug,
                "lines": [
                    {
                        "line": receipt["lines"][0]["slug"],
                        "action": "add_to_existing",
                        "item": stray.slug,
                    }
                ]
            },
            format="json",
        )
        assert done.status_code == 400
        assert done.json()["item"] == "This item is not in the receipt warehouse."

    def test_rfq_and_po_xlsx_export(self, ops_client, vendor_a, vendor_b):
        _created, rfq, line_slugs = _submit_quoted_rfq(ops_client, vendor_a, vendor_b)
        ops_client.post(
            f"{RFQ}{rfq['slug']}/select-lines/",
            {"selections": [{"line": line_slugs[0], "vendor": vendor_a.slug}]},
            format="json",
        )
        po = ops_client.post(
            f"{RFQ}{rfq['slug']}/purchase-orders/",
            {"vendor": vendor_a.slug, "create_purchase_order": True},
            format="json",
        ).json()
        xlsx = ops_client.get(f"{RFQ}{rfq['slug']}/export/?format=xlsx")
        assert xlsx.status_code == 200
        assert xlsx.content[:2] == b"PK"
        po_pdf = ops_client.get(f"{PO}{po['slug']}/export/?format=pdf")
        assert po_pdf.status_code == 200
        assert po_pdf.content[:4] == b"%PDF"


def _award_first_line_and_receive(ops_client, warehouse_client, vendor_a, vendor_b, pr_lines):
    """Submit an ops PR, award the first line, QC-pass, return the pending receipt."""
    created = ops_client.post(
        PR, {"title": "Receive match", "lines": pr_lines}, format="json"
    ).json()
    ops_client.post(f"{PR}{created['slug']}/submit/", format="json")
    rfq = ops_client.post(
        RFQ,
        {
            "purchase_request": created["slug"],
            "vendor_slugs": [vendor_a.slug, vendor_b.slug],
        },
        format="json",
    ).json()
    line_slugs = [row["slug"] for row in rfq["lines"]]
    for vendor in (vendor_a, vendor_b):
        ops_client.post(
            f"{RFQ}{rfq['slug']}/quotes/",
            {
                "vendor": vendor.slug,
                "lines": [
                    {"line": slug, "unit_price": "12.50"} for slug in line_slugs
                ],
            },
            format="json",
        )
    ops_client.post(
        f"{RFQ}{rfq['slug']}/select-lines/",
        {"selections": [{"line": line_slugs[0], "vendor": vendor_a.slug}]},
        format="json",
    )
    po = ops_client.post(
        f"{RFQ}{rfq['slug']}/purchase-orders/",
        {"vendor": vendor_a.slug, "create_purchase_order": True},
        format="json",
    ).json()
    ops_client.post(f"{PO}{po['slug']}/quality-check/", {"passed": True}, format="json")
    return warehouse_client.get(f"{RECV}?status=pending").json()["results"][0]


@pytest.mark.django_db
class TestReceiptSuggestions:
    def test_source_item_and_suggested_from_pr_item(
        self, ops_client, warehouse_client, vendor_a, vendor_b, test_org, warehouse
    ):
        existing = Item.objects.create(
            org=test_org,
            warehouse=warehouse,
            name="A4 paper",
            unit="ream",
            part_number="PAP-A4",
            quantity_on_hand=3,
        )
        receipt = _award_first_line_and_receive(
            ops_client,
            warehouse_client,
            vendor_a,
            vendor_b,
            [
                {
                    "description": "A4 paper",
                    "quantity": "10",
                    "unit": "ream",
                    "item": existing.slug,
                }
            ],
        )
        line = receipt["lines"][0]
        assert line["source_item"] == existing.slug
        assert line["suggested_items"][0]["slug"] == existing.slug
        assert line["suggested_items"][0]["part_number"] == "PAP-A4"
        detail = warehouse_client.get(f"{RECV}{receipt['slug']}/")
        assert detail.status_code == 200
        assert detail.json()["lines"][0]["source_item"] == existing.slug

    def test_suggested_items_match_description_name(
        self, ops_client, warehouse_client, vendor_a, vendor_b, test_org, warehouse
    ):
        existing = Item.objects.create(
            org=test_org,
            warehouse=warehouse,
            name="A4 paper",
            unit="ream",
            quantity_on_hand=2,
        )
        receipt = _award_first_line_and_receive(
            ops_client,
            warehouse_client,
            vendor_a,
            vendor_b,
            [{"description": "A4 paper", "quantity": "10", "unit": "ream"}],
        )
        slugs = [row["slug"] for row in receipt["lines"][0]["suggested_items"]]
        assert existing.slug in slugs
        assert receipt["lines"][0]["source_item"] is None

    def test_no_warehouse_means_empty_suggestions(
        self, ops_client, warehouse_client, vendor_a, vendor_b, test_org, warehouse
    ):
        Item.objects.create(
            org=test_org, warehouse=warehouse, name="A4 paper", unit="ream"
        )
        Warehouse.objects.create(org=test_org, name="South store")
        receipt = _award_first_line_and_receive(
            ops_client,
            warehouse_client,
            vendor_a,
            vendor_b,
            [{"description": "A4 paper", "quantity": "10", "unit": "ream"}],
        )
        assert receipt["warehouse"] is None
        assert receipt["lines"][0]["suggested_items"] == []
        assert receipt["lines"][0]["source_item"] is None
