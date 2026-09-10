from django.apps import AppConfig


class CommonConfig(AppConfig):
    """Shared abstract models and utilities — no concrete DB models."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.common"
    verbose_name = "Common"
