"""Tests for warehouse CRUD."""
import pytest

from apps.inventory.models import Warehouse

WAREHOUSES = "/api/orgs/warehouses/"


@pytest.mark.django_db
class TestWarehouseAPI:
    def test_list_includes_default(self, warehouse_client, warehouse):
        response = warehouse_client.get(WAREHOUSES)
        assert response.status_code == 200
        slugs = [row["slug"] for row in response.json()["results"]]
        assert warehouse.slug in slugs

    def test_create_and_duplicate(self, warehouse_client):
        created = warehouse_client.post(
            WAREHOUSES, {"name": "South store", "location": "Dock 2"}, format="json"
        )
        assert created.status_code == 201
        assert created.json()["slug"] == "south-store"
        dup = warehouse_client.post(
            WAREHOUSES, {"name": "South store"}, format="json"
        )
        assert dup.status_code == 400
        assert dup.json()["name"] == ["A warehouse with this name already exists."]

    def test_space_incharge_forbidden(self, assigned_space_client):
        assert assigned_space_client.get(WAREHOUSES).status_code == 403

    def test_ops_can_list_not_create(self, ops_client, warehouse):
        listed = ops_client.get(WAREHOUSES)
        assert listed.status_code == 200
        created = ops_client.post(WAREHOUSES, {"name": "Nope"}, format="json")
        assert created.status_code == 403

    def test_patch_is_active(self, warehouse_client, warehouse):
        response = warehouse_client.patch(
            f"{WAREHOUSES}{warehouse.slug}/",
            {"is_active": False},
            format="json",
        )
        assert response.status_code == 200
        assert response.json()["is_active"] is False
        warehouse.refresh_from_db()
        assert warehouse.is_active is False
