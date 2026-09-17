"""
DRF permission classes for organisation-scoped endpoints.

IsCentralAdmin      — central admin of an active organisation.
IsOrgUser           — any org-assignable role of an active organisation.
IsVendorManager     — central admin, operation incharge, or warehouse manager.
IsCentralAdminOrOps — central admin or operation incharge.
IsSpaceViewer       — central admin, operation incharge, or space incharge.
IsItemReader / IsItemWriter — inventory catalog access.
IsWarehouseReceiver — warehouse manager or central admin.
"""
from rest_framework.permissions import BasePermission

from apps.users.models import UserProfile


def _active_org_profile(user):
    """Return (profile, org) or (None, None) when the caller is not an org user."""
    if not user or not user.is_authenticated:
        return None, None
    try:
        profile = user.profile
    except UserProfile.DoesNotExist:
        return None, None
    org = profile.org
    if org is None or not org.is_active:
        return None, None
    return profile, org


class _OrgRolePermission(BasePermission):
    """Allow authenticated org users whose user_type is in allowed_types."""

    allowed_types = frozenset()

    def has_permission(self, request, view) -> bool:
        profile, org = _active_org_profile(request.user)
        if profile is None:
            return False
        return profile.user_type in self.allowed_types


class IsCentralAdmin(_OrgRolePermission):
    """
    Allow only authenticated central admins whose organisation is active.

    Super admins have no org, other org roles are denied, and a suspended
    org is treated as forbidden (403).
    """

    allowed_types = frozenset({UserProfile.UserType.CENTRAL_ADMIN})


class IsOrgUser(_OrgRolePermission):
    """Allow any org-assignable role of an active organisation."""

    allowed_types = UserProfile.ORG_ASSIGNABLE_TYPES


class IsVendorManager(_OrgRolePermission):
    """Allow vendor CRUD: not space_incharge."""

    allowed_types = UserProfile.VENDOR_ACCESS_TYPES


class IsCentralAdminOrOps(_OrgRolePermission):
    """Allow purchase operations after a request exists (and ops-created PRs)."""

    allowed_types = UserProfile.PURCHASE_OPERATOR_TYPES


class IsSpaceViewer(_OrgRolePermission):
    """Allow GET on spaces: central admin, ops, or space incharge."""

    allowed_types = UserProfile.SPACE_VIEW_TYPES


class IsItemReader(_OrgRolePermission):
    """Allow listing the item catalog."""

    allowed_types = UserProfile.ITEM_READ_TYPES


class IsItemWriter(_OrgRolePermission):
    """Allow creating/updating catalog items (not ops)."""

    allowed_types = UserProfile.ITEM_WRITE_TYPES


class IsPurchaseRequester(_OrgRolePermission):
    """Allow creating/listing PRs: space incharge, ops, or central admin."""

    allowed_types = frozenset(
        {
            UserProfile.UserType.CENTRAL_ADMIN,
            UserProfile.UserType.OPERATION_INCHARGE,
            UserProfile.UserType.SPACE_INCHARGE,
        }
    )


class IsWarehouseReceiver(_OrgRolePermission):
    """Allow warehouse inbound receiving."""

    allowed_types = UserProfile.ITEM_WRITE_TYPES
