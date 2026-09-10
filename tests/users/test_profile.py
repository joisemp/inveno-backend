"""
Tests for UserProfile model and slug behaviour.

Covers:
- Auto-creation of super_admin profile via post_save signal
- Slug auto-generation and uniqueness
- Org-link validation rule (non-staff must have org; staff must not)
- Profile accessible via User.full_name delegation
"""
import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from apps.organizations.models import Organization
from apps.users.models import UserProfile

User = get_user_model()


@pytest.mark.django_db
class TestStaffProfileSignal:
    def test_profile_auto_created_for_staff(self):
        """A super_admin profile is created automatically for staff users."""
        user = User.objects.create_superuser(
            email="staff@example.com", password="Pass123!"
        )
        assert hasattr(user, "profile")
        assert user.profile.user_type == UserProfile.UserType.SUPER_ADMIN
        assert user.profile.org is None

    def test_profile_not_auto_created_for_non_staff(self, db):
        """Non-staff users do NOT get an auto profile (service handles it)."""
        user = User.objects.create_user(
            email="regular@example.com", password="Pass123!"
        )
        with pytest.raises(UserProfile.DoesNotExist):
            _ = user.profile

    def test_signal_is_idempotent(self):
        """Re-saving a staff user does not create a duplicate profile."""
        user = User.objects.create_superuser(
            email="staff2@example.com", password="Pass123!"
        )
        user.save()  # second save
        assert UserProfile.objects.filter(user=user).count() == 1


@pytest.mark.django_db
class TestSlugAutoGeneration:
    def test_slug_auto_generated_from_name(self, test_org):
        user = User.objects.create_user(email="slug@example.com", password="Pass123!")
        profile = UserProfile.objects.create(
            user=user,
            user_type=UserProfile.UserType.CENTRAL_ADMIN,
            first_name="Alice",
            last_name="Smith",
            org=test_org,
        )
        assert profile.slug == "alice-smith"

    def test_slug_unique_collision_appends_suffix(self, test_org):
        """Colliding slug gets -2, -3, etc."""
        org2 = Organization.objects.create(name="Org B", org_suffix="org_b")

        user1 = User.objects.create_user(email="u1@example.com", password="Pass123!")
        UserProfile.objects.create(
            user=user1,
            user_type=UserProfile.UserType.CENTRAL_ADMIN,
            first_name="Bob",
            last_name="Jones",
            org=test_org,
        )

        user2 = User.objects.create_user(email="u2@example.com", password="Pass123!")
        profile2 = UserProfile.objects.create(
            user=user2,
            user_type=UserProfile.UserType.CENTRAL_ADMIN,
            first_name="Bob",
            last_name="Jones",
            org=org2,
        )
        assert profile2.slug == "bob-jones-2"

    def test_slug_stable_after_name_change(self, test_org):
        """Slug is NOT rewritten when first_name / last_name changes."""
        user = User.objects.create_user(email="stable@example.com", password="Pass123!")
        profile = UserProfile.objects.create(
            user=user,
            user_type=UserProfile.UserType.CENTRAL_ADMIN,
            first_name="Carol",
            last_name="White",
            org=test_org,
        )
        original_slug = profile.slug

        profile.first_name = "Changed"
        profile.save()

        profile.refresh_from_db()
        assert profile.slug == original_slug

    def test_org_slug_auto_generated(self):
        """Organization.slug is auto-generated from name."""
        org = Organization.objects.create(
            name="Alpha Corp", org_suffix="alpha_corp"
        )
        assert org.slug == "alpha-corp"


@pytest.mark.django_db
class TestOrgLinkValidation:
    def test_non_staff_profile_without_org_fails(self):
        """clean() must reject a non-staff profile with no org."""
        user = User.objects.create_user(email="noorg@example.com", password="Pass123!")
        profile = UserProfile(
            user=user,
            user_type=UserProfile.UserType.CENTRAL_ADMIN,
            org=None,
        )
        with pytest.raises(ValidationError, match="must be linked"):
            profile.clean()

    def test_staff_profile_with_org_fails(self, test_org):
        """clean() must reject a staff user linked to an org."""
        user = User.objects.create_superuser(
            email="stafforg@example.com", password="Pass123!"
        )
        profile = user.profile  # auto-created with org=None
        profile.org = test_org
        with pytest.raises(ValidationError, match="must not be linked"):
            profile.clean()


@pytest.mark.django_db
class TestFullName:
    def test_user_full_name_delegates_to_profile(self, test_user):
        assert test_user.full_name == "Test User"

    def test_user_full_name_fallback_to_email_without_profile(self, db):
        user = User.objects.create_user(email="noname@example.com", password="Pass123!")
        assert user.full_name == "noname@example.com"

    def test_multiple_central_admins_per_org(self, test_org, db):
        """An org can have more than one central admin."""
        for i in range(3):
            u = User.objects.create_user(
                email=f"admin{i}@example.com", password="Pass123!"
            )
            UserProfile.objects.create(
                user=u,
                user_type=UserProfile.UserType.CENTRAL_ADMIN,
                first_name=f"Admin{i}",
                org=test_org,
            )
        assert test_org.profiles.count() == 3
