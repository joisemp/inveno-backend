"""
Remove first_name and last_name from the User model.

These fields have been copied to UserProfile in the previous data migration.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0003_data_migrate_names"),
    ]

    operations = [
        migrations.RemoveField(model_name="user", name="first_name"),
        migrations.RemoveField(model_name="user", name="last_name"),
    ]
