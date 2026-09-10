from django.apps import AppConfig


class OrganizationsConfig(AppConfig):
    """Manages Organisation model and the org-registration service."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.organizations"
    verbose_name = "Organizations"
