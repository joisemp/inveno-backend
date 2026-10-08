"""
Development-only demo org, users, catalog, and purchase-flow snapshots.

Called by `manage.py seed_demo`. Production never imports this from a request
path. Wipe deletes the demo org then the demo users (profile.org is SET_NULL,
so org delete alone would leave orphan logins).
"""
from decimal import Decimal
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from PIL import Image

from apps.inventory.models import Item, ItemCategory, ItemPhoto, Warehouse
from apps.inventory.services import (
    add_item_photo,
    create_item,
    create_item_category,
    create_warehouse,
    increment_stock,
    suspend_item,
)
from apps.organizations.models import Organization, Space
from apps.organizations.services import create_org_user, create_org_with_central_admin
from apps.organizations.space_services import assign_space_incharge, create_space
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
from apps.purchases.services import (
    complete_warehouse_receipt,
    create_purchase_order,
    create_purchase_request,
    create_rfq,
    decline_purchase_request,
    record_invoice,
    record_quality_check,
    record_vendor_quote,
    select_lines,
    submit_purchase_request,
)
from apps.users.models import UserProfile
from apps.vendors.models import Vendor
from apps.vendors.services import create_vendor, suspend_vendor

User = get_user_model()

DEMO_ORG_SUFFIX = "demo"
DEMO_ORG_NAME = "Demo Kitchen Group"
DEMO_PASSWORD = "DemoPass123!"

DEMO_SUPER_EMAIL = "super@inveno.local"
DEMO_ADMIN_EMAIL = "admin@demo.inveno.local"
DEMO_OPS_EMAIL = "ops@demo.inveno.local"
DEMO_WAREHOUSE_EMAIL = "warehouse@demo.inveno.local"
DEMO_SPACE_EMAIL = "space@demo.inveno.local"

# Login id is email (User.USERNAME_FIELD). Printed after create / wipe.
DEMO_ACCOUNTS = (
    (DEMO_SUPER_EMAIL, "super_admin"),
    (DEMO_ADMIN_EMAIL, "central_admin"),
    (DEMO_OPS_EMAIL, "operation_incharge"),
    (DEMO_WAREHOUSE_EMAIL, "warehouse_manager"),
    (DEMO_SPACE_EMAIL, "space_incharge"),
)
DEMO_EMAILS = tuple(email for email, _role in DEMO_ACCOUNTS)


def get_demo_org():
    """Return the demo organisation, or None."""
    return Organization.objects.filter(org_suffix=DEMO_ORG_SUFFIX).first()


def format_demo_logins() -> str:
    """Return the copy-paste login table for newly created demo users."""
    lines = [
        "Demo users created. Login with email + password:",
        "",
        f"  {'Login (email)':<32} {'Role':<22} Password",
    ]
    for email, role in DEMO_ACCOUNTS:
        lines.append(f"  {email:<32} {role:<22} {DEMO_PASSWORD}")
    return "\n".join(lines)


@transaction.atomic
def wipe_demo() -> None:
    """Delete demo rows in FK-safe order, then the demo logins."""
    org = get_demo_org()
    if org is not None:
        ProcessEvent.objects.filter(org=org).delete()
        WarehouseReceiptLine.objects.filter(receipt__org=org).delete()
        WarehouseReceipt.objects.filter(org=org).delete()
        QualityCheck.objects.filter(purchase_order__org=org).delete()
        PurchaseInvoice.objects.filter(purchase_order__org=org).delete()
        PurchaseOrderLine.objects.filter(purchase_order__org=org).delete()
        PurchaseOrder.objects.filter(org=org).delete()
        VendorQuoteLine.objects.filter(
            quote__quote_request_vendor__quote_request__org=org
        ).delete()
        VendorQuote.objects.filter(
            quote_request_vendor__quote_request__org=org
        ).delete()
        QuoteRequestVendor.objects.filter(quote_request__org=org).delete()
        QuoteRequest.objects.filter(org=org).delete()
        PurchaseRequestLine.objects.filter(request__org=org).delete()
        PurchaseRequest.all_objects.filter(org=org).delete()
        ItemPhoto.objects.filter(item__org=org).delete()
        Item.objects.filter(org=org).delete()
        Warehouse.objects.filter(org=org).delete()
        Vendor.objects.filter(org=org).delete()
        ItemCategory.objects.filter(org=org).delete()
        Space.objects.filter(org=org).delete()
        org.delete()
    User.objects.filter(email__in=DEMO_EMAILS).delete()


def seed_demo() -> Organization:
    """Create the demo org and related rows. Caller must wipe first if needed."""
    with transaction.atomic():
        org, admin = create_org_with_central_admin(
            org_name=DEMO_ORG_NAME,
            org_suffix=DEMO_ORG_SUFFIX,
            location="Demo City",
            admin_email=DEMO_ADMIN_EMAIL,
            admin_first_name="Dana",
            admin_last_name="Central",
            admin_phone="5550100",
            send_email=False,
        )
        _create_superuser()
        ops = create_org_user(
            org=org,
            email=DEMO_OPS_EMAIL,
            first_name="Omar",
            last_name="Ops",
            phone="5550101",
            user_type=UserProfile.UserType.OPERATION_INCHARGE,
            send_email=False,
        )
        warehouse_user = create_org_user(
            org=org,
            email=DEMO_WAREHOUSE_EMAIL,
            first_name="Wendy",
            last_name="Warehouse",
            phone="5550102",
            user_type=UserProfile.UserType.WAREHOUSE_MANAGER,
            send_email=False,
        )
        space_user = create_org_user(
            org=org,
            email=DEMO_SPACE_EMAIL,
            first_name="Nora",
            last_name="North",
            phone="5550103",
            user_type=UserProfile.UserType.SPACE_INCHARGE,
            send_email=False,
        )
        _set_demo_passwords()

        north = create_space(org=org, name="North Wing", location="Building A")
        create_space(org=org, name="Kitchen B", location="Building B")
        assign_space_incharge(
            org=org,
            space_slug=north.slug,
            member_slug=space_user.profile.slug,
        )
        space_user.profile.refresh_from_db()

        default_wh = Warehouse.objects.get(org=org, name="Warehouse")
        tomato = _seed_catalog(org=org, warehouse=default_wh)
        vendors = _seed_vendors(org=org)
        _seed_purchases(
            org=org,
            admin=admin.profile,
            ops=ops.profile,
            warehouse_profile=warehouse_user.profile,
            space_profile=space_user.profile,
            vendors=vendors,
            tomato=tomato,
        )
        south = create_warehouse(org=org, name="South store", location="Yard")
        create_item(
            org=org,
            warehouse=south,
            name="Spare gas hose",
            unit="pcs",
            part_number="HOSE-1",
        )
        return org


def _create_superuser():
    user = User.objects.create_superuser(
        email=DEMO_SUPER_EMAIL,
        password=DEMO_PASSWORD,
    )
    profile = user.profile
    profile.first_name = "Super"
    profile.last_name = "Admin"
    profile.save(update_fields=["first_name", "last_name"])
    return user


def _set_demo_passwords():
    for email, _role in DEMO_ACCOUNTS:
        user = User.objects.get(email=email)
        user.set_password(DEMO_PASSWORD)
        user.save(update_fields=["password"])


def _tiny_png():
    buf = BytesIO()
    Image.new("RGB", (8, 8), color=(200, 80, 40)).save(buf, format="PNG")
    return SimpleUploadedFile("tomato.png", buf.getvalue(), content_type="image/png")


def _seed_catalog(*, org, warehouse):
    kitchen_cat = create_item_category(org=org, name="Kitchen supplies")
    office_cat = create_item_category(org=org, name="Office supplies")
    tomato = create_item(
        org=org,
        warehouse=warehouse,
        name="Tomato puree",
        unit="can",
        part_number="TOM-1",
        category=kitchen_cat,
        location="Aisle 1",
    )
    increment_stock(item=tomato, quantity=Decimal("24"))
    add_item_photo(item=tomato, uploaded_file=_tiny_png())
    oil = create_item(
        org=org,
        warehouse=warehouse,
        name="Olive oil",
        unit="bottle",
        part_number="OIL-1",
        category=kitchen_cat,
    )
    increment_stock(item=oil, quantity=Decimal("12"))
    create_item(
        org=org,
        warehouse=warehouse,
        name="Basmati rice",
        unit="kg",
        part_number="RICE-1",
        category=kitchen_cat,
    )
    create_item(
        org=org,
        warehouse=warehouse,
        name="A4 paper",
        unit="ream",
        part_number="PAP-A4",
        category=office_cat,
    )
    blender = create_item(
        org=org,
        warehouse=warehouse,
        name="Retired blender",
        unit="pcs",
        part_number="BLD-X",
        category=kitchen_cat,
    )
    suspend_item(org=org, slug=blender.slug)
    return tomato


def _seed_vendors(*, org):
    farm = create_vendor(
        org=org,
        name="Fresh Farm Foods",
        contact_name="Priya Farm",
        phone="5550201",
        address="12 Market Road",
        email="farm@demo.inveno.local",
    )
    metro = create_vendor(
        org=org,
        name="Metro Wholesale",
        contact_name="Lee Metro",
        phone="5550202",
        address="88 Depot Lane",
        email="metro@demo.inveno.local",
    )
    old = create_vendor(
        org=org,
        name="Old Town Traders",
        contact_name="Sam Old",
        phone="5550203",
        address="1 Harbour Street",
    )
    suspend_vendor(org=org, slug=old.slug)
    return farm, metro


def _pr(*, org, actor, title, lines, space=None):
    return create_purchase_request(
        org=org,
        actor=actor,
        title=title,
        notes="Demo seed",
        space=space,
        lines=lines,
    )


def _ops_approved(*, org, ops, title, lines):
    pr = _pr(org=org, actor=ops, title=title, lines=lines)
    return submit_purchase_request(pr=pr, actor=ops)


def _quoted_rfq(*, org, ops, pr, vendors):
    rfq = create_rfq(
        org=org,
        actor=ops,
        purchase_request=pr.slug,
        vendor_slugs=[vendor.slug for vendor in vendors],
    )
    req_lines = list(pr.lines.all())
    for vendor in vendors:
        record_vendor_quote(
            rfq=rfq,
            actor=ops,
            vendor_slug=vendor.slug,
            notes="Demo quote",
            lines=[
                {"line": line.slug, "unit_price": "10.50"} for line in req_lines
            ],
        )
    return rfq, req_lines


def _issue_po_through_qc(*, org, ops, warehouse_profile, title, lines, vendors, winner):
    pr = _ops_approved(org=org, ops=ops, title=title, lines=lines)
    rfq, req_lines = _quoted_rfq(org=org, ops=ops, pr=pr, vendors=vendors)
    select_lines(
        rfq=rfq,
        actor=ops,
        selections=[
            {"line": line.slug, "vendor": winner.slug} for line in req_lines
        ],
    )
    po = create_purchase_order(rfq=rfq, actor=ops, vendor_slug=winner.slug)
    record_quality_check(po=po, actor=warehouse_profile, passed=True)
    return PurchaseOrder.objects.select_related("warehouse_receipt").get(pk=po.pk)


def _seed_purchases(
    *,
    org,
    admin,
    ops,
    warehouse_profile,
    space_profile,
    vendors,
    tomato,
):
    farm, metro = vendors

    _pr(
        org=org,
        actor=space_profile,
        title="Draft pantry restock",
        lines=[
            {
                "item": tomato.slug,
                "description": "Tomato puree",
                "quantity": "6",
                "unit": "can",
            }
        ],
    )

    submitted = _pr(
        org=org,
        actor=space_profile,
        title="North Wing weekly produce",
        lines=[
            {"description": "Salad greens", "quantity": "10", "unit": "kg"},
        ],
    )
    submit_purchase_request(pr=submitted, actor=space_profile)

    declined = _pr(
        org=org,
        actor=space_profile,
        title="Over-budget glassware",
        lines=[{"description": "Wine glasses", "quantity": "24", "unit": "pcs"}],
    )
    submit_purchase_request(pr=declined, actor=space_profile)
    decline_purchase_request(
        pr=declined,
        actor=ops,
        reason="Over budget for this cycle",
    )

    rfq_pr = _ops_approved(
        org=org,
        ops=ops,
        title="Bulk rice and oil",
        lines=[
            {"description": "Basmati rice", "quantity": "50", "unit": "kg"},
            {"description": "Olive oil", "quantity": "8", "unit": "bottle"},
        ],
    )
    _quoted_rfq(org=org, ops=ops, pr=rfq_pr, vendors=(farm, metro))

    _issue_po_through_qc(
        org=org,
        ops=ops,
        warehouse_profile=warehouse_profile,
        title="Mixing bowls for Kitchen B",
        lines=[
            {"description": "Stainless mixing bowl", "quantity": "4", "unit": "pcs"}
        ],
        vendors=(farm, metro),
        winner=metro,
    )

    completed_po = _issue_po_through_qc(
        org=org,
        ops=ops,
        warehouse_profile=warehouse_profile,
        title="Tomato puree top-up",
        lines=[
            {
                "item": tomato.slug,
                "description": "Tomato puree",
                "quantity": "12",
                "unit": "can",
            }
        ],
        vendors=(farm, metro),
        winner=farm,
    )
    receipt = completed_po.warehouse_receipt
    complete_warehouse_receipt(
        receipt=receipt,
        actor=warehouse_profile,
        lines=[
            {
                "line": line.slug,
                "action": "add_to_existing",
                "item": tomato.slug,
            }
            for line in receipt.lines.all()
        ],
    )

    invoiced = _issue_po_through_qc(
        org=org,
        ops=ops,
        warehouse_profile=warehouse_profile,
        title="Olive oil restock invoice run",
        lines=[
            {"description": "Olive oil", "quantity": "6", "unit": "bottle"},
        ],
        vendors=(farm, metro),
        winner=farm,
    )
    record_invoice(
        po=invoiced,
        actor=admin,
        notes="Forwarded for demo payment screen",
    )
