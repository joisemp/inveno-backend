"""Tests for Space API and space-incharge assignment."""
import pytest
from django.core.exceptions import ValidationError

from apps.organizations.models import Organization, Space
from apps.organizations.space_services import (
    ALREADY_ASSIGNED,
    create_space,
)
from apps.users.models import UserProfile

SPACES = "/api/orgs/spaces/"


def _detail(slug):
    return f"{SPACES}{slug}/"


def _incharges(slug):
    return f"{SPACES}{slug}/incharges/"


def _unassign(slug, member):
    return f"{SPACES}{slug}/incharges/{member}/unassign/"


@pytest.mark.django_db
class TestCreateSpaceService:
    def test_create(self, test_org):
        space = create_space(org=test_org, name="Kitchen", location="L1")
        assert space.slug == "kitchen"
        assert space.org == test_org

    def test_duplicate_name(self, test_org, space):
        with pytest.raises(ValidationError):
            create_space(org=test_org, name=space.name)


@pytest.mark.django_db
class TestSpaceListCreate:
    def test_create_and_list(self, auth_client):
        response = auth_client.post(
            SPACES,
            {"name": "South Wing", "location": "B2"},
            format="json",
        )
        assert response.status_code == 201
        data = response.json()
        assert data["slug"] == "south-wing"
        assert data["name"] == "South Wing"
        listed = auth_client.get(SPACES)
        assert listed.status_code == 200
        assert any(row["slug"] == "south-wing" for row in listed.json()["results"])

    def test_ops_can_list_not_create(self, ops_client, space):
        listed = ops_client.get(SPACES)
        assert listed.status_code == 200
        created = ops_client.post(SPACES, {"name": "Denied"}, format="json")
        assert created.status_code == 403

    def test_assigned_incharge_sees_own_space(self, assigned_space_client, space):
        listed = assigned_space_client.get(SPACES)
        assert listed.status_code == 200
        slugs = [row["slug"] for row in listed.json()["results"]]
        assert slugs == [space.slug]

    def test_unassigned_incharge_empty_list(self, space_incharge_client, space):
        listed = space_incharge_client.get(SPACES)
        assert listed.status_code == 200
        assert listed.json()["results"] == []

    def test_warehouse_forbidden(self, warehouse_client):
        assert warehouse_client.get(SPACES).status_code == 403

    def test_space_incharge_cannot_create(self, assigned_space_client):
        assert (
            assigned_space_client.post(SPACES, {"name": "X"}, format="json").status_code
            == 403
        )

    def test_duplicate_name(self, auth_client, space):
        response = auth_client.post(SPACES, {"name": space.name}, format="json")
        assert response.status_code == 400
        assert "name" in response.json()

    def test_unauthenticated(self, api_client):
        assert api_client.get(SPACES).status_code == 401


@pytest.mark.django_db
class TestSpaceRetrieveUpdate:
    def test_get_and_patch(self, auth_client, space):
        got = auth_client.get(_detail(space.slug))
        assert got.status_code == 200
        patched = auth_client.patch(
            _detail(space.slug), {"location": "Moved"}, format="json"
        )
        assert patched.status_code == 200
        assert patched.json()["location"] == "Moved"

    def test_ops_get_not_patch(self, ops_client, space):
        assert ops_client.get(_detail(space.slug)).status_code == 200
        assert (
            ops_client.patch(
                _detail(space.slug), {"location": "Nope"}, format="json"
            ).status_code
            == 403
        )


@pytest.mark.django_db
class TestSpaceSuspend:
    def test_suspend_unsuspend(self, auth_client, space):
        sus = auth_client.post(_detail(space.slug) + "suspend/", format="json")
        assert sus.status_code == 200
        space.refresh_from_db()
        assert space.is_active is False
        uns = auth_client.post(_detail(space.slug) + "unsuspend/", format="json")
        assert uns.status_code == 200
        space.refresh_from_db()
        assert space.is_active is True

    def test_ops_cannot_suspend(self, ops_client, space):
        assert (
            ops_client.post(_detail(space.slug) + "suspend/", format="json").status_code
            == 403
        )


@pytest.mark.django_db
class TestAssignIncharge:
    def test_assign_and_list(self, auth_client, space, space_incharge):
        response = auth_client.post(
            _incharges(space.slug),
            {"member": space_incharge.profile.slug},
            format="json",
        )
        assert response.status_code == 200
        data = response.json()
        assert data["space"]["slug"] == space.slug
        listed = auth_client.get(_incharges(space.slug))
        assert listed.status_code == 200
        assert any(row["slug"] == space_incharge.profile.slug for row in listed.json())

    def test_wrong_role(self, auth_client, space, warehouse_manager):
        response = auth_client.post(
            _incharges(space.slug),
            {"member": warehouse_manager.profile.slug},
            format="json",
        )
        assert response.status_code == 400
        assert "member" in response.json()

    def test_already_assigned(self, auth_client, space, assigned_space_incharge):
        response = auth_client.post(
            _incharges(space.slug),
            {"member": assigned_space_incharge.profile.slug},
            format="json",
        )
        assert response.status_code == 400
        assert response.json()["detail"] == ALREADY_ASSIGNED

    def test_unassign(self, auth_client, space, assigned_space_incharge):
        response = auth_client.post(
            _unassign(space.slug, assigned_space_incharge.profile.slug),
            format="json",
        )
        assert response.status_code == 200
        assigned_space_incharge.profile.refresh_from_db()
        assert assigned_space_incharge.profile.space_id is None

    def test_ops_cannot_assign(self, ops_client, space, space_incharge):
        assert (
            ops_client.post(
                _incharges(space.slug),
                {"member": space_incharge.profile.slug},
                format="json",
            ).status_code
            == 403
        )


@pytest.mark.django_db
class TestSpaceProfileClean:
    def test_central_admin_cannot_have_space(self, test_user, space):
        test_user.profile.space = space
        with pytest.raises(ValidationError, match="Only a space incharge"):
            test_user.profile.clean()

    def test_space_must_match_org(self, space_incharge):
        other_org = Organization.objects.create(name="Other", org_suffix="other_org")
        other = Space.objects.create(org=other_org, name="Elsewhere")
        space_incharge.profile.space = other
        with pytest.raises(ValidationError, match="same organisation"):
            space_incharge.profile.clean()


@pytest.mark.django_db
class TestSpaceInchargeVendorsForbidden:
    def test_cannot_list_vendors(self, space_incharge_client):
        assert space_incharge_client.get("/api/orgs/vendors/").status_code == 403

    def test_ops_can_list_vendors(self, ops_client):
        assert ops_client.get("/api/orgs/vendors/").status_code == 200
