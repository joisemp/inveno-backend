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
    DUPLICATE_EMAIL,
    INVALID_USER_TYPE,
    create_org_user,
    create_org_with_central_admin,
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

    def test_superuser_forbidden(self, superuser_client):
        assert superuser_client.get(MEMBERS_URL).status_code == 403
        assert superuser_client.post(MEMBERS_URL, _payload(), format="json").status_code == 403

    def test_inactive_org_forbidden(self, auth_client, test_org):
        test_org.is_active = False
        test_org.save()
        assert auth_client.get(MEMBERS_URL).status_code == 403
        assert auth_client.post(MEMBERS_URL, _payload(), format="json").status_code == 403


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
        response = auth_client.post(
            _resend_url(test_user.profile.slug), format="json"
        )
        assert response.status_code == 403


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
