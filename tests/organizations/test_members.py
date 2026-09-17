"""
Tests for organisation member API and create_org_user().

Covers:
- Service: both assignable roles, duplicate email, rejected super_admin, email
- API: list/create/resend by slug
- 401 / 403 (warehouse manager, superuser, inactive org) / 404 / 400
"""
import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.organizations.models import Organization
from apps.organizations.services import (
    ALREADY_SET_PASSWORD,
    ALREADY_SUSPENDED,
    CANNOT_SUSPEND_SELF,
    DUPLICATE_EMAIL,
    INVALID_USER_TYPE,
    NOT_SUSPENDED,
    USER_SUSPENDED,
    USER_UNSUSPENDED,
    create_org_user,
    create_org_with_central_admin,
    suspend_org_user,
    unsuspend_org_user,
)
from apps.users.models import UserProfile

User = get_user_model()

MEMBERS_URL = "/api/orgs/members/"


def _payload(**overrides):
    data = {
        "email": "alice@acme.com",
        "first_name": "Alice",
        "last_name": "Smith",
        "phone": "+15551234",
        "user_type": "warehouse_manager",
    }
    data.update(overrides)
    return data


def _resend_url(slug: str) -> str:
    return f"{MEMBERS_URL}{slug}/resend-welcome/"


def _suspend_url(slug: str) -> str:
    return f"{MEMBERS_URL}{slug}/suspend/"


def _unsuspend_url(slug: str) -> str:
    return f"{MEMBERS_URL}{slug}/unsuspend/"


@pytest.mark.django_db
class TestCreateOrgUser:
    def test_creates_warehouse_manager(self, test_org):
        user = create_org_user(
            org=test_org,
            email="wm@example.com",
            first_name="W",
            last_name="M",
            user_type=UserProfile.UserType.WAREHOUSE_MANAGER,
            send_email=False,
        )
        assert not user.has_usable_password()
        assert not user.is_staff
        assert user.profile.user_type == UserProfile.UserType.WAREHOUSE_MANAGER
        assert user.profile.org == test_org
        assert user.profile.slug == "w-m"

    def test_creates_central_admin(self, test_org):
        user = create_org_user(
            org=test_org,
            email="ca2@example.com",
            first_name="Second",
            last_name="Admin",
            user_type=UserProfile.UserType.CENTRAL_ADMIN,
            send_email=False,
        )
        assert user.profile.user_type == UserProfile.UserType.CENTRAL_ADMIN

    def test_sends_welcome_email(self, test_org):
        create_org_user(
            org=test_org,
            email="new@example.com",
            first_name="New",
            last_name="User",
            user_type=UserProfile.UserType.WAREHOUSE_MANAGER,
            send_email=True,
        )
        assert len(mail.outbox) == 1
        assert "new@example.com" in mail.outbox[0].to

    def test_duplicate_email_rejected(self, test_org, test_user):
        with pytest.raises(ValidationError) as exc:
            create_org_user(
                org=test_org,
                email=test_user.email,
                first_name="Dup",
                last_name="User",
                user_type=UserProfile.UserType.CENTRAL_ADMIN,
                send_email=False,
            )
        assert DUPLICATE_EMAIL in exc.value.messages

    def test_super_admin_type_rejected(self, test_org):
        with pytest.raises(ValidationError) as exc:
            create_org_user(
                org=test_org,
                email="evil@example.com",
                first_name="No",
                last_name="Way",
                user_type=UserProfile.UserType.SUPER_ADMIN,
                send_email=False,
            )
        assert INVALID_USER_TYPE in exc.value.messages
        assert not User.objects.filter(email="evil@example.com").exists()


@pytest.mark.django_db
class TestOrgMemberListCreate:
    def test_list_members(self, auth_client, test_user, warehouse_manager):
        response = auth_client.get(MEMBERS_URL)
        assert response.status_code == 200
        body = response.json()
        slugs = {row["slug"] for row in body["results"]}
        assert test_user.profile.slug in slugs
        assert warehouse_manager.profile.slug in slugs
        for row in body["results"]:
            assert "id" not in row
            assert "slug" in row

    def test_create_warehouse_manager(self, auth_client, test_org):
        response = auth_client.post(MEMBERS_URL, _payload(), format="json")
        assert response.status_code == 201
        data = response.json()
        assert data["slug"] == "alice-smith"
        assert data["email"] == "alice@acme.com"
        assert data["user_type"] == "warehouse_manager"
        assert data["has_usable_password"] is False
        assert "id" not in data
        assert len(mail.outbox) == 1
        profile = UserProfile.objects.get(slug="alice-smith")
        assert profile.org == test_org
        assert data["space"] is None

    def test_create_space_incharge_without_space(self, auth_client):
        response = auth_client.post(
            MEMBERS_URL,
            _payload(
                email="space@acme.com",
                first_name="Space",
                last_name="Lead",
                user_type="space_incharge",
            ),
            format="json",
        )
        assert response.status_code == 201
        data = response.json()
        assert data["user_type"] == "space_incharge"
        assert data["space"] is None

    def test_create_operation_incharge(self, auth_client):
        response = auth_client.post(
            MEMBERS_URL,
            _payload(
                email="ops@acme.com",
                first_name="Op",
                last_name="Lead",
                user_type="operation_incharge",
            ),
            format="json",
        )
        assert response.status_code == 201
        assert response.json()["user_type"] == "operation_incharge"

    def test_create_central_admin(self, auth_client):
        response = auth_client.post(
            MEMBERS_URL,
            _payload(
                email="second@acme.com",
                first_name="Second",
                last_name="Admin",
                user_type="central_admin",
            ),
            format="json",
        )
        assert response.status_code == 201
        assert response.json()["user_type"] == "central_admin"
        assert response.json()["slug"] == "second-admin"

    def test_duplicate_email(self, auth_client, test_user):
        response = auth_client.post(
            MEMBERS_URL,
            _payload(email=test_user.email),
            format="json",
        )
        assert response.status_code == 400
        assert response.json()["email"] == [DUPLICATE_EMAIL]

    def test_super_admin_user_type_rejected(self, auth_client):
        response = auth_client.post(
            MEMBERS_URL,
            _payload(user_type="super_admin"),
            format="json",
        )
        assert response.status_code == 400
        assert "user_type" in response.json()

    def test_unauthenticated(self):
        client = APIClient()
        assert client.get(MEMBERS_URL).status_code == 401
        assert client.post(MEMBERS_URL, _payload(), format="json").status_code == 401

    def test_warehouse_manager_forbidden(self, warehouse_client):
        assert warehouse_client.get(MEMBERS_URL).status_code == 403
        assert warehouse_client.post(MEMBERS_URL, _payload(), format="json").status_code == 403

    def test_ops_forbidden(self, ops_client):
        assert ops_client.get(MEMBERS_URL).status_code == 403

    def test_space_incharge_forbidden(self, space_incharge_client):
        assert space_incharge_client.get(MEMBERS_URL).status_code == 403

    def test_superuser_forbidden(self, superuser_client):
        assert superuser_client.get(MEMBERS_URL).status_code == 403
        assert superuser_client.post(MEMBERS_URL, _payload(), format="json").status_code == 403

    def test_inactive_org_forbidden(self, auth_client, test_org):
        test_org.is_active = False
        test_org.save()
        assert auth_client.get(MEMBERS_URL).status_code == 403
        assert auth_client.post(MEMBERS_URL, _payload(), format="json").status_code == 403

    def test_list_status_active(self, auth_client, test_user, warehouse_manager):
        warehouse_manager.is_active = False
        warehouse_manager.save()
        response = auth_client.get(MEMBERS_URL, {"status": "active"})
        assert response.status_code == 200
        slugs = {row["slug"] for row in response.json()["results"]}
        assert test_user.profile.slug in slugs
        assert warehouse_manager.profile.slug not in slugs

    def test_list_status_suspended(self, auth_client, test_user, warehouse_manager):
        warehouse_manager.is_active = False
        warehouse_manager.save()
        response = auth_client.get(MEMBERS_URL, {"status": "suspended"})
        assert response.status_code == 200
        slugs = {row["slug"] for row in response.json()["results"]}
        assert warehouse_manager.profile.slug in slugs
        assert test_user.profile.slug not in slugs
        assert all(row["is_active"] is False for row in response.json()["results"])

    def test_list_invalid_status(self, auth_client):
        response = auth_client.get(MEMBERS_URL, {"status": "nope"})
        assert response.status_code == 400
        assert "status" in response.json()


@pytest.mark.django_db
class TestOrgMemberResendWelcome:
    def test_resend_by_slug(self, auth_client, test_org):
        user = create_org_user(
            org=test_org,
            email="pending@example.com",
            first_name="Pending",
            last_name="User",
            user_type=UserProfile.UserType.WAREHOUSE_MANAGER,
            send_email=False,
        )
        mail.outbox.clear()
        response = auth_client.post(_resend_url(user.profile.slug), format="json")
        assert response.status_code == 200
        assert response.json() == {"detail": "Welcome email sent."}
        assert len(mail.outbox) == 1
        assert "pending@example.com" in mail.outbox[0].to

    def test_already_set_password(self, auth_client, test_user):
        response = auth_client.post(
            _resend_url(test_user.profile.slug), format="json"
        )
        assert response.status_code == 400
        assert response.json() == {"detail": ALREADY_SET_PASSWORD}

    def test_unknown_slug(self, auth_client):
        response = auth_client.post(_resend_url("does-not-exist"), format="json")
        assert response.status_code == 404
        assert response.json() == {"detail": "Not found."}

    def test_other_org_slug_not_found(self, auth_client):
        other_org = Organization.objects.create(
            name="Other Org", org_suffix="other_org"
        )
        other = create_org_user(
            org=other_org,
            email="other@example.com",
            first_name="Other",
            last_name="Person",
            user_type=UserProfile.UserType.CENTRAL_ADMIN,
            send_email=False,
        )
        response = auth_client.post(
            _resend_url(other.profile.slug), format="json"
        )
        assert response.status_code == 404

    def test_warehouse_manager_forbidden(self, warehouse_client, test_user):
        response = warehouse_client.post(
            _resend_url(test_user.profile.slug), format="json"
        )
        assert response.status_code == 403

    def test_superuser_forbidden(self, superuser_client, test_user):
        response = superuser_client.post(
            _resend_url(test_user.profile.slug), format="json"
        )
        assert response.status_code == 403

    def test_unauthenticated(self, test_user):
        client = APIClient()
        response = client.post(_resend_url(test_user.profile.slug), format="json")
        assert response.status_code == 401

    def test_inactive_org_forbidden(self, auth_client, test_org, test_user):
        test_org.is_active = False
        test_org.save()
        assert auth_client.post(
            _resend_url(test_user.profile.slug), format="json"
        ).status_code == 403


@pytest.mark.django_db
class TestSetOrgUserActive:
    def test_suspend_and_unsuspend(self, test_org, warehouse_manager, test_user):
        suspend_org_user(
            org=test_org,
            slug=warehouse_manager.profile.slug,
            acting_user=test_user,
        )
        warehouse_manager.refresh_from_db()
        assert warehouse_manager.is_active is False

        unsuspend_org_user(
            org=test_org,
            slug=warehouse_manager.profile.slug,
            acting_user=test_user,
        )
        warehouse_manager.refresh_from_db()
        assert warehouse_manager.is_active is True

    def test_cannot_suspend_self(self, test_org, test_user):
        with pytest.raises(ValidationError) as exc:
            suspend_org_user(
                org=test_org,
                slug=test_user.profile.slug,
                acting_user=test_user,
            )
        assert CANNOT_SUSPEND_SELF in exc.value.messages

    def test_other_org_slug_missing(self, test_org, test_user):
        other_org = Organization.objects.create(
            name="Other Org", org_suffix="other_org_suspend"
        )
        other = create_org_user(
            org=other_org,
            email="outsider@example.com",
            first_name="Out",
            last_name="Sider",
            user_type=UserProfile.UserType.WAREHOUSE_MANAGER,
            send_email=False,
        )
        with pytest.raises(UserProfile.DoesNotExist):
            suspend_org_user(
                org=test_org,
                slug=other.profile.slug,
                acting_user=test_user,
            )


@pytest.mark.django_db
class TestOrgMemberSuspendUnsuspend:
    def test_suspend_by_slug(self, auth_client, warehouse_manager):
        response = auth_client.post(
            _suspend_url(warehouse_manager.profile.slug), format="json"
        )
        assert response.status_code == 200
        assert response.json() == {"detail": USER_SUSPENDED}
        warehouse_manager.refresh_from_db()
        assert warehouse_manager.is_active is False

    def test_unsuspend_by_slug(self, auth_client, warehouse_manager):
        warehouse_manager.is_active = False
        warehouse_manager.save()
        response = auth_client.post(
            _unsuspend_url(warehouse_manager.profile.slug), format="json"
        )
        assert response.status_code == 200
        assert response.json() == {"detail": USER_UNSUSPENDED}
        warehouse_manager.refresh_from_db()
        assert warehouse_manager.is_active is True

    def test_already_suspended(self, auth_client, warehouse_manager):
        warehouse_manager.is_active = False
        warehouse_manager.save()
        response = auth_client.post(
            _suspend_url(warehouse_manager.profile.slug), format="json"
        )
        assert response.status_code == 400
        assert response.json() == {"detail": ALREADY_SUSPENDED}

    def test_already_active(self, auth_client, warehouse_manager):
        response = auth_client.post(
            _unsuspend_url(warehouse_manager.profile.slug), format="json"
        )
        assert response.status_code == 400
        assert response.json() == {"detail": NOT_SUSPENDED}

    def test_cannot_suspend_self(self, auth_client, test_user):
        response = auth_client.post(
            _suspend_url(test_user.profile.slug), format="json"
        )
        assert response.status_code == 400
        assert response.json() == {"detail": CANNOT_SUSPEND_SELF}

    def test_unknown_slug(self, auth_client):
        assert auth_client.post(
            _suspend_url("does-not-exist"), format="json"
        ).status_code == 404

    def test_other_org_slug_not_found(self, auth_client):
        other_org = Organization.objects.create(
            name="Other Org", org_suffix="other_org_api"
        )
        other = create_org_user(
            org=other_org,
            email="other2@example.com",
            first_name="Other",
            last_name="Two",
            user_type=UserProfile.UserType.WAREHOUSE_MANAGER,
            send_email=False,
        )
        assert auth_client.post(
            _suspend_url(other.profile.slug), format="json"
        ).status_code == 404

    def test_warehouse_manager_forbidden(self, warehouse_client, test_user):
        assert warehouse_client.post(
            _suspend_url(test_user.profile.slug), format="json"
        ).status_code == 403

    def test_superuser_forbidden(self, superuser_client, warehouse_manager):
        assert superuser_client.post(
            _suspend_url(warehouse_manager.profile.slug), format="json"
        ).status_code == 403

    def test_unauthenticated(self, warehouse_manager):
        client = APIClient()
        assert client.post(
            _suspend_url(warehouse_manager.profile.slug), format="json"
        ).status_code == 401

    def test_inactive_org_forbidden(self, auth_client, test_org, warehouse_manager):
        test_org.is_active = False
        test_org.save()
        assert auth_client.post(
            _suspend_url(warehouse_manager.profile.slug), format="json"
        ).status_code == 403


@pytest.mark.django_db
def test_create_org_with_central_admin_still_works():
    """Extraction must not change org registration behaviour."""
    org, user = create_org_with_central_admin(
        org_name="Keep Working",
        org_suffix="keep_working",
        admin_email="keep@example.com",
        admin_first_name="Keep",
        admin_last_name="Working",
        send_email=False,
    )
    assert org.org_suffix == "keep_working"
    assert user.profile.user_type == UserProfile.UserType.CENTRAL_ADMIN
    assert user.profile.slug == "keep-working"
