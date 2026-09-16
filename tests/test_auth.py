"""
Core authentication tests.

Covers login, token refresh, profile (GET/PATCH /me/), logout, and the
forgot-password flow.  Registration tests have been removed — accounts are
created through the org-registration service (see tests/organizations/).
"""
import pytest
from django.contrib.auth import get_user_model

User = get_user_model()

LOGIN_URL = "/api/auth/login/"
TOKEN_REFRESH_URL = "/api/auth/token/refresh/"
ME_URL = "/api/auth/me/"
LOGOUT_URL = "/api/auth/logout/"
CHANGE_PASSWORD_URL = "/api/auth/password/change/"
PASSWORD_RESET_URL = "/api/auth/password/reset/"
REGISTER_URL = "/api/auth/register/"  # should be gone (404 / 405)


@pytest.mark.django_db
class TestRegisterDisabled:
    """Public self-registration must be disabled."""

    def test_register_endpoint_gone(self, api_client):
        response = api_client.post(
            REGISTER_URL,
            {"email": "new@example.com", "password": "x", "password2": "x"},
        )
        assert response.status_code in (404, 405), (
            "Public register endpoint should no longer exist"
        )


@pytest.mark.django_db
class TestLogin:
    def test_login_success(self, api_client, test_user):
        response = api_client.post(
            LOGIN_URL, {"email": test_user.email, "password": "StrongPass123!"}
        )
        assert response.status_code == 200
        assert "access" in response.data
        assert "refresh" in response.data

    def test_login_returns_jwt_claims(self, api_client, test_user):
        """JWT payload should include user_type, org_id, org_suffix."""
        import base64
        import json

        response = api_client.post(
            LOGIN_URL, {"email": test_user.email, "password": "StrongPass123!"}
        )
        assert response.status_code == 200
        # Decode payload (middle part of access token)
        access = response.data["access"]
        payload_b64 = access.split(".")[1]
        # Add padding if needed
        payload_b64 += "=" * (4 - len(payload_b64) % 4)
        payload = json.loads(base64.b64decode(payload_b64))
        assert "user_type" in payload
        assert "org_id" in payload
        assert "org_suffix" in payload

    def test_login_wrong_password(self, api_client, test_user):
        response = api_client.post(
            LOGIN_URL, {"email": test_user.email, "password": "wrong"}
        )
        assert response.status_code == 401

    def test_login_nonexistent_email(self, api_client):
        response = api_client.post(
            LOGIN_URL, {"email": "nobody@example.com", "password": "pass"}
        )
        assert response.status_code == 401

    def test_login_inactive_org_blocked(self, api_client, test_user, test_org):
        """Central admin cannot log in if their org is suspended."""
        test_org.is_active = False
        test_org.save()
        response = api_client.post(
            LOGIN_URL, {"email": test_user.email, "password": "StrongPass123!"}
        )
        assert response.status_code == 400

    def test_login_suspended_user_blocked(self, api_client, warehouse_manager):
        """Suspended org user with the correct password gets a 400, not 401."""
        warehouse_manager.is_active = False
        warehouse_manager.save()
        response = api_client.post(
            LOGIN_URL,
            {"email": warehouse_manager.email, "password": "StrongPass123!"},
        )
        assert response.status_code == 400
        assert "account has been suspended" in str(response.data).lower()

    def test_login_suspended_user_wrong_password_is_401(
        self, api_client, warehouse_manager
    ):
        warehouse_manager.is_active = False
        warehouse_manager.save()
        response = api_client.post(
            LOGIN_URL,
            {"email": warehouse_manager.email, "password": "wrong"},
        )
        assert response.status_code == 401

    def test_login_after_unsuspend(self, api_client, warehouse_manager):
        warehouse_manager.is_active = False
        warehouse_manager.save()
        warehouse_manager.is_active = True
        warehouse_manager.save()
        response = api_client.post(
            LOGIN_URL,
            {"email": warehouse_manager.email, "password": "StrongPass123!"},
        )
        assert response.status_code == 200

    def test_refresh_rejected_after_suspend(self, api_client, warehouse_manager):
        login = api_client.post(
            LOGIN_URL,
            {"email": warehouse_manager.email, "password": "StrongPass123!"},
        )
        assert login.status_code == 200
        refresh = login.data["refresh"]
        warehouse_manager.is_active = False
        warehouse_manager.save()
        response = api_client.post(TOKEN_REFRESH_URL, {"refresh": refresh})
        assert response.status_code == 401

    def test_superuser_login_unaffected_by_inactive_org(self, api_client, superuser):
        """Superusers have no org — inactive org check must not apply to them."""
        response = api_client.post(
            LOGIN_URL, {"email": superuser.email, "password": "AdminPass123!"}
        )
        assert response.status_code == 200


@pytest.mark.django_db
class TestTokenRefresh:
    def test_refresh_success(self, api_client, test_user):
        login = api_client.post(
            LOGIN_URL, {"email": test_user.email, "password": "StrongPass123!"}
        )
        refresh = login.data["refresh"]
        response = api_client.post(TOKEN_REFRESH_URL, {"refresh": refresh})
        assert response.status_code == 200
        assert "access" in response.data


@pytest.mark.django_db
class TestMe:
    def test_get_me_returns_profile_and_org(self, auth_client, test_user):
        response = auth_client.get(ME_URL)
        assert response.status_code == 200
        data = response.data
        assert data["email"] == test_user.email
        assert data["profile"] is not None
        assert data["profile"]["user_type"] == "central_admin"
        assert data["profile"]["first_name"] == "Test"
        assert data["org"] is not None
        assert data["org"]["org_suffix"] == "test_org"

    def test_get_me_superuser_org_is_null(self, superuser_client):
        response = superuser_client.get(ME_URL)
        assert response.status_code == 200
        assert response.data["org"] is None

    def test_get_me_unauthenticated(self, api_client):
        response = api_client.get(ME_URL)
        assert response.status_code == 401

    def test_patch_me_updates_profile_name(self, auth_client, test_user):
        response = auth_client.patch(ME_URL, {"first_name": "Updated"})
        assert response.status_code == 200
        test_user.profile.refresh_from_db()
        assert test_user.profile.first_name == "Updated"

    def test_patch_me_updates_profile_phone(self, auth_client, test_user):
        response = auth_client.patch(ME_URL, {"phone": "+919876543210"})
        assert response.status_code == 200
        test_user.profile.refresh_from_db()
        assert test_user.profile.phone == "+919876543210"


@pytest.mark.django_db
class TestLogout:
    def test_logout_blacklists_refresh(self, api_client, test_user):
        login = api_client.post(
            LOGIN_URL, {"email": test_user.email, "password": "StrongPass123!"}
        )
        refresh = login.data["refresh"]
        access = login.data["access"]

        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        logout_response = api_client.post(LOGOUT_URL, {"refresh": refresh})
        assert logout_response.status_code == 200

        # Blacklisted refresh token must not be reusable
        refresh_response = api_client.post(TOKEN_REFRESH_URL, {"refresh": refresh})
        assert refresh_response.status_code == 401


@pytest.mark.django_db
class TestPasswordReset:
    def test_reset_request_existing_email(self, api_client, test_user):
        response = api_client.post(PASSWORD_RESET_URL, {"email": test_user.email})
        assert response.status_code == 200  # anti-enumeration

    def test_reset_request_nonexistent_email(self, api_client):
        response = api_client.post(PASSWORD_RESET_URL, {"email": "ghost@example.com"})
        assert response.status_code == 200  # anti-enumeration


@pytest.mark.django_db
class TestChangePassword:
    def test_change_password_success(self, auth_client, test_user):
        payload = {
            "old_password": "StrongPass123!",
            "new_password": "NewStrong456!",
            "new_password2": "NewStrong456!",
        }
        response = auth_client.post(CHANGE_PASSWORD_URL, payload)
        assert response.status_code == 200
        test_user.refresh_from_db()
        assert test_user.check_password("NewStrong456!")

    def test_change_password_wrong_old(self, auth_client):
        payload = {
            "old_password": "wrong",
            "new_password": "NewStrong456!",
            "new_password2": "NewStrong456!",
        }
        response = auth_client.post(CHANGE_PASSWORD_URL, payload)
        assert response.status_code == 400
