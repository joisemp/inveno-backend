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
LoginView               POST /api/auth/login/
TokenRefreshView        POST /api/auth/token/refresh/
TokenVerifyView         POST /api/auth/token/verify/

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
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView as SimpleJWTTokenRefreshView,
    TokenVerifyView as SimpleJWTTokenVerifyView,
)

from apps.common.openapi import (
    EmptySerializer,
    LoginRequestSerializer,
    LogoutRequestSerializer,
    TokenPairSerializer,
    TokenRefreshRequestSerializer,
    TokenVerifyRequestSerializer,
    detail_response,
    error_responses,
)

from .serializers import (
    ChangePasswordSerializer,
    CustomTokenRefreshSerializer,
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


def field_error_response(*examples):
    """OpenAPI 400 body for serializer field errors."""
    flat = []
    for item in examples:
        if isinstance(item, (list, tuple)):
            flat.extend(item)
        else:
            flat.append(item)
    return OpenApiResponse(
        response=OpenApiTypes.OBJECT,
        description="Validation error.",
        examples=flat,
    )


# ---------------------------------------------------------------------------
# Profile — GET / PATCH /api/auth/me/
# ---------------------------------------------------------------------------

@extend_schema_view(
    get=extend_schema(
        tags=["Auth"],
        summary="Get my profile",
        responses={
            200: MeSerializer,
            **error_responses(401),
        },
    ),
    patch=extend_schema(
        tags=["Auth"],
        summary="Update my profile",
        request=MeSerializer,
        responses={
            200: MeSerializer,
            400: field_error_response(
                [
                    OpenApiExample(
                        "Validation",
                        value={
                            "phone": [
                                "Ensure this field has no more than 30 characters."
                            ]
                        },
                        response_only=True,
                        status_codes=["400"],
                    )
                ]
            ),
            **error_responses(401),
        },
    ),
)
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

@extend_schema(
    tags=["Auth"],
    summary="Log out (blacklist refresh token)",
    request=LogoutRequestSerializer,
    responses={
        200: detail_response(
            "Refresh token blacklisted.",
            "Logged out",
            {"detail": "Successfully logged out."},
        ),
        400: OpenApiResponse(
            response=OpenApiTypes.OBJECT,
            description="Missing or invalid refresh token.",
            examples=[
                OpenApiExample(
                    "Missing refresh",
                    value={"detail": "Refresh token is required."},
                    response_only=True,
                    status_codes=["400"],
                ),
                OpenApiExample(
                    "Already blacklisted",
                    value={"detail": "Invalid or already blacklisted token."},
                    response_only=True,
                    status_codes=["400"],
                ),
            ],
        ),
        **error_responses(401),
    },
)
class LogoutView(generics.GenericAPIView):
    """Blacklist the refresh token to log out."""

    serializer_class = LogoutRequestSerializer
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

@extend_schema(
    tags=["Auth"],
    summary="Change password",
    request=ChangePasswordSerializer,
    responses={
        200: detail_response(
            "Password updated.",
            "Updated",
            {"detail": "Password updated successfully."},
        ),
        400: field_error_response(
            [
                OpenApiExample(
                    "Wrong old password",
                    value={"old_password": ["Old password is incorrect."]},
                    response_only=True,
                    status_codes=["400"],
                ),
                OpenApiExample(
                    "Mismatch",
                    value={"new_password2": ["Passwords do not match."]},
                    response_only=True,
                    status_codes=["400"],
                ),
                OpenApiExample(
                    "Weak password",
                    value={"new_password": ["This password is too common."]},
                    response_only=True,
                    status_codes=["400"],
                ),
            ]
        ),
        **error_responses(401),
    },
)
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

@extend_schema(
    tags=["Auth"],
    summary="Request password reset email",
    request=PasswordResetRequestSerializer,
    responses={
        200: detail_response(
            "Always 200 to prevent email enumeration.",
            "Accepted",
            {
                "detail": (
                    "If an account with that email exists, a reset link has been sent."
                )
            },
        ),
        400: field_error_response(
            [
                OpenApiExample(
                    "Invalid email",
                    value={"email": ["Enter a valid email address."]},
                    response_only=True,
                    status_codes=["400"],
                )
            ]
        ),
        **error_responses(429),
    },
)
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


@extend_schema(
    tags=["Auth"],
    summary="Confirm password reset",
    request=PasswordResetConfirmSerializer,
    responses={
        200: detail_response(
            "Password reset completed.",
            "Reset",
            {"detail": "Password has been reset successfully."},
        ),
        400: field_error_response(
            [
                OpenApiExample(
                    "Invalid uid",
                    value={"uid": ["Invalid reset link."]},
                    response_only=True,
                    status_codes=["400"],
                ),
                OpenApiExample(
                    "Expired token",
                    value={"token": ["Reset link is invalid or has expired."]},
                    response_only=True,
                    status_codes=["400"],
                ),
                OpenApiExample(
                    "Mismatch",
                    value={"new_password2": ["Passwords do not match."]},
                    response_only=True,
                    status_codes=["400"],
                ),
            ]
        ),
        **error_responses(429),
    },
)
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

@extend_schema(
    tags=["Auth"],
    summary="Set password from welcome email",
    request=PasswordSetupSerializer,
    responses={
        200: detail_response(
            "Password set; user must log in next.",
            "Set",
            {"detail": "Password set successfully. You can now log in."},
        ),
        400: field_error_response(
            [
                OpenApiExample(
                    "Invalid uid",
                    value={"uid": ["Invalid link."]},
                    response_only=True,
                    status_codes=["400"],
                ),
                OpenApiExample(
                    "Expired token",
                    value={
                        "token": [
                            "Link is invalid or has expired. Request a new welcome email."
                        ]
                    },
                    response_only=True,
                    status_codes=["400"],
                ),
                OpenApiExample(
                    "Mismatch",
                    value={"new_password2": ["Passwords do not match."]},
                    response_only=True,
                    status_codes=["400"],
                ),
                OpenApiExample(
                    "Weak password",
                    value={"new_password": ["This password is too common."]},
                    response_only=True,
                    status_codes=["400"],
                ),
            ]
        ),
        **error_responses(429),
    },
)
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


# ---------------------------------------------------------------------------
# JWT — login / refresh / verify
# ---------------------------------------------------------------------------

@extend_schema(
    tags=["Auth"],
    summary="Log in (email + password)",
    request=LoginRequestSerializer,
    responses={
        200: OpenApiResponse(
            response=TokenPairSerializer,
            description="Access (15 min) and refresh (7 days) tokens.",
            examples=[
                OpenApiExample(
                    "Tokens",
                    value={
                        "access": "eyJ0eXAiOiJKV1QiLCJhbGci...",
                        "refresh": "eyJ0eXAiOiJKV1QiLCJhbGci...",
                    },
                    response_only=True,
                    status_codes=["200"],
                )
            ],
        ),
        400: field_error_response(
            [
                OpenApiExample(
                    "Organisation suspended",
                    value={
                        "non_field_errors": [
                            "Your organisation has been suspended. "
                            "Please contact your administrator."
                        ]
                    },
                    response_only=True,
                    status_codes=["400"],
                ),
                OpenApiExample(
                    "Account suspended",
                    value={
                        "non_field_errors": [
                            "Your account has been suspended. "
                            "Please contact your administrator."
                        ]
                    },
                    response_only=True,
                    status_codes=["400"],
                ),
                OpenApiExample(
                    "Missing fields",
                    value={
                        "email": ["This field is required."],
                        "password": ["This field is required."],
                    },
                    response_only=True,
                    status_codes=["400"],
                ),
            ]
        ),
        401: OpenApiResponse(
            response=OpenApiTypes.OBJECT,
            description="Wrong email or password.",
            examples=[
                OpenApiExample(
                    "Bad credentials",
                    value={
                        "detail": "No active account found with the given credentials."
                    },
                    response_only=True,
                    status_codes=["401"],
                )
            ],
        ),
        **error_responses(429),
    },
)
class LoginView(TokenObtainPairView):
    """Email + password → JWT pair. Uses CustomTokenObtainPairSerializer."""


@extend_schema(
    tags=["Auth"],
    summary="Refresh access token",
    request=TokenRefreshRequestSerializer,
    responses={
        200: OpenApiResponse(
            response=TokenPairSerializer,
            description="New access token; refresh is rotated.",
        ),
        400: field_error_response(
            [
                OpenApiExample(
                    "Missing refresh",
                    value={"refresh": ["This field is required."]},
                    response_only=True,
                    status_codes=["400"],
                )
            ]
        ),
        401: OpenApiResponse(
            response=OpenApiTypes.OBJECT,
            description="Invalid, expired, or blacklisted refresh token.",
            examples=[
                OpenApiExample(
                    "Invalid refresh",
                    value={
                        "detail": "Token is invalid or expired",
                        "code": "token_not_valid",
                    },
                    response_only=True,
                    status_codes=["401"],
                )
            ],
        ),
    },
)
class TokenRefreshView(SimpleJWTTokenRefreshView):
    """Rotate access (and refresh) tokens. Inactive users are rejected."""

    serializer_class = CustomTokenRefreshSerializer


@extend_schema(
    tags=["Auth"],
    summary="Verify a JWT",
    request=TokenVerifyRequestSerializer,
    responses={
        200: OpenApiResponse(
            response=EmptySerializer,
            description="Token is valid.",
            examples=[
                OpenApiExample(
                    "Valid",
                    value={},
                    response_only=True,
                    status_codes=["200"],
                )
            ],
        ),
        400: field_error_response(
            [
                OpenApiExample(
                    "Missing token",
                    value={"token": ["This field is required."]},
                    response_only=True,
                    status_codes=["400"],
                )
            ]
        ),
        401: OpenApiResponse(
            response=OpenApiTypes.OBJECT,
            description="Invalid or expired token.",
            examples=[
                OpenApiExample(
                    "Invalid token",
                    value={
                        "detail": "Token is invalid or expired",
                        "code": "token_not_valid",
                    },
                    response_only=True,
                    status_codes=["401"],
                )
            ],
        ),
    },
)
class TokenVerifyView(SimpleJWTTokenVerifyView):
    """Check whether a token is valid."""
