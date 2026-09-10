"""Create the organizations_organization table."""
import uuid

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Organization",
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
                    models.SlugField(blank=True, max_length=255, unique=True),
                ),
                ("name", models.CharField(max_length=255)),
                (
                    "org_suffix",
                    models.CharField(
                        max_length=100,
                        unique=True,
                        validators=[
                            django.core.validators.RegexValidator(
                                regex="^[a-z0-9_]+$",
                                message=(
                                    "org_suffix may only contain lowercase "
                                    "letters, digits, and underscores."
                                ),
                            )
                        ],
                    ),
                ),
                ("location", models.CharField(blank=True, max_length=255)),
                ("is_active", models.BooleanField(default=True)),
                ("registered_on", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Organization",
                "verbose_name_plural": "Organizations",
                "ordering": ["-registered_on"],
            },
        ),
    ]
