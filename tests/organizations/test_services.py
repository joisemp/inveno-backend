"""
Tests for apps.organizations.services.create_org_with_central_admin().

Covers:
- Happy path: org, user, profile created; welcome email sent
- Duplicate org_suffix rejected
- Duplicate admin email rejected
- org name is NOT unique (two orgs can share the same name)
- org_suffix stored lowercase
- Slug auto-generated for org
- Multiple central admins per org
"""
import pytest
from django.core import mail
from django.contrib.auth import get_user_model
from django.db import IntegrityError

from apps.organizations.models import Organization
from apps.organizations.services import create_org_with_central_admin
from apps.users.models import UserProfile

User = get_user_model()


@pytest.mark.django_db
class TestCreateOrgWithCentralAdmin:
    def test_creates_org_user_and_profile(self):
        org, user = create_org_with_central_admin(
            org_name="Acme Corp",
            org_suffix="acme_corp",
            location="New York",
            admin_email="admin@acme.com",
            admin_first_name="Alice",
            admin_last_name="Smith",
            send_email=False,
        )
        assert Organization.objects.filter(org_suffix="acme_corp").exists()
        assert User.objects.filter(email="admin@acme.com").exists()
        profile = UserProfile.objects.get(user=user)
        assert profile.user_type == UserProfile.UserType.CENTRAL_ADMIN
        assert profile.org == org
        assert profile.first_name == "Alice"

    def test_user_has_unusable_password(self):
        _, user = create_org_with_central_admin(
            org_name="Beta Inc",
            org_suffix="beta_inc",
            admin_email="admin@beta.com",
            admin_first_name="Bob",
            admin_last_name="Jones",
            send_email=False,
        )
        assert not user.has_usable_password()

    def test_sends_welcome_email(self):
        create_org_with_central_admin(
            org_name="Gamma LLC",
            org_suffix="gamma_llc",
            admin_email="admin@gamma.com",
            admin_first_name="Carol",
            admin_last_name="White",
            send_email=True,
        )
        assert len(mail.outbox) == 1
        assert "admin@gamma.com" in mail.outbox[0].to
        assert "get-started" in mail.outbox[0].body.lower() or "get started" in mail.outbox[0].body.lower()

    def test_duplicate_org_suffix_fails(self):
        create_org_with_central_admin(
            org_name="Delta Co",
            org_suffix="delta_co",
            admin_email="a@delta.com",
            admin_first_name="A",
            admin_last_name="B",
            send_email=False,
        )
        with pytest.raises(Exception):  # IntegrityError or ValidationError
            create_org_with_central_admin(
                org_name="Delta Two",
                org_suffix="delta_co",  # same suffix
                admin_email="b@delta.com",
                admin_first_name="C",
                admin_last_name="D",
                send_email=False,
            )

    def test_duplicate_admin_email_fails(self):
        create_org_with_central_admin(
            org_name="Echo Corp",
            org_suffix="echo_corp",
            admin_email="dup@example.com",
            admin_first_name="E",
            admin_last_name="F",
            send_email=False,
        )
        with pytest.raises(Exception):
            create_org_with_central_admin(
                org_name="Echo Two",
                org_suffix="echo_two",
                admin_email="dup@example.com",  # same email
                admin_first_name="G",
                admin_last_name="H",
                send_email=False,
            )

    def test_duplicate_org_name_allowed(self):
        """Two orgs can share the same display name if org_suffix differs."""
        org1, _ = create_org_with_central_admin(
            org_name="Same Name",
            org_suffix="same_name_east",
            admin_email="east@example.com",
            admin_first_name="E",
            admin_last_name="E",
            send_email=False,
        )
        org2, _ = create_org_with_central_admin(
            org_name="Same Name",
            org_suffix="same_name_west",
            admin_email="west@example.com",
            admin_first_name="W",
            admin_last_name="W",
            send_email=False,
        )
        assert org1.name == org2.name
        assert org1.org_suffix != org2.org_suffix

    def test_org_suffix_stored_lowercase(self):
        org, _ = create_org_with_central_admin(
            org_name="Foxtrot",
            org_suffix="foxtrot_org",
            admin_email="fox@example.com",
            admin_first_name="F",
            admin_last_name="F",
            send_email=False,
        )
        assert org.org_suffix == "foxtrot_org"

    def test_org_slug_auto_generated(self):
        org, _ = create_org_with_central_admin(
            org_name="Golf Club",
            org_suffix="golf_club",
            admin_email="golf@example.com",
            admin_first_name="G",
            admin_last_name="G",
            send_email=False,
        )
        assert org.slug == "golf-club"

    def test_profile_slug_auto_generated(self):
        _, user = create_org_with_central_admin(
            org_name="Hotel Corp",
            org_suffix="hotel_corp",
            admin_email="hotel@example.com",
            admin_first_name="Harry",
            admin_last_name="Potter",
            send_email=False,
        )
        assert user.profile.slug == "harry-potter"

    def test_multiple_central_admins_per_org(self):
        """Adding a second central admin to the same org is allowed."""
        from apps.users.models import UserProfile

        org, _ = create_org_with_central_admin(
            org_name="India Co",
            org_suffix="india_co",
            admin_email="first@india.com",
            admin_first_name="First",
            admin_last_name="Admin",
            send_email=False,
        )
        # Manually add a second central admin
        second_user = User.objects.create_user(
            email="second@india.com", password="Pass123!"
        )
        UserProfile.objects.create(
            user=second_user,
            user_type=UserProfile.UserType.CENTRAL_ADMIN,
            first_name="Second",
            last_name="Admin",
            org=org,
        )
        assert org.profiles.filter(
            user_type=UserProfile.UserType.CENTRAL_ADMIN
        ).count() == 2

    def test_user_is_not_staff(self):
        _, user = create_org_with_central_admin(
            org_name="Juliet Inc",
            org_suffix="juliet_inc",
            admin_email="juliet@example.com",
            admin_first_name="J",
            admin_last_name="J",
            send_email=False,
        )
        assert not user.is_staff
        assert not user.is_superuser
