"""Tests for the development demo seed command."""
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command

from apps.common.demo import DEMO_EMAILS, DEMO_ORG_SUFFIX, DEMO_PASSWORD
from apps.inventory.models import Item, ItemPhoto, Warehouse
from apps.organizations.models import Organization, Space
from apps.purchases.models import (
    PurchaseInvoice,
    PurchaseOrder,
    PurchaseRequest,
    QuoteRequest,
    WarehouseReceipt,
)
from apps.vendors.models import Vendor

User = get_user_model()


@pytest.fixture(autouse=True)
def _demo_media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    settings.DEBUG = True
    settings.SEED_DEMO = True


def _seed(*args):
    out = StringIO()
    call_command("seed_demo", *args, stdout=out)
    return out.getvalue()


@pytest.mark.django_db
class TestSeedDemo:
    def test_creates_users_and_prints_logins(self):
        output = _seed()
        assert Organization.objects.filter(org_suffix=DEMO_ORG_SUFFIX).exists()
        for email in DEMO_EMAILS:
            user = User.objects.get(email=email)
            assert user.check_password(DEMO_PASSWORD)
            assert email in output
        assert DEMO_PASSWORD in output
        assert "Demo users created" in output

    def test_keep_does_not_duplicate(self):
        _seed()
        first_count = User.objects.filter(email__in=DEMO_EMAILS).count()
        pr_count = PurchaseRequest.objects.filter(
            org__org_suffix=DEMO_ORG_SUFFIX
        ).count()
        output = _seed("--keep")
        assert User.objects.filter(email__in=DEMO_EMAILS).count() == first_count
        assert (
            PurchaseRequest.objects.filter(org__org_suffix=DEMO_ORG_SUFFIX).count()
            == pr_count
        )
        assert "Keeping existing" in output
        assert "Demo users created" not in output

    def test_second_run_without_flags_keeps_when_not_a_tty(self):
        _seed()
        output = _seed()
        assert User.objects.filter(email__in=DEMO_EMAILS).count() == len(DEMO_EMAILS)
        assert "Keeping existing" in output
        assert "docker compose exec -it" in output

    def test_reset_recreates_same_emails(self):
        _seed()
        old_id = User.objects.get(email=DEMO_EMAILS[0]).pk
        output = _seed("--reset")
        assert User.objects.filter(email__in=DEMO_EMAILS).count() == len(DEMO_EMAILS)
        assert User.objects.get(email=DEMO_EMAILS[0]).pk != old_id
        assert "Demo users created" in output
        org = Organization.objects.get(org_suffix=DEMO_ORG_SUFFIX)
        assert Space.objects.filter(org=org).count() == 2
        assert Warehouse.objects.filter(org=org).count() == 2
        assert Item.objects.filter(org=org).count() == 6
        assert ItemPhoto.objects.filter(item__org=org).count() == 1
        assert Vendor.objects.filter(org=org, is_active=False).count() == 1
        assert PurchaseRequest.objects.filter(org=org, status="draft").exists()
        assert PurchaseRequest.objects.filter(org=org, status="submitted").exists()
        assert PurchaseRequest.objects.filter(org=org, status="declined").exists()
        assert QuoteRequest.objects.filter(org=org, status="in_review").exists()
        assert WarehouseReceipt.objects.filter(org=org, status="pending").exists()
        assert WarehouseReceipt.objects.filter(org=org, status="completed").exists()
        assert PurchaseInvoice.objects.filter(
            purchase_order__org=org, status="pending_payment"
        ).exists()
        assert PurchaseOrder.objects.filter(org=org).exists()
        assert Item.objects.filter(org=org, is_active=False).exists()

    def test_skips_when_not_debug(self, settings):
        settings.DEBUG = False
        output = _seed()
        assert "DEBUG is False" in output
        assert not Organization.objects.filter(org_suffix=DEMO_ORG_SUFFIX).exists()

    def test_skips_when_seed_demo_disabled(self, settings):
        settings.SEED_DEMO = False
        output = _seed()
        assert "SEED_DEMO is False" in output
        assert not Organization.objects.filter(org_suffix=DEMO_ORG_SUFFIX).exists()
