"""
Data migration: create UserProfile for every existing User.

Copies first_name / last_name from User (which still has those columns at
this point in the migration chain) and generates a unique slug.

Staff users → user_type = super_admin, org = None.
Non-staff    → user_type = central_admin, org = None
               (existing non-staff users pre-date the org system; the org
                link rule is enforced only for new profiles going forward).
"""
from django.db import migrations
from django.utils.text import slugify


def _unique_slug(UserProfile, base: str) -> str:
    """Generate a slug that does not already exist in UserProfile."""
    slug = base
    counter = 2
    while UserProfile.objects.filter(slug=slug).exists():
        slug = f"{base}-{counter}"
        counter += 1
    return slug


def create_profiles(apps, schema_editor):
    User = apps.get_model("users", "User")
    UserProfile = apps.get_model("users", "UserProfile")

    for user in User.objects.all():
        full = f"{user.first_name} {user.last_name}".strip() or user.email
        base_slug = slugify(full).lower() or "user"
        slug = _unique_slug(UserProfile, base_slug)

        user_type = "super_admin" if user.is_staff else "central_admin"
        UserProfile.objects.get_or_create(
            user=user,
            defaults={
                "user_type": user_type,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "slug": slug,
            },
        )


def reverse_profiles(apps, schema_editor):
    apps.get_model("users", "UserProfile").objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0002_add_userprofile"),
    ]

    operations = [
        migrations.RunPython(create_profiles, reverse_profiles),
    ]
