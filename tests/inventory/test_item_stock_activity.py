"""Tests for item stock add/remove and the activity log."""
import pytest

from apps.inventory.models import Item, ItemActivity
from apps.inventory.services import increment_stock

ITEMS = "/api/orgs/items/"


def _create_item(client, warehouse, name="A4 paper"):
    response = client.post(
        ITEMS,
        {"name": name, "unit": "ream", "warehouse": warehouse.slug},
        format="json",
    )
    assert response.status_code == 201
    return response.json()


@pytest.mark.django_db
class TestItemCreateActivity:
    def test_create_logs_item_edit_created(self, warehouse_client, warehouse_manager, warehouse):
        data = _create_item(warehouse_client, warehouse)
        assert data["quantity_on_hand"] == "0.000"
        assert "id" not in data
        listed = warehouse_client.get(f"{ITEMS}{data['slug']}/activity/")
        assert listed.status_code == 200
        rows = listed.json()["results"]
        assert len(rows) == 1
        row = rows[0]
        assert row["kind"] == "item_edit"
        assert row["action"] == "created"
        assert row["slug"] == "a4-paper-created"
        assert row["previous_quantity"] is None
        assert row["recorded_on"]
        assert row["recorded_by"]["slug"] == warehouse_manager.profile.slug
        assert "id" not in row

    def test_create_still_ignores_quantity_on_hand(self, warehouse_client, warehouse):
        response = warehouse_client.post(
            ITEMS,
            {
                "name": "Tape",
                "unit": "roll",
                "quantity_on_hand": "99",
                "warehouse": warehouse.slug,
            },
            format="json",
        )
        assert response.status_code == 201
        assert response.json()["quantity_on_hand"] == "0.000"


@pytest.mark.django_db
class TestItemStockEndpoint:
    def test_add_stock(self, warehouse_client, warehouse_manager, warehouse):
        item = _create_item(warehouse_client, warehouse)
        response = warehouse_client.post(
            f"{ITEMS}{item['slug']}/stock/",
            {"action": "add", "quantity": "12.000", "reason": "Opening balance"},
            format="json",
        )
        assert response.status_code == 200
        assert response.json()["quantity_on_hand"] == "12.000"
        assert response.json()["balance_in_stock"] == "12.000"
        assert response.json()["last_purchase_date"] is None
        assert "id" not in response.json()
        listed = warehouse_client.get(f"{ITEMS}{item['slug']}/activity/?kind=incoming")
        rows = listed.json()["results"]
        assert rows[0]["action"] == "added"
        assert rows[0]["previous_quantity"] == "0.000"
        assert rows[0]["quantity"] == "12.000"
        assert rows[0]["delta"] == "12.000"
        assert rows[0]["remarks"] == "Opening balance"
        assert rows[0]["recorded_by"]["slug"] == warehouse_manager.profile.slug
        assert rows[0]["reference"]["type"] == "item_activity"

    def test_remove_stock(self, warehouse_client, warehouse):
        item = _create_item(warehouse_client, warehouse)
        warehouse_client.post(
            f"{ITEMS}{item['slug']}/stock/",
            {"action": "add", "quantity": "12", "reason": "Opening balance"},
            format="json",
        )
        response = warehouse_client.post(
            f"{ITEMS}{item['slug']}/stock/",
            {"action": "remove", "quantity": "2", "reason": "Damaged"},
            format="json",
        )
        assert response.status_code == 200
        assert response.json()["quantity_on_hand"] == "10.000"
        assert response.json()["last_purchase_date"] is None
        outgoing = warehouse_client.get(
            f"{ITEMS}{item['slug']}/activity/?kind=outgoing"
        ).json()["results"]
        assert outgoing[0]["action"] == "removed"
        assert outgoing[0]["delta"] == "-2.000"

    def test_remove_more_than_on_hand(self, warehouse_client, warehouse):
        item = _create_item(warehouse_client, warehouse)
        response = warehouse_client.post(
            f"{ITEMS}{item['slug']}/stock/",
            {"action": "remove", "quantity": "1", "reason": "Damaged"},
            format="json",
        )
        assert response.status_code == 400
        assert response.json()["quantity"] == ["Insufficient stock."]

    def test_missing_reason(self, warehouse_client, warehouse):
        item = _create_item(warehouse_client, warehouse)
        response = warehouse_client.post(
            f"{ITEMS}{item['slug']}/stock/",
            {"action": "add", "quantity": "1"},
            format="json",
        )
        assert response.status_code == 400
        assert "reason" in response.json()

    def test_non_positive_quantity(self, warehouse_client, warehouse):
        item = _create_item(warehouse_client, warehouse)
        response = warehouse_client.post(
            f"{ITEMS}{item['slug']}/stock/",
            {"action": "add", "quantity": "0", "reason": "Nope"},
            format="json",
        )
        assert response.status_code == 400
        assert "quantity" in response.json()

    def test_patch_cannot_change_stock(self, warehouse_client, warehouse):
        item = _create_item(warehouse_client, warehouse)
        warehouse_client.post(
            f"{ITEMS}{item['slug']}/stock/",
            {"action": "add", "quantity": "5", "reason": "Seed"},
            format="json",
        )
        patched = warehouse_client.patch(
            f"{ITEMS}{item['slug']}/",
            {"quantity_on_hand": "99", "name": "A4 copier paper"},
            format="json",
        )
        assert patched.status_code == 200
        assert patched.json()["quantity_on_hand"] == "5.000"
        assert patched.json()["name"] == "A4 copier paper"

    def test_ops_forbidden_on_stock_can_read_activity(
        self, warehouse_client, ops_client, warehouse
    ):
        item = _create_item(warehouse_client, warehouse)
        denied = ops_client.post(
            f"{ITEMS}{item['slug']}/stock/",
            {"action": "add", "quantity": "1", "reason": "Nope"},
            format="json",
        )
        assert denied.status_code == 403
        listed = ops_client.get(f"{ITEMS}{item['slug']}/activity/")
        assert listed.status_code == 200

    def test_space_incharge_forbidden(self, warehouse_client, assigned_space_client, warehouse):
        item = _create_item(warehouse_client, warehouse)
        assert assigned_space_client.get(f"{ITEMS}{item['slug']}/activity/").status_code == 403
        assert (
            assigned_space_client.post(
                f"{ITEMS}{item['slug']}/stock/",
                {"action": "add", "quantity": "1", "reason": "Nope"},
                format="json",
            ).status_code
            == 403
        )


@pytest.mark.django_db
class TestItemActivityDetails:
    def test_catalog_patch_logs_updated(self, warehouse_client, warehouse):
        item = _create_item(warehouse_client, warehouse)
        warehouse_client.patch(
            f"{ITEMS}{item['slug']}/",
            {"location": "Aisle 3"},
            format="json",
        )
        rows = warehouse_client.get(
            f"{ITEMS}{item['slug']}/activity/?kind=item_edit"
        ).json()["results"]
        updated = next(row for row in rows if row["action"] == "updated")
        detail = warehouse_client.get(
            f"{ITEMS}{item['slug']}/activity/{updated['slug']}/"
        )
        assert detail.status_code == 200
        assert detail.json()["payload"]["changes"]["location"] == {
            "from": "",
            "to": "Aisle 3",
        }
        assert "id" not in detail.json()

    def test_suspend_includes_actor_and_status(self, warehouse_client, warehouse_manager, warehouse):
        item = _create_item(warehouse_client, warehouse)
        assert warehouse_client.post(f"{ITEMS}{item['slug']}/suspend/").status_code == 200
        rows = warehouse_client.get(f"{ITEMS}{item['slug']}/activity/").json()["results"]
        suspended = next(row for row in rows if row["action"] == "suspended")
        assert suspended["recorded_on"]
        assert suspended["recorded_by"]["slug"] == warehouse_manager.profile.slug
        detail = warehouse_client.get(
            f"{ITEMS}{item['slug']}/activity/{suspended['slug']}/"
        ).json()
        assert detail["payload"]["is_active"] == {"from": True, "to": False}
        assert detail["payload"]["actor"]["slug"] == warehouse_manager.profile.slug

    def test_invalid_kind_filter(self, warehouse_client, warehouse):
        item = _create_item(warehouse_client, warehouse)
        response = warehouse_client.get(f"{ITEMS}{item['slug']}/activity/?kind=nope")
        assert response.status_code == 400
        assert "kind" in response.json()

    def test_unknown_activity_404(self, warehouse_client, warehouse):
        item = _create_item(warehouse_client, warehouse)
        response = warehouse_client.get(f"{ITEMS}{item['slug']}/activity/missing/")
        assert response.status_code == 404

    def test_receipt_increment_logs_received(self, warehouse_client, warehouse_manager, warehouse):
        item = _create_item(warehouse_client, warehouse)
        db_item = Item.objects.get(slug=item["slug"])
        increment_stock(
            item=db_item,
            quantity=10,
            actor=warehouse_manager.profile,
            receipt_slug="recv-po-a4-paper",
            line_slug="a4-receipt-line",
        )
        rows = warehouse_client.get(
            f"{ITEMS}{item['slug']}/activity/?kind=incoming"
        ).json()["results"]
        received = next(row for row in rows if row["action"] == "received")
        assert received["reference"] == {
            "type": "warehouse_receipt",
            "slug": "recv-po-a4-paper",
        }
        assert received["quantity"] == "10.000"
        db_item.refresh_from_db()
        assert db_item.last_purchase_quantity == 10
        detail = warehouse_client.get(
            f"{ITEMS}{item['slug']}/activity/{received['slug']}/"
        ).json()
        assert detail["payload"]["receipt"] == "recv-po-a4-paper"
        assert detail["payload"]["line"] == "a4-receipt-line"

    def test_every_row_has_recorded_on(self, warehouse_client, warehouse):
        item = _create_item(warehouse_client, warehouse)
        warehouse_client.post(
            f"{ITEMS}{item['slug']}/stock/",
            {"action": "add", "quantity": "1", "reason": "Count"},
            format="json",
        )
        rows = warehouse_client.get(f"{ITEMS}{item['slug']}/activity/").json()["results"]
        assert rows
        assert all(row["recorded_on"] for row in rows)
        assert ItemActivity.objects.filter(item__slug=item["slug"]).count() >= 2
