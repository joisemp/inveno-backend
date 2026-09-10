"""
Django Admin for the Organizations app.

OrganizationAdmin provides:
- A custom add form that collects both Organisation details and the first
  central admin's details.  On save it calls create_org_with_central_admin()
  so everything is created atomically.
- A change view showing name / location / is_active plus an inline list of
  linked central-admin profiles.
- An admin action to resend the welcome email to admins who haven't set a
  password yet.

Access is restricted to superusers only (not every is_staff user).
"""
import logging

from django import forms
from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.http import HttpResponseRedirect
from django.urls import reverse

from apps.organizations.models import Organization
from apps.organizations.services import create_org_with_central_admin
from apps.users.models import UserProfile

logger = logging.getLogger(__name__)
User = get_user_model()


# ---------------------------------------------------------------------------
# Custom add form
# ---------------------------------------------------------------------------

class OrganizationAdminAddForm(forms.ModelForm):
    """
    ModelForm for registering a new Organisation plus its first central admin.

    Organisation fields come from the model; extra fields collect the admin's
    details so the service can create the User and UserProfile in one go.
    """

    # Central admin fields (extra — not on the Organisation model)
    admin_email = forms.EmailField(label="Central admin email")
    admin_first_name = forms.CharField(max_length=150, label="First name")
    admin_last_name = forms.CharField(max_length=150, label="Last name")
    admin_phone = forms.CharField(max_length=30, required=False, label="Phone")

    class Meta:
        model = Organization
        fields = ["name", "org_suffix", "location"]

    def clean_admin_email(self):
        email = self.cleaned_data["admin_email"]
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError(
                "A user with this email already exists."
            )
        return email

    def clean_org_suffix(self):
        value = self.cleaned_data.get("org_suffix", "").lower()
        if Organization.objects.filter(org_suffix=value).exists():
            raise forms.ValidationError("This org handle is already taken.")
        return value


# ---------------------------------------------------------------------------
# Central admin inline (shown on the change view only)
# ---------------------------------------------------------------------------

class CentralAdminInline(admin.TabularInline):
    """Read-only list of central admins linked to this org."""

    model = UserProfile
    fk_name = "org"
    fields = ("user", "user_type", "first_name", "last_name", "phone", "slug")
    readonly_fields = ("user", "user_type", "first_name", "last_name", "phone", "slug")
    extra = 0
    can_delete = False
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False


# ---------------------------------------------------------------------------
# OrganizationAdmin
# ---------------------------------------------------------------------------

@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "org_suffix", "location", "is_active", "registered_on")
    list_filter = ("is_active",)
    search_fields = ("name", "org_suffix")
    ordering = ("-registered_on",)
    readonly_fields = ("slug", "registered_on")
    actions = ["resend_welcome_email_action"]

    # Change-view fieldsets
    fieldsets = (
        (None, {"fields": ("name", "org_suffix", "location")}),
        ("Status", {"fields": ("is_active",)}),
        ("Meta", {"fields": ("slug", "registered_on"), "classes": ("collapse",)}),
    )

    # ---------------------------------------------------------------------------
    # Add-view customisation
    # ---------------------------------------------------------------------------

    def get_form(self, request, obj=None, **kwargs):
        """Return the custom add form for new objects; default form for edits."""
        if obj is None:
            return OrganizationAdminAddForm
        return super().get_form(request, obj, **kwargs)

    def get_fieldsets(self, request, obj=None):
        """Two-section fieldset on add; standard on change."""
        if obj is None:
            return (
                (
                    "Organisation details",
                    {"fields": ("name", "org_suffix", "location")},
                ),
                (
                    "First central admin",
                    {
                        "fields": (
                            "admin_email",
                            "admin_first_name",
                            "admin_last_name",
                            "admin_phone",
                        )
                    },
                ),
            )
        return super().get_fieldsets(request, obj)

    def get_inlines(self, request, obj):
        """Show central-admin inline only on the change view."""
        if obj is None:
            return []
        return [CentralAdminInline]

    def save_model(self, request, obj, form, change):
        """
        On add: delegate to the registration service (creates org + user +
        profile + sends email).  On change: standard model save.
        """
        if not change:
            data = form.cleaned_data
            try:
                org, user = create_org_with_central_admin(
                    org_name=data["name"],
                    org_suffix=data["org_suffix"],
                    location=data.get("location", ""),
                    admin_email=data["admin_email"],
                    admin_first_name=data["admin_first_name"],
                    admin_last_name=data["admin_last_name"],
                    admin_phone=data.get("admin_phone", ""),
                )
                # Copy the real pk to obj so response_add() can redirect to
                # the correct change URL.
                obj.pk = org.pk
                obj.id = org.id
                obj._state.adding = False
                messages.success(
                    request,
                    f"Organisation '{org.name}' created and welcome email sent to "
                    f"'{user.email}'.",
                )
            except Exception as exc:
                logger.exception("Failed to register org via admin: %s", exc)
                messages.error(request, f"Registration failed: {exc}")
                raise
        else:
            super().save_model(request, obj, form, change)

    def response_add(self, request, obj, post_url_continue=None):
        """After a successful add, go straight to the new org's change view."""
        if obj.pk:
            url = reverse(
                "admin:organizations_organization_change", args=[obj.pk]
            )
            return HttpResponseRedirect(url)
        return super().response_add(request, obj, post_url_continue)

    # ---------------------------------------------------------------------------
    # Superuser-only access
    # ---------------------------------------------------------------------------

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    # ---------------------------------------------------------------------------
    # Admin action: resend welcome email
    # ---------------------------------------------------------------------------

    @admin.action(description="Resend welcome email to central admins who have not set a password")
    def resend_welcome_email_action(self, request, queryset):
        from apps.users.emails import send_welcome_email

        sent = 0
        for org in queryset:
            for profile in org.profiles.filter(
                user_type=UserProfile.UserType.CENTRAL_ADMIN
            ):
                if not profile.user.has_usable_password():
                    send_welcome_email(profile.user)
                    sent += 1
        self.message_user(
            request,
            f"Welcome email resent to {sent} central admin(s).",
            messages.SUCCESS,
        )
