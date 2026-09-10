"""
API views for the users app.

Auth endpoints
--------------
MeView                  GET/PATCH /api/auth/me/
LogoutView              POST /api/auth/logout/
ChangePasswordView      POST /api/auth/password/change/
PasswordResetRequestView POST /api/auth/password/reset/
PasswordResetConfirmView POST /api/auth/password/reset/confirm/
PasswordSetView          POST /api/auth/password/set/   (welcome-email link)

Note: user registration (POST /api/auth/register/) has been removed.
Accounts are created by super admins through Django Admin using the
organisation registration flow.
"""
import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from drf_spectacular.utils import extend_schema
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken

from .serializers import (
    ChangePasswordSerializer,
    MeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    PasswordSetupSerializer,
)

logger = logging.getLogger(__name__)
User = get_user_model()


class AuthRateThrottle(AnonRateThrottle):
    rate = "10/min"
    scope = "auth"


# ---------------------------------------------------------------------------
# Profile — GET / PATCH /api/auth/me/
# ---------------------------------------------------------------------------

@extend_schema(tags=["Auth"])
class MeView(generics.RetrieveUpdateAPIView):
    """
    Retrieve or update the authenticated user's profile.

    GET  — returns user info, nested profile (name, phone, user_type), and org.
    PATCH — accepts first_name, last_name, phone to update the UserProfile.
    """

    serializer_class = MeSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "patch", "head", "options"]

    def get_object(self):
        return self.request.user


# ---------------------------------------------------------------------------
# Logout — POST /api/auth/logout/
# ---------------------------------------------------------------------------

@extend_schema(tags=["Auth"])
class LogoutView(generics.GenericAPIView):
    """Blacklist the refresh token to log out."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        try:
            refresh_token = request.data.get("refresh")
            if not refresh_token:
                return Response(
                    {"detail": "Refresh token is required."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            token = RefreshToken(refresh_token)
            token.blacklist()
            logger.info("User logged out: %s", request.user.email)
            return Response({"detail": "Successfully logged out."})
        except Exception:
            return Response(
                {"detail": "Invalid or already blacklisted token."},
                status=status.HTTP_400_BAD_REQUEST,
            )


# ---------------------------------------------------------------------------
# Change password — POST /api/auth/password/change/
# ---------------------------------------------------------------------------

@extend_schema(tags=["Auth"])
class ChangePasswordView(generics.GenericAPIView):
    """Change password for the authenticated user (requires old password)."""

    serializer_class = ChangePasswordSerializer
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save()
        logger.info("Password changed for user: %s", request.user.email)
        return Response({"detail": "Password updated successfully."})


# ---------------------------------------------------------------------------
# Password reset (forgot-password) — POST /api/auth/password/reset/
# ---------------------------------------------------------------------------

@extend_schema(tags=["Auth"])
class PasswordResetRequestView(generics.GenericAPIView):
    """
    Request a password-reset email (forgot-password flow).

    Always returns 200 to prevent email enumeration.
    In development, the email is printed to the terminal.
    """

    serializer_class = PasswordResetRequestSerializer
    permission_classes = [permissions.AllowAny]
    throttle_classes = [AuthRateThrottle]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]

        try:
            user = User.objects.get(email=email)
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            frontend_url = getattr(
                __import__("django.conf", fromlist=["settings"]).settings,
                "FRONTEND_URL",
                "http://localhost:5173",
            )
            reset_url = (
                f"{frontend_url}/reset-password?uid={uid}&token={token}"
            )
            subject = "Password Reset Request"
            message = (
                f"Hi {user.full_name},\n\n"
                f"Click the link below to reset your password:\n\n"
                f"{reset_url}\n\n"
                f"This link expires in 1 hour.\n\n"
                f"If you did not request this, please ignore this email.\n\n"
                f"— The Inveno Team"
            )
            send_mail(subject, message, None, [email], fail_silently=False)
            logger.info("Password reset email sent to: %s", email)
        except User.DoesNotExist:
            logger.debug("Password reset requested for non-existent email: %s", email)

        return Response(
            {"detail": "If an account with that email exists, a reset link has been sent."}
        )


@extend_schema(tags=["Auth"])
class PasswordResetConfirmView(generics.GenericAPIView):
    """Confirm password reset with uid + token from the forgot-password email."""

    serializer_class = PasswordResetConfirmSerializer
    permission_classes = [permissions.AllowAny]
    throttle_classes = [AuthRateThrottle]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        user.set_password(serializer.validated_data["new_password"])
        user.save()
        logger.info("Password reset completed for user: %s", user.email)
        return Response({"detail": "Password has been reset successfully."})


# ---------------------------------------------------------------------------
# Password setup — POST /api/auth/password/set/
# ---------------------------------------------------------------------------

@extend_schema(tags=["Auth"])
class PasswordSetView(generics.GenericAPIView):
    """
    Set a password for the first time using the get-started link from the
    welcome email.

    Accepts uid + token (from the email link) plus new_password / new_password2.
    Returns 200 on success; the user must then log in with POST /api/auth/login/.

    The token uses PasswordSetupTokenGenerator (7-day TTL) and is automatically
    invalidated once the password is set.
    """

    serializer_class = PasswordSetupSerializer
    permission_classes = [permissions.AllowAny]
    throttle_classes = [AuthRateThrottle]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        user.set_password(serializer.validated_data["new_password"])
        user.save()
        logger.info("Password set via welcome email link for user: %s", user.email)
        return Response(
            {"detail": "Password set successfully. You can now log in."}
        )
