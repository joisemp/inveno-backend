"""
Django Admin for the Users app.

UserAdmin  — updated to reflect that personal name fields (first_name,
             last_name) have moved to UserProfile.  A stacked UserProfile
             inline lets admins view and edit the profile from the user page.
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import User, UserProfile


# ---------------------------------------------------------------------------
# UserProfile inline
# ---------------------------------------------------------------------------

class UserProfileInline(admin.StackedInline):
    """Edit the UserProfile directly from the User change page."""

    model = UserProfile
    fields = ("user_type", "first_name", "last_name", "phone", "org", "slug")
    readonly_fields = ("slug",)
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        # Profile is created automatically; adding manually is unnecessary.
        return False


# ---------------------------------------------------------------------------
# UserAdmin
# ---------------------------------------------------------------------------

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("email", "is_active", "is_staff", "date_joined")
    list_filter = ("is_active", "is_staff", "is_superuser")
    search_fields = ("email",)
    ordering = ("-date_joined",)
    readonly_fields = ("id", "date_joined", "updated_at")
    inlines = [UserProfileInline]

    fieldsets = (
        (None, {"fields": ("id", "email", "password")}),
        (
            _("Permissions"),
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        (_("Important dates"), {"fields": ("last_login", "date_joined", "updated_at")}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2"),
            },
        ),
    )

    # email is the USERNAME_FIELD — no username field
    filter_horizontal = ("groups", "user_permissions")
