"""Add Space model."""
import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Space",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "slug",
                    models.SlugField(blank=True, db_index=True, max_length=255, unique=True),
                ),
                ("name", models.CharField(max_length=255)),
                ("location", models.CharField(blank=True, max_length=255)),
                (
                    "is_active",
                    models.BooleanField(
                        default=True,
                        help_text="Inactive spaces cannot receive new purchase requests.",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "org",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="spaces",
                        to="organizations.organization",
                    ),
                ),
            ],
            options={
                "verbose_name": "Space",
                "verbose_name_plural": "Spaces",
                "ordering": ["name"],
            },
        ),
        migrations.AddConstraint(
            model_name="space",
            constraint=models.UniqueConstraint(
                fields=("org", "name"),
                name="organizations_space_org_name_uniq",
            ),
        ),
    ]
