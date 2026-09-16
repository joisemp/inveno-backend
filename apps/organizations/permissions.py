"""
DRF permission classes for organisation-scoped endpoints.

IsCentralAdmin — caller must be a central admin of an active organisation.
"""
from rest_framework.permissions import BasePermission

from apps.users.models import UserProfile


class IsCentralAdmin(BasePermission):
    """
    Allow only authenticated central admins whose organisation is active.

    Super admins have no org, warehouse managers are not central admins,
    and a suspended org is treated as forbidden (403).
    """

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not user or not user.is_authenticated:
            return False
        try:
            profile = user.profile
        except UserProfile.DoesNotExist:
            return False
        if profile.user_type != UserProfile.UserType.CENTRAL_ADMIN:
            return False
        org = profile.org
        return org is not None and org.is_active
