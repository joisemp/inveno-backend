"""
Shared pytest fixtures for the Inveno test suite.

Fixtures
--------
api_client      — unauthenticated DRF APIClient
test_org        — an active Organization
test_user       — a central-admin User (with profile linked to test_org)
auth_client     — DRF client authenticated as test_user via JWT
superuser       — a staff/superuser with a super_admin profile (auto-created
                  by the post_save signal)
superuser_client— DRF client authenticated as the superuser
"""
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

User = get_user_model()


@pytest.fixture
def api_client():
    """Unauthenticated DRF test client."""
    return APIClient()


@pytest.fixture
def test_org(db):
    """An active Organisation for use in tests."""
    from apps.organizations.models import Organization

    return Organization.objects.create(
        name="Test Organisation",
        org_suffix="test_org",
        location="Test City",
    )


@pytest.fixture
def test_user(db, test_org):
    """
    A central-admin User with a profile linked to test_org.

    Passwords are set (usable) so login tests work out of the box.
    Personal name fields live on UserProfile, not on User.
    """
    from apps.users.models import UserProfile

    user = User.objects.create_user(
        email="testuser@example.com",
        password="StrongPass123!",
    )
    UserProfile.objects.create(
        user=user,
        user_type=UserProfile.UserType.CENTRAL_ADMIN,
        first_name="Test",
        last_name="User",
        org=test_org,
    )
    return user


@pytest.fixture
def auth_client(api_client, test_user):
    """DRF test client authenticated as test_user via JWT."""
    from rest_framework_simplejwt.tokens import RefreshToken

    refresh = RefreshToken.for_user(test_user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {str(refresh.access_token)}")
    return api_client


@pytest.fixture
def superuser(db):
    """
    A superuser.

    The post_save signal auto-creates a super_admin UserProfile with org=None.
    """
    return User.objects.create_superuser(
        email="admin@example.com",
        password="AdminPass123!",
    )


@pytest.fixture
def superuser_client(api_client, superuser):
    """DRF test client authenticated as the superuser via JWT."""
    from rest_framework_simplejwt.tokens import RefreshToken

    refresh = RefreshToken.for_user(superuser)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {str(refresh.access_token)}")
    return api_client
