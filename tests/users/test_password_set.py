"""
Tests for POST /api/auth/password/set/ (welcome-email get-started flow).

Covers:
- Valid token → password set, login succeeds
- Login with unusable password fails before setting
- Invalid / tampered token rejected
- Token invalidated after password is set (used-up)
"""
import pytest
from django.contrib.auth import get_user_model
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from apps.organizations.models import Organization
from apps.users.models import UserProfile
from apps.users.tokens import password_setup_token_generator

User = get_user_model()

PASSWORD_SET_URL = "/api/auth/password/set/"
LOGIN_URL = "/api/auth/login/"


def _make_setup_link(user):
    """Return (uid, token) for the get-started link."""
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = password_setup_token_generator.make_token(user)
    return uid, token


@pytest.fixture
def pending_user(db):
    """A central-admin user with an unusable password (pre-setup state)."""
    org = Organization.objects.create(name="Pending Org", org_suffix="pending_org")
    user = User.objects.create_user(email="pending@example.com", password=None)
    user.set_unusable_password()
    user.save()
    UserProfile.objects.create(
        user=user,
        user_type=UserProfile.UserType.CENTRAL_ADMIN,
        first_name="Pending",
        last_name="Admin",
        org=org,
    )
    return user


@pytest.mark.django_db
class TestPasswordSet:
    def test_login_before_set_fails(self, api_client, pending_user):
        """User with unusable password cannot log in."""
        response = api_client.post(
            LOGIN_URL, {"email": pending_user.email, "password": "anything"}
        )
        assert response.status_code == 401

    def test_set_password_valid_token_succeeds(self, api_client, pending_user):
        uid, token = _make_setup_link(pending_user)
        response = api_client.post(
            PASSWORD_SET_URL,
            {
                "uid": uid,
                "token": token,
                "new_password": "BrandNew789!",
                "new_password2": "BrandNew789!",
            },
        )
        assert response.status_code == 200
        pending_user.refresh_from_db()
        assert pending_user.check_password("BrandNew789!")

    def test_login_after_set_succeeds(self, api_client, pending_user):
        uid, token = _make_setup_link(pending_user)
        api_client.post(
            PASSWORD_SET_URL,
            {
                "uid": uid,
                "token": token,
                "new_password": "BrandNew789!",
                "new_password2": "BrandNew789!",
            },
        )
        # Now login should work
        login = api_client.post(
            LOGIN_URL,
            {"email": pending_user.email, "password": "BrandNew789!"},
        )
        assert login.status_code == 200
        assert "access" in login.data

    def test_token_invalidated_after_use(self, api_client, pending_user):
        """Once a password is set the original token must no longer work."""
        uid, token = _make_setup_link(pending_user)
        api_client.post(
            PASSWORD_SET_URL,
            {
                "uid": uid,
                "token": token,
                "new_password": "BrandNew789!",
                "new_password2": "BrandNew789!",
            },
        )
        # Second attempt with the same token
        response = api_client.post(
            PASSWORD_SET_URL,
            {
                "uid": uid,
                "token": token,
                "new_password": "AnotherPass000!",
                "new_password2": "AnotherPass000!",
            },
        )
        assert response.status_code == 400

    def test_invalid_token_rejected(self, api_client, pending_user):
        uid = urlsafe_base64_encode(force_bytes(pending_user.pk))
        response = api_client.post(
            PASSWORD_SET_URL,
            {
                "uid": uid,
                "token": "invalid-token-value",
                "new_password": "BrandNew789!",
                "new_password2": "BrandNew789!",
            },
        )
        assert response.status_code == 400

    def test_password_mismatch_rejected(self, api_client, pending_user):
        uid, token = _make_setup_link(pending_user)
        response = api_client.post(
            PASSWORD_SET_URL,
            {
                "uid": uid,
                "token": token,
                "new_password": "BrandNew789!",
                "new_password2": "DifferentPass!",
            },
        )
        assert response.status_code == 400
