"""
Organisation registration service.

create_org_with_central_admin() is the single entry point for registering a
new Organisation together with its first central admin.  Everything runs in
one atomic transaction so a failure rolls back all DB changes.
"""
import logging

from django.contrib.auth import get_user_model
from django.db import transaction

from apps.organizations.models import Organization
from apps.users.models import UserProfile

logger = logging.getLogger(__name__)
User = get_user_model()


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
    2. Create User with an unusable password (is_staff=False).
    3. Create UserProfile linking the user to the org as central_admin.
    4. Optionally send the welcome / get-started email.

    Returns
    -------
    (Organization, User) tuple.

    Raises
    ------
    IntegrityError  — if org_suffix or admin_email is already taken.
    Any exception from send_welcome_email propagates (wrapped in the
    atomic transaction so DB changes are rolled back).
    """
    # 1. Organisation
    org = Organization.objects.create(
        name=org_name,
        org_suffix=org_suffix,
        location=location,
    )

    # 2. User — password is set via the welcome-email get-started link
    user = User.objects.create_user(
        email=admin_email,
        password=None,  # sets an unusable password
        is_staff=False,
        is_superuser=False,
        is_active=True,
    )
    # Explicitly mark unusable (create_user with password=None already does
    # this, but be explicit for clarity).
    user.set_unusable_password()
    user.save()

    # 3. UserProfile
    UserProfile.objects.create(
        user=user,
        user_type=UserProfile.UserType.CENTRAL_ADMIN,
        first_name=admin_first_name,
        last_name=admin_last_name,
        phone=admin_phone,
        org=org,
    )

    logger.info(
        "Created org '%s' (%s) with central admin '%s'",
        org_name,
        org_suffix,
        admin_email,
    )

    # 4. Welcome email (local import avoids circular dependency)
    if send_email:
        from apps.users.emails import send_welcome_email  # noqa: PLC0415

        send_welcome_email(user)

    return org, user
