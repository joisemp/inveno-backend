"""Tests for assign_unique_slug date-letter collision suffixes."""
import pytest
from django.utils import timezone

from apps.common.slugs import assign_unique_slug, letter_suffix
from apps.organizations.models import Organization


@pytest.mark.parametrize(
    ("index", "expected"),
    [(1, "a"), (2, "b"), (26, "z"), (27, "aa"), (28, "ab")],
)
def test_letter_suffix(index, expected):
    assert letter_suffix(index) == expected


@pytest.mark.django_db
class TestAssignUniqueSlug:
    def test_first_slug_is_clean(self):
        org = Organization(name="Alpha Corp", org_suffix="alpha_corp")
        assert assign_unique_slug(org, "Alpha Corp") == "alpha-corp"

    def test_collision_uses_date_letter_not_numeric(self):
        Organization.objects.create(name="Alpha Corp", org_suffix="alpha_a")
        org2 = Organization(name="Alpha Corp", org_suffix="alpha_b")
        date_part = timezone.localdate().strftime("%Y%m%d")
        slug = assign_unique_slug(org2, "Alpha Corp")
        assert slug == f"alpha-corp-{date_part}-a"
        assert slug != "alpha-corp-2"

    def test_second_same_day_collision_uses_b(self):
        date_part = timezone.localdate().strftime("%Y%m%d")
        Organization.objects.create(name="Alpha Corp", org_suffix="alpha_a")
        Organization.objects.create(
            name="Alpha Two",
            org_suffix="alpha_b",
            slug=f"alpha-corp-{date_part}-a",
        )
        org3 = Organization(name="Alpha Corp", org_suffix="alpha_c")
        assert assign_unique_slug(org3, "Alpha Corp") == f"alpha-corp-{date_part}-b"
