"""Add warehouse_manager to UserProfile.user_type choices."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0004_remove_user_name_fields"),
    ]

    operations = [
        migrations.AlterField(
            model_name="userprofile",
            name="user_type",
            field=models.CharField(
                choices=[
                    ("super_admin", "Super Admin"),
                    ("central_admin", "Central Admin"),
                    ("warehouse_manager", "Warehouse Manager"),
                ],
                default="central_admin",
                max_length=20,
            ),
        ),
    ]
