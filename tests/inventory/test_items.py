"""Tests for the item catalog API. quantity_on_hand is not freely writable."""
import pytest

from apps.inventory.models import Item

ITEMS = "/api/orgs/items/"


@pytest.mark.django_db
class TestItemListCreate:
    def test_warehouse_creates(self, warehouse_client):
        response = warehouse_client.post(
            ITEMS,
            {"name": "A4 paper", "unit": "ream", "sku": "PAP-A4"},
            format="json",
        )
        assert response.status_code == 201
        data = response.json()
        assert data["slug"] == "a4-paper"
        assert data["quantity_on_hand"] == "0.000"
        assert "id" not in data

    def test_ops_can_list_not_create(self, ops_client, warehouse_client):
        warehouse_client.post(
            ITEMS, {"name": "Pens", "unit": "pcs"}, format="json"
        )
        listed = ops_client.get(ITEMS)
        assert listed.status_code == 200
        assert listed.json()["results"]
        created = ops_client.post(
            ITEMS, {"name": "Nope", "unit": "pcs"}, format="json"
        )
        assert created.status_code == 403

    def test_space_incharge_forbidden(self, assigned_space_client):
        assert assigned_space_client.get(ITEMS).status_code == 403

    def test_quantity_not_accepted_on_create(self, warehouse_client):
        response = warehouse_client.post(
            ITEMS,
            {"name": "Tape", "unit": "roll", "quantity_on_hand": "99"},
            format="json",
        )
        assert response.status_code == 201
        assert response.json()["quantity_on_hand"] == "0.000"


@pytest.mark.django_db
class TestItemUpdate:
    def test_patch_name_not_quantity(self, warehouse_client, test_org):
        item = Item.objects.create(org=test_org, name="Stapler", unit="pcs")
        item.quantity_on_hand = 5
        item.save()
        response = warehouse_client.patch(
            f"{ITEMS}{item.slug}/",
            {"name": "Office stapler", "quantity_on_hand": "100"},
            format="json",
        )
        assert response.status_code == 200
        item.refresh_from_db()
        assert item.name == "Office stapler"
        assert item.quantity_on_hand == 5
