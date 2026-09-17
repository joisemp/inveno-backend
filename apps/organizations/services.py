"""
Organisation registration and member-provisioning services.

create_org_with_central_admin() registers a new Organisation together with
its first central admin.

create_org_user() adds a user to an existing org (any org-assignable role)
and optionally sends the welcome / get-started email.

resend_org_user_welcome() re-sends that email for a member who has not set a
password yet.

set_org_user_active() suspends or unsuspends a member (User.is_active).

Everything that writes to the DB runs in one atomic transaction so a failure
rolls back all changes.
"""
import logging

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.organizations.models import Organization
from apps.users.models import UserProfile

logger = logging.getLogger(__name__)
User = get_user_model()

ALREADY_SET_PASSWORD = "This user has already set a password."
DUPLICATE_EMAIL = "A user with this email already exists."
INVALID_USER_TYPE = "Cannot assign this user type."
ALREADY_SUSPENDED = "This user is already suspended."
NOT_SUSPENDED = "This user is not suspended."
CANNOT_SUSPEND_SELF = "You cannot suspend your own account."
USER_SUSPENDED = "User suspended."
USER_UNSUSPENDED = "User unsuspended."


@transaction.atomic
def create_org_user(
    *,
    org: Organization,
    email: str,
    first_name: str,
    last_name: str,
    phone: str = "",
    user_type: str,
    send_email: bool = True,
):
    """
    Create a non-staff User + UserProfile linked to *org*.

    The user is created with an unusable password.  They set it via the
    welcome-email get-started link (POST /api/auth/password/set/).

    *user_type* must be one of UserProfile.ORG_ASSIGNABLE_TYPES
    (central_admin, operation_incharge, warehouse_manager, space_incharge).
    super_admin is rejected.

    Returns the User.

    Raises
    ------
    ValidationError  — duplicate email or disallowed user_type.
    """
    if user_type not in UserProfile.ORG_ASSIGNABLE_TYPES:
        raise ValidationError({"user_type": INVALID_USER_TYPE})

    if User.objects.filter(email=email).exists():
        raise ValidationError({"email": DUPLICATE_EMAIL})

    user = User.objects.create_user(
        email=email,
        password=None,
        is_staff=False,
        is_superuser=False,
        is_active=True,
    )
    user.set_unusable_password()
    user.save()

    UserProfile.objects.create(
        user=user,
        user_type=user_type,
        first_name=first_name,
        last_name=last_name,
        phone=phone,
        org=org,
    )

    logger.info(
        "Created %s '%s' for org '%s'",
        user_type,
        email,
        org.org_suffix,
    )

    if send_email:
        from apps.users.emails import send_welcome_email  # noqa: PLC0415

        send_welcome_email(user)

    return user


@transaction.atomic
def create_org_with_central_admin(
    *,
    org_name: str,
    org_suffix: str,
    location: str = "",
    admin_email: str,
    admin_first_name: str,
    admin_last_name: str,
    admin_phone: str = "",
    send_email: bool = True,
) -> tuple:
    """
    Register an Organisation and its first central admin in one transaction.

    Steps
    -----
    1. Create Organisation (slug auto-generated).
    2. Delegate user + profile + optional welcome email to create_org_user().

    Returns
    -------
    (Organization, User) tuple.

    Raises
    ------
    IntegrityError  — if org_suffix is already taken.
    ValidationError — if admin_email is already taken.
    Any exception from send_welcome_email propagates (wrapped in the
    atomic transaction so DB changes are rolled back).
    """
    org = Organization.objects.create(
        name=org_name,
        org_suffix=org_suffix,
        location=location,
    )

    user = create_org_user(
        org=org,
        email=admin_email,
        first_name=admin_first_name,
        last_name=admin_last_name,
        phone=admin_phone,
        user_type=UserProfile.UserType.CENTRAL_ADMIN,
        send_email=send_email,
    )

    logger.info(
        "Created org '%s' (%s) with central admin '%s'",
        org_name,
        org_suffix,
        admin_email,
    )

    return org, user


def get_org_member_profile(*, org: Organization, slug: str) -> UserProfile:
    """
    Return the UserProfile for *slug* in *org*.

    Raises UserProfile.DoesNotExist when the slug is unknown or belongs
    to a different organisation.
    """
    return UserProfile.objects.select_related("user").get(org=org, slug=slug)


def resend_org_user_welcome(*, org: Organization, slug: str):
    """
    Re-send the welcome / get-started email for a member identified by slug.

    Raises
    ------
    UserProfile.DoesNotExist — unknown slug or not in *org*.
    ValidationError          — the user already has a usable password.
    """
    profile = get_org_member_profile(org=org, slug=slug)
    if profile.user.has_usable_password():
        raise ValidationError({"detail": ALREADY_SET_PASSWORD})

    from apps.users.emails import send_welcome_email  # noqa: PLC0415

    send_welcome_email(profile.user)
    return profile.user


def set_org_user_active(*, org: Organization, slug: str, is_active: bool, acting_user):
    """
    Suspend or unsuspend the org member identified by *slug*.

    *acting_user* is the central admin performing the action.  They cannot
    suspend themselves.

    Raises
    ------
    UserProfile.DoesNotExist — unknown slug or not in *org*.
    ValidationError          — self-suspend, or already in the requested state.
    """
    profile = get_org_member_profile(org=org, slug=slug)
    user = profile.user

    if not is_active and user.pk == acting_user.pk:
        raise ValidationError({"detail": CANNOT_SUSPEND_SELF})

    if is_active and user.is_active:
        raise ValidationError({"detail": NOT_SUSPENDED})
    if not is_active and not user.is_active:
        raise ValidationError({"detail": ALREADY_SUSPENDED})

    user.is_active = is_active
    user.save(update_fields=["is_active"])

    logger.info(
        "%s user '%s' in org '%s'",
        "Unsuspended" if is_active else "Suspended",
        user.email,
        org.org_suffix,
    )
    return user


def suspend_org_user(*, org: Organization, slug: str, acting_user):
    """Set the member's User.is_active to False."""
    return set_org_user_active(
        org=org, slug=slug, is_active=False, acting_user=acting_user
    )


def unsuspend_org_user(*, org: Organization, slug: str, acting_user):
    """Set the member's User.is_active to True."""
    return set_org_user_active(
        org=org, slug=slug, is_active=True, acting_user=acting_user
    )
