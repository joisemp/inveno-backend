"""Tests for the item catalog API. quantity_on_hand is not freely writable."""
from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.inventory.models import Item, ItemPhoto, Warehouse
from apps.organizations.models import Organization

ITEMS = "/api/orgs/items/"
CATEGORIES = "/api/orgs/item-categories/"


def _png_upload(name="shot.png"):
    buf = BytesIO()
    Image.new("RGB", (8, 8), color="red").save(buf, format="PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


@pytest.mark.django_db
class TestItemListCreate:
    def test_warehouse_creates(self, warehouse_client, warehouse):
        response = warehouse_client.post(
            ITEMS,
            {
                "name": "A4 paper",
                "unit": "ream",
                "part_number": "PAP-A4",
                "warehouse": warehouse.slug,
            },
            format="json",
        )
        assert response.status_code == 201
        data = response.json()
        assert data["slug"] == "a4-paper"
        assert data["part_number"] == "PAP-A4"
        assert data["warehouse"] == warehouse.slug
        assert data["quantity_on_hand"] == "0.000"
        assert data["balance_in_stock"] == "0.000"
        assert data["photos"] == []
        assert "id" not in data

    def test_create_requires_warehouse(self, warehouse_client):
        response = warehouse_client.post(
            ITEMS, {"name": "A4 paper", "unit": "ream"}, format="json"
        )
        assert response.status_code == 400
        assert "warehouse" in response.json()

    def test_create_rejects_inactive_warehouse(self, warehouse_client, warehouse):
        warehouse.is_active = False
        warehouse.save()
        response = warehouse_client.post(
            ITEMS,
            {"name": "Tape", "unit": "roll", "warehouse": warehouse.slug},
            format="json",
        )
        assert response.status_code == 400
        assert response.json()["warehouse"] == ["This warehouse is inactive."]

    def test_ops_can_list_not_create(self, ops_client, warehouse_client, warehouse):
        warehouse_client.post(
            ITEMS,
            {"name": "Pens", "unit": "pcs", "warehouse": warehouse.slug},
            format="json",
        )
        listed = ops_client.get(ITEMS)
        assert listed.status_code == 200
        assert listed.json()["results"]
        created = ops_client.post(
            ITEMS,
            {"name": "Nope", "unit": "pcs", "warehouse": warehouse.slug},
            format="json",
        )
        assert created.status_code == 403

    def test_space_incharge_forbidden(self, assigned_space_client):
        assert assigned_space_client.get(ITEMS).status_code == 403

    def test_quantity_not_accepted_on_create(self, warehouse_client, warehouse):
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

    def test_duplicate_name_same_warehouse(self, warehouse_client, warehouse):
        payload = {
            "name": "A4 paper",
            "unit": "ream",
            "part_number": "PAP-A4",
            "warehouse": warehouse.slug,
        }
        assert warehouse_client.post(ITEMS, payload, format="json").status_code == 201
        dup = warehouse_client.post(ITEMS, payload, format="json")
        assert dup.status_code == 400
        assert dup.json()["name"] == ["An item with this name already exists."]

    def test_duplicate_part_number_same_warehouse(self, warehouse_client, warehouse):
        warehouse_client.post(
            ITEMS,
            {
                "name": "A4 paper",
                "unit": "ream",
                "part_number": "PAP-A4",
                "warehouse": warehouse.slug,
            },
            format="json",
        )
        dup = warehouse_client.post(
            ITEMS,
            {
                "name": "A3 paper",
                "unit": "ream",
                "part_number": "PAP-A4",
                "warehouse": warehouse.slug,
            },
            format="json",
        )
        assert dup.status_code == 400
        assert dup.json()["part_number"] == [
            "An item with this part number already exists."
        ]

    def test_same_name_second_warehouse(self, warehouse_client, warehouse, test_org):
        other = Warehouse.objects.create(org=test_org, name="South store")
        warehouse_client.post(
            ITEMS,
            {"name": "A4 paper", "unit": "ream", "warehouse": warehouse.slug},
            format="json",
        )
        second = warehouse_client.post(
            ITEMS,
            {"name": "A4 paper", "unit": "ream", "warehouse": other.slug},
            format="json",
        )
        assert second.status_code == 201

    def test_list_filters_warehouse(self, warehouse_client, warehouse, test_org):
        other = Warehouse.objects.create(org=test_org, name="South store")
        warehouse_client.post(
            ITEMS,
            {"name": "A4 paper", "unit": "ream", "warehouse": warehouse.slug},
            format="json",
        )
        warehouse_client.post(
            ITEMS,
            {"name": "Pens", "unit": "pcs", "warehouse": other.slug},
            format="json",
        )
        listed = warehouse_client.get(ITEMS, {"warehouse": warehouse.slug})
        names = [row["name"] for row in listed.json()["results"]]
        assert names == ["A4 paper"]
        unknown = warehouse_client.get(ITEMS, {"warehouse": "missing"})
        assert unknown.status_code == 400


@pytest.mark.django_db
class TestItemUpdate:
    def test_patch_name_not_quantity(self, warehouse_client, test_org, warehouse):
        item = Item.objects.create(
            org=test_org, warehouse=warehouse, name="Stapler", unit="pcs"
        )
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

    def test_patch_last_purchase_and_warehouse(
        self, warehouse_client, test_org, warehouse
    ):
        item = Item.objects.create(
            org=test_org, warehouse=warehouse, name="Stapler", unit="pcs"
        )
        other = Warehouse.objects.create(org=test_org, name="South store")
        response = warehouse_client.patch(
            f"{ITEMS}{item.slug}/",
            {
                "last_purchase_date": "2026-01-15",
                "last_purchase_quantity": "4.000",
                "warehouse": other.slug,
            },
            format="json",
        )
        assert response.status_code == 200
        data = response.json()
        assert data["last_purchase_date"] == "2026-01-15"
        assert data["last_purchase_quantity"] == "4.000"
        assert data["warehouse"] == other.slug


@pytest.mark.django_db
class TestItemCategory:
    def test_create_and_attach(self, warehouse_client, warehouse):
        created = warehouse_client.post(CATEGORIES, {"name": "Stationery"}, format="json")
        assert created.status_code == 201
        slug = created.json()["slug"]
        item = warehouse_client.post(
            ITEMS,
            {
                "name": "A4 paper",
                "unit": "ream",
                "warehouse": warehouse.slug,
                "category": slug,
                "location": "Aisle 2",
                "remarks": "Keep dry",
            },
            format="json",
        )
        assert item.status_code == 201
        assert item.json()["category"] == slug
        assert item.json()["location"] == "Aisle 2"


@pytest.mark.django_db
class TestItemPhotos:
    def test_upload_converts_to_webp(self, warehouse_client, test_org, warehouse):
        item = Item.objects.create(
            org=test_org, warehouse=warehouse, name="A4 paper", unit="ream"
        )
        response = warehouse_client.post(
            f"{ITEMS}{item.slug}/photos/",
            {"image": _png_upload("aisle-bin.png")},
            format="multipart",
        )
        assert response.status_code == 201
        data = response.json()
        assert data["slug"] == "aisle-bin"
        assert data["url"].endswith(
            f"/api/orgs/items/{item.slug}/photos/{data['slug']}/file/"
        )
        photo = ItemPhoto.objects.get(slug=data["slug"])
        assert photo.image.name.endswith(".webp")
        photo.image.open("rb")
        header = photo.image.read(12)
        photo.image.close()
        assert header[:4] == b"RIFF"
        assert header[8:] == b"WEBP"

    def test_sixth_photo_rejected(self, warehouse_client, test_org, warehouse):
        item = Item.objects.create(
            org=test_org, warehouse=warehouse, name="A4 paper", unit="ream"
        )
        for i in range(5):
            resp = warehouse_client.post(
                f"{ITEMS}{item.slug}/photos/",
                {"image": _png_upload(f"pic-{i}.png")},
                format="multipart",
            )
            assert resp.status_code == 201
        sixth = warehouse_client.post(
            f"{ITEMS}{item.slug}/photos/",
            {"image": _png_upload("too-many.png")},
            format="multipart",
        )
        assert sixth.status_code == 400
        assert sixth.json()["detail"] == "An item can have at most 5 photos."

    def test_delete_photo(self, warehouse_client, test_org, warehouse):
        item = Item.objects.create(
            org=test_org, warehouse=warehouse, name="A4 paper", unit="ream"
        )
        created = warehouse_client.post(
            f"{ITEMS}{item.slug}/photos/",
            {"image": _png_upload()},
            format="multipart",
        )
        slug = created.json()["slug"]
        deleted = warehouse_client.delete(f"{ITEMS}{item.slug}/photos/{slug}/")
        assert deleted.status_code == 204
        assert ItemPhoto.objects.filter(slug=slug).count() == 0

    def test_file_requires_login(self, api_client, warehouse_client, test_org, warehouse):
        item = Item.objects.create(
            org=test_org, warehouse=warehouse, name="A4 paper", unit="ream"
        )
        created = warehouse_client.post(
            f"{ITEMS}{item.slug}/photos/",
            {"image": _png_upload("aisle-bin.png")},
            format="multipart",
        )
        photo_slug = created.json()["slug"]
        url = f"{ITEMS}{item.slug}/photos/{photo_slug}/file/"
        assert api_client.get(url).status_code == 401

    def test_file_forbidden_for_space_incharge(
        self, assigned_space_client, warehouse_client, test_org, warehouse
    ):
        item = Item.objects.create(
            org=test_org, warehouse=warehouse, name="A4 paper", unit="ream"
        )
        created = warehouse_client.post(
            f"{ITEMS}{item.slug}/photos/",
            {"image": _png_upload("aisle-bin.png")},
            format="multipart",
        )
        photo_slug = created.json()["slug"]
        url = f"{ITEMS}{item.slug}/photos/{photo_slug}/file/"
        assert assigned_space_client.get(url).status_code == 403

    def test_file_other_org_not_found(self, warehouse_client, warehouse):
        other_org = Organization.objects.create(name="Other", org_suffix="other_media")
        other_wh = Warehouse.objects.create(org=other_org, name="Elsewhere")
        other_item = Item.objects.create(
            org=other_org, warehouse=other_wh, name="Secret", unit="pcs"
        )
        url = f"{ITEMS}{other_item.slug}/photos/missing/file/"
        assert warehouse_client.get(url).status_code == 404

    def test_file_returns_webp(
        self, warehouse_client, ops_client, test_org, warehouse
    ):
        item = Item.objects.create(
            org=test_org, warehouse=warehouse, name="A4 paper", unit="ream"
        )
        created = warehouse_client.post(
            f"{ITEMS}{item.slug}/photos/",
            {"image": _png_upload("aisle-bin.png")},
            format="multipart",
        )
        photo_slug = created.json()["slug"]
        url = f"{ITEMS}{item.slug}/photos/{photo_slug}/file/"
        response = ops_client.get(url)
        assert response.status_code == 200
        assert response["Content-Type"] == "image/webp"
        body = b"".join(response.streaming_content)
        assert body[:4] == b"RIFF"
        assert body[8:12] == b"WEBP"
