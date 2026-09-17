"""Add operation_incharge and space_incharge roles plus optional space FK."""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0002_space"),
        ("users", "0005_userprofile_warehouse_manager"),
    ]

    operations = [
        migrations.AlterField(
            model_name="userprofile",
            name="user_type",
            field=models.CharField(
                choices=[
                    ("super_admin", "Super Admin"),
                    ("central_admin", "Central Admin"),
                    ("operation_incharge", "Operation Incharge"),
                    ("warehouse_manager", "Warehouse Manager"),
                    ("space_incharge", "Space Incharge"),
                ],
                default="central_admin",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="space",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="incharges",
                to="organizations.space",
            ),
        ),
    ]
