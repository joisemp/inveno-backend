from django.apps import AppConfig


class VendorsConfig(AppConfig):
    """Org-scoped vendors — create, update, and suspend (no delete)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.vendors"
    verbose_name = "Vendors"
