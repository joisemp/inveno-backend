from django.apps import AppConfig


class OrganizationsConfig(AppConfig):
    """Manages Organisation model, registration service, and member API."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.organizations"
    verbose_name = "Organizations"
