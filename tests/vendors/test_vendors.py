"""
Tests for vendor API and services.

Warehouse managers ARE allowed (unlike member management).
"""
import pytest
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.organizations.models import Organization
from apps.vendors.models import Vendor
from apps.vendors.services import (
    ALREADY_SUSPENDED,
    DUPLICATE_NAME,
    NOT_SUSPENDED,
    VENDOR_SUSPENDED,
    VENDOR_UNSUSPENDED,
    create_vendor,
    suspend_vendor,
    unsuspend_vendor,
)

VENDORS_URL = "/api/orgs/vendors/"


def _payload(**overrides):
    data = {
        "name": "Acme Supplies",
        "contact_name": "Jane Doe",
        "phone": "+15551234",
        "address": "12 Warehouse Rd",
        "email": "jane@acme.com",
        "gst": "22AAAAA0000A1Z5",
        "website": "https://acme.example",
    }
    data.update(overrides)
    return data


def _detail_url(slug: str) -> str:
    return f"{VENDORS_URL}{slug}/"


@pytest.mark.django_db
class TestCreateVendorService:
    def test_creates_vendor(self, test_org):
        vendor = create_vendor(org=test_org, **_payload())
        assert vendor.slug == "acme-supplies"
        assert vendor.org == test_org
        assert vendor.is_active is True

    def test_duplicate_name_same_org(self, test_org):
        create_vendor(org=test_org, **_payload())
        with pytest.raises(ValidationError) as exc:
            create_vendor(org=test_org, **_payload())
        assert DUPLICATE_NAME in exc.value.messages

    def test_same_name_different_org_allowed(self, test_org):
        other = Organization.objects.create(name="Other", org_suffix="other_v")
        create_vendor(org=test_org, **_payload())
        vendor = create_vendor(org=other, **_payload())
        assert vendor.org == other


@pytest.mark.django_db
class TestVendorListCreate:
    def test_create_and_list(self, auth_client):
        response = auth_client.post(VENDORS_URL, _payload(), format="json")
        assert response.status_code == 201
        data = response.json()
        assert data["slug"] == "acme-supplies"
        assert "id" not in data
        listed = auth_client.get(VENDORS_URL)
        assert listed.status_code == 200
        slugs = {row["slug"] for row in listed.json()["results"]}
        assert "acme-supplies" in slugs

    def test_warehouse_manager_can_create(self, warehouse_client):
        response = warehouse_client.post(VENDORS_URL, _payload(), format="json")
        assert response.status_code == 201

    def test_duplicate_name(self, auth_client):
        auth_client.post(VENDORS_URL, _payload(), format="json")
        response = auth_client.post(VENDORS_URL, _payload(), format="json")
        assert response.status_code == 400
        assert response.json()["name"] == [DUPLICATE_NAME]

    def test_list_status_filters(self, auth_client, test_org):
        active = create_vendor(org=test_org, **_payload())
        suspended = create_vendor(
            org=test_org, **_payload(name="Paused Co", email="p@example.com")
        )
        suspend_vendor(org=test_org, slug=suspended.slug)

        active_list = auth_client.get(VENDORS_URL, {"status": "active"})
        assert {r["slug"] for r in active_list.json()["results"]} == {active.slug}

        suspended_list = auth_client.get(VENDORS_URL, {"status": "suspended"})
        assert {r["slug"] for r in suspended_list.json()["results"]} == {suspended.slug}

        bad = auth_client.get(VENDORS_URL, {"status": "nope"})
        assert bad.status_code == 400

    def test_unauthenticated(self):
        assert APIClient().get(VENDORS_URL).status_code == 401

    def test_superuser_forbidden(self, superuser_client):
        assert superuser_client.get(VENDORS_URL).status_code == 403
        assert superuser_client.post(VENDORS_URL, _payload(), format="json").status_code == 403


@pytest.mark.django_db
class TestVendorRetrieveUpdate:
    def test_get_and_patch(self, auth_client, test_org):
        vendor = create_vendor(org=test_org, **_payload())
        get = auth_client.get(_detail_url(vendor.slug))
        assert get.status_code == 200
        assert get.json()["name"] == "Acme Supplies"

        patch = auth_client.patch(
            _detail_url(vendor.slug),
            {"phone": "+1999"},
            format="json",
        )
        assert patch.status_code == 200
        assert patch.json()["phone"] == "+1999"
        assert patch.json()["slug"] == "acme-supplies"

    def test_patch_duplicate_name(self, auth_client, test_org):
        create_vendor(org=test_org, **_payload())
        other = create_vendor(
            org=test_org, **_payload(name="Beta", email="b@example.com")
        )
        response = auth_client.patch(
            _detail_url(other.slug),
            {"name": "Acme Supplies"},
            format="json",
        )
        assert response.status_code == 400
        assert response.json()["name"] == [DUPLICATE_NAME]

    def test_other_org_not_found(self, auth_client):
        other = Organization.objects.create(name="Other", org_suffix="other_v2")
        vendor = create_vendor(org=other, **_payload())
        assert auth_client.get(_detail_url(vendor.slug)).status_code == 404

    def test_warehouse_manager_can_patch(self, warehouse_client, test_org):
        vendor = create_vendor(org=test_org, **_payload())
        response = warehouse_client.patch(
            _detail_url(vendor.slug),
            {"contact_name": "Sam"},
            format="json",
        )
        assert response.status_code == 200
        assert response.json()["contact_name"] == "Sam"


@pytest.mark.django_db
class TestVendorSuspend:
    def test_suspend_and_unsuspend(self, auth_client, test_org):
        vendor = create_vendor(org=test_org, **_payload())
        suspend = auth_client.post(_detail_url(vendor.slug) + "suspend/", format="json")
        assert suspend.status_code == 200
        assert suspend.json() == {"detail": VENDOR_SUSPENDED}
        vendor.refresh_from_db()
        assert vendor.is_active is False

        again = auth_client.post(_detail_url(vendor.slug) + "suspend/", format="json")
        assert again.status_code == 400
        assert again.json() == {"detail": ALREADY_SUSPENDED}

        unsuspend = auth_client.post(
            _detail_url(vendor.slug) + "unsuspend/", format="json"
        )
        assert unsuspend.status_code == 200
        assert unsuspend.json() == {"detail": VENDOR_UNSUSPENDED}

        not_suspended = auth_client.post(
            _detail_url(vendor.slug) + "unsuspend/", format="json"
        )
        assert not_suspended.status_code == 400
        assert not_suspended.json() == {"detail": NOT_SUSPENDED}

    def test_unknown_slug(self, auth_client):
        assert auth_client.post(
            f"{VENDORS_URL}missing/suspend/", format="json"
        ).status_code == 404

    def test_warehouse_manager_can_suspend(self, warehouse_client, test_org):
        vendor = create_vendor(org=test_org, **_payload())
        response = warehouse_client.post(
            _detail_url(vendor.slug) + "suspend/", format="json"
        )
        assert response.status_code == 200
        assert Vendor.objects.get(pk=vendor.pk).is_active is False
