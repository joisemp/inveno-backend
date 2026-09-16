"""
API views for organisation members.

OrgMemberListCreateView     GET/POST /api/orgs/members/
OrgMemberResendWelcomeView  POST /api/orgs/members/{slug}/resend-welcome/

Central admins of an active org only.  Members are identified by
UserProfile.slug, never UUID.
"""
from django.core.exceptions import ValidationError as DjangoValidationError
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)
from rest_framework import generics, permissions, status
from rest_framework.response import Response

from apps.common.openapi import (
    EmptySerializer,
    detail_response,
    error_responses,
)
from apps.organizations.permissions import IsCentralAdmin
from apps.organizations.serializers import (
    OrgMemberCreateSerializer,
    OrgMemberSerializer,
)
from apps.organizations.services import (
    ALREADY_SET_PASSWORD,
    resend_org_user_welcome,
)
from apps.users.models import UserProfile


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


_EXAMPLE_MEMBER = {
    "slug": "alice-smith",
    "email": "alice@acme.com",
    "user_type": "warehouse_manager",
    "first_name": "Alice",
    "last_name": "Smith",
    "phone": "+15551234",
    "full_name": "Alice Smith",
    "is_active": True,
    "has_usable_password": False,
    "date_joined": "2026-09-15T10:00:00Z",
}


@extend_schema_view(
    get=extend_schema(
        tags=["Organisation"],
        summary="List organisation members",
        responses={
            200: OrgMemberSerializer(many=True),
            **error_responses(401, 403),
        },
        examples=[
            OpenApiExample(
                "Member list item",
                value=_EXAMPLE_MEMBER,
                response_only=True,
                status_codes=["200"],
            )
        ],
    ),
    post=extend_schema(
        tags=["Organisation"],
        summary="Add an organisation member",
        request=OrgMemberCreateSerializer,
        responses={
            201: OpenApiResponse(
                response=OrgMemberSerializer,
                description="Member created and welcome email sent.",
                examples=[
                    OpenApiExample(
                        "Created",
                        value=_EXAMPLE_MEMBER,
                        response_only=True,
                        status_codes=["201"],
                    )
                ],
            ),
            400: field_error_response(
                OpenApiExample(
                    "Duplicate email",
                    value={"email": ["A user with this email already exists."]},
                    response_only=True,
                    status_codes=["400"],
                ),
                OpenApiExample(
                    "Invalid user type",
                    value={
                        "user_type": ['"super_admin" is not a valid choice.']
                    },
                    response_only=True,
                    status_codes=["400"],
                ),
            ),
            **error_responses(401, 403),
        },
    ),
)
class OrgMemberListCreateView(generics.ListCreateAPIView):
    """
    List members of the caller's organisation, or add a new one.

    POST creates a User with an unusable password and sends the existing
    welcome / get-started email.  The new member's slug is generated.
    """

    permission_classes = [permissions.IsAuthenticated, IsCentralAdmin]
    serializer_class = OrgMemberSerializer

    def get_queryset(self):
        return (
            UserProfile.objects.filter(org=self.request.user.profile.org)
            .select_related("user")
            .order_by("-user__date_joined")
        )

    def get_serializer_class(self):
        if self.request.method == "POST":
            return OrgMemberCreateSerializer
        return OrgMemberSerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["org"] = self.request.user.profile.org
        return ctx

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile = serializer.save()
        return Response(
            OrgMemberSerializer(profile).data,
            status=status.HTTP_201_CREATED,
        )


@extend_schema(
    tags=["Organisation"],
    summary="Resend welcome email",
    request=EmptySerializer,
    parameters=[
        OpenApiParameter(
            name="slug",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.PATH,
            description="Member slug (UserProfile.slug).",
        )
    ],
    responses={
        200: detail_response(
            "Welcome email sent.",
            "Sent",
            {"detail": "Welcome email sent."},
        ),
        400: detail_response(
            "Member has already set a password.",
            "Already set password",
            {"detail": ALREADY_SET_PASSWORD},
            status_code="400",
        ),
        404: detail_response(
            "Unknown slug or member belongs to another organisation.",
            "Not found",
            {"detail": "Not found."},
            status_code="404",
        ),
        **error_responses(401, 403),
    },
)
class OrgMemberResendWelcomeView(generics.GenericAPIView):
    """Re-send the get-started email for a member who has not set a password."""

    permission_classes = [permissions.IsAuthenticated, IsCentralAdmin]
    serializer_class = EmptySerializer
    lookup_field = "slug"
    lookup_url_kwarg = "slug"
    queryset = UserProfile.objects.all()

    def get_queryset(self):
        return UserProfile.objects.filter(
            org=self.request.user.profile.org
        ).select_related("user")

    def post(self, request, *args, **kwargs):
        slug = self.kwargs[self.lookup_url_kwarg]
        try:
            resend_org_user_welcome(
                org=request.user.profile.org,
                slug=slug,
            )
        except UserProfile.DoesNotExist:
            return Response(
                {"detail": "Not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        except DjangoValidationError:
            return Response(
                {"detail": ALREADY_SET_PASSWORD},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({"detail": "Welcome email sent."})
