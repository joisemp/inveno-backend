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
superuser_client   — DRF client authenticated as the superuser
warehouse_manager  — a warehouse-manager User linked to test_org
warehouse_client   — DRF client authenticated as warehouse_manager
operation_incharge — an operation-incharge User linked to test_org
ops_client         — DRF client authenticated as operation_incharge
space              — an active Space in test_org
warehouse          — default Warehouse named "Warehouse" in test_org
space_incharge     — unassigned space_incharge User
space_incharge_client — JWT client for space_incharge
assigned_space_incharge — space_incharge linked to space
assigned_space_client — JWT client for assigned_space_incharge
"""
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

User = get_user_model()


def _jwt_client(user):
    """Return a fresh APIClient so concurrent role fixtures do not share JWTs."""
    from rest_framework_simplejwt.tokens import RefreshToken

    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {str(refresh.access_token)}")
    return client


@pytest.fixture
def api_client():
    """Unauthenticated DRF test client."""
    return APIClient()


@pytest.fixture
def test_org(db):
    """An active Organisation with a default warehouse."""
    from apps.inventory.models import Warehouse
    from apps.organizations.models import Organization

    org = Organization.objects.create(
        name="Test Organisation",
        org_suffix="test_org",
        location="Test City",
    )
    Warehouse.objects.create(org=org, name="Warehouse")
    return org


@pytest.fixture
def warehouse(db, test_org):
    """Default warehouse for test_org (created if missing)."""
    from apps.inventory.models import Warehouse

    obj, _created = Warehouse.objects.get_or_create(
        org=test_org, name="Warehouse", defaults={"location": ""}
    )
    return obj


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
def auth_client(test_user):
    """DRF test client authenticated as test_user via JWT."""
    return _jwt_client(test_user)


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
def superuser_client(superuser):
    """DRF test client authenticated as the superuser via JWT."""
    return _jwt_client(superuser)


@pytest.fixture
def warehouse_manager(db, test_org):
    """A warehouse-manager User with a profile linked to test_org."""
    from apps.users.models import UserProfile

    user = User.objects.create_user(
        email="warehouse@example.com",
        password="StrongPass123!",
    )
    UserProfile.objects.create(
        user=user,
        user_type=UserProfile.UserType.WAREHOUSE_MANAGER,
        first_name="Ware",
        last_name="House",
        org=test_org,
    )
    return user


@pytest.fixture
def warehouse_client(warehouse_manager):
    """DRF test client authenticated as warehouse_manager via JWT."""
    return _jwt_client(warehouse_manager)


@pytest.fixture
def operation_incharge(db, test_org):
    """An operation-incharge User with a profile linked to test_org."""
    from apps.users.models import UserProfile

    user = User.objects.create_user(
        email="ops@example.com",
        password="StrongPass123!",
    )
    UserProfile.objects.create(
        user=user,
        user_type=UserProfile.UserType.OPERATION_INCHARGE,
        first_name="Op",
        last_name="Incharge",
        org=test_org,
    )
    return user


@pytest.fixture
def ops_client(operation_incharge):
    """DRF test client authenticated as operation_incharge via JWT."""
    return _jwt_client(operation_incharge)


@pytest.fixture
def space(db, test_org):
    """An active Space in test_org."""
    from apps.organizations.models import Space

    return Space.objects.create(
        org=test_org,
        name="North Wing",
        location="Building A",
    )


@pytest.fixture
def space_incharge(db, test_org):
    """An unassigned space_incharge User linked to test_org."""
    from apps.users.models import UserProfile

    user = User.objects.create_user(
        email="space@example.com",
        password="StrongPass123!",
    )
    UserProfile.objects.create(
        user=user,
        user_type=UserProfile.UserType.SPACE_INCHARGE,
        first_name="Space",
        last_name="Incharge",
        org=test_org,
    )
    return user


@pytest.fixture
def space_incharge_client(space_incharge):
    """DRF test client authenticated as an unassigned space_incharge."""
    return _jwt_client(space_incharge)


@pytest.fixture
def assigned_space_incharge(db, test_org, space):
    """A space_incharge assigned to *space*."""
    from apps.users.models import UserProfile

    user = User.objects.create_user(
        email="assigned-space@example.com",
        password="StrongPass123!",
    )
    UserProfile.objects.create(
        user=user,
        user_type=UserProfile.UserType.SPACE_INCHARGE,
        first_name="Assigned",
        last_name="Incharge",
        org=test_org,
        space=space,
    )
    return user


@pytest.fixture
def assigned_space_client(assigned_space_incharge):
    """DRF test client authenticated as assigned_space_incharge."""
    return _jwt_client(assigned_space_incharge)
