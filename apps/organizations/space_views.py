"""
API views for organisation spaces and incharge assignment.

SpaceListCreateView          GET/POST /api/orgs/spaces/
SpaceRetrieveUpdateView      GET/PATCH /api/orgs/spaces/{slug}/
SpaceSuspendView             POST /api/orgs/spaces/{slug}/suspend/
SpaceUnsuspendView           POST /api/orgs/spaces/{slug}/unsuspend/
SpaceInchargeListCreateView  GET/POST /api/orgs/spaces/{slug}/incharges/
SpaceInchargeUnassignView    POST /api/orgs/spaces/{slug}/incharges/{member}/unassign/

Writes are central-admin only.  Ops may list/retrieve all spaces.
Space incharges may GET their assigned space only.
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

from apps.common.openapi import EmptySerializer, detail_response, error_responses
from apps.organizations.models import Space
from apps.organizations.permissions import IsCentralAdmin, IsSpaceViewer
from apps.organizations.serializers import OrgMemberSerializer
from apps.organizations.space_serializers import (
    SpaceAssignSerializer,
    SpaceCreateSerializer,
    SpaceSerializer,
    SpaceUpdateSerializer,
)
from apps.organizations.space_services import (
    ALREADY_ASSIGNED,
    ALREADY_SUSPENDED,
    INCHARGE_ASSIGNED,
    INCHARGE_UNASSIGNED,
    NOT_ASSIGNED,
    NOT_SPACE_INCHARGE,
    NOT_SUSPENDED,
    SPACE_SUSPENDED,
    SPACE_UNSUSPENDED,
    assign_space_incharge,
    suspend_space,
    unassign_space_incharge,
    unsuspend_space,
)
from apps.users.models import UserProfile

SPACE_STATUS_VALUES = ("active", "suspended")
INVALID_STATUS = 'Must be "active" or "suspended".'


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


def _detail_from_validation_error(exc: DjangoValidationError) -> str:
    if hasattr(exc, "message_dict") and "detail" in exc.message_dict:
        val = exc.message_dict["detail"]
        return val[0] if isinstance(val, list) else val
    if exc.messages:
        return exc.messages[0]
    return "Invalid."


_EXAMPLE_SPACE = {
    "slug": "north-wing",
    "name": "North Wing",
    "location": "Building A",
    "is_active": True,
    "created_at": "2026-09-17T10:00:00Z",
    "updated_at": "2026-09-17T10:00:00Z",
}

_SLUG_PARAM = OpenApiParameter(
    name="slug",
    type=OpenApiTypes.STR,
    location=OpenApiParameter.PATH,
    description="Space slug.",
)

_MEMBER_PARAM = OpenApiParameter(
    name="member",
    type=OpenApiTypes.STR,
    location=OpenApiParameter.PATH,
    description="Member slug (UserProfile.slug).",
)

_NOT_FOUND = detail_response(
    "Unknown slug or space belongs to another organisation.",
    "Not found",
    {"detail": "Not found."},
    status_code="404",
)


@extend_schema_view(
    get=extend_schema(
        tags=["Spaces"],
        summary="List organisation spaces",
        parameters=[
            OpenApiParameter(
                name="status",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=False,
                enum=list(SPACE_STATUS_VALUES),
                description="Filter by space status. Omit to return all spaces.",
            )
        ],
        responses={
            200: SpaceSerializer(many=True),
            400: field_error_response(
                OpenApiExample(
                    "Invalid status",
                    value={"status": [INVALID_STATUS]},
                    response_only=True,
                    status_codes=["400"],
                )
            ),
            **error_responses(401, 403),
        },
        examples=[
            OpenApiExample(
                "Space list item",
                value=_EXAMPLE_SPACE,
                response_only=True,
                status_codes=["200"],
            )
        ],
    ),
    post=extend_schema(
        tags=["Spaces"],
        summary="Create a space",
        request=SpaceCreateSerializer,
        responses={
            201: OpenApiResponse(
                response=SpaceSerializer,
                description="Space created.",
                examples=[
                    OpenApiExample(
                        "Created",
                        value=_EXAMPLE_SPACE,
                        response_only=True,
                        status_codes=["201"],
                    )
                ],
            ),
            400: field_error_response(
                OpenApiExample(
                    "Duplicate name",
                    value={"name": ["A space with this name already exists."]},
                    response_only=True,
                    status_codes=["400"],
                ),
            ),
            **error_responses(401, 403),
        },
    ),
)
class SpaceListCreateView(generics.ListCreateAPIView):
    """List spaces in the caller's org, or create one (central admin)."""

    serializer_class = SpaceSerializer

    def get_permissions(self):
        if self.request.method == "POST":
            return [permissions.IsAuthenticated(), IsCentralAdmin()]
        return [permissions.IsAuthenticated(), IsSpaceViewer()]

    def get_queryset(self):
        org = self.request.user.profile.org
        qs = Space.objects.filter(org=org).order_by("name")
        profile = self.request.user.profile
        if profile.user_type == UserProfile.UserType.SPACE_INCHARGE:
            if profile.space_id:
                qs = qs.filter(pk=profile.space_id)
            else:
                qs = qs.none()
        space_status = self.request.query_params.get("status")
        if space_status == "active":
            return qs.filter(is_active=True)
        if space_status == "suspended":
            return qs.filter(is_active=False)
        if space_status is not None:
            return qs.none()
        return qs

    def list(self, request, *args, **kwargs):
        space_status = request.query_params.get("status")
        if space_status is not None and space_status not in SPACE_STATUS_VALUES:
            return Response(
                {"status": [INVALID_STATUS]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().list(request, *args, **kwargs)

    def get_serializer_class(self):
        if self.request.method == "POST":
            return SpaceCreateSerializer
        return SpaceSerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["org"] = self.request.user.profile.org
        return ctx

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        space = serializer.save()
        return Response(SpaceSerializer(space).data, status=status.HTTP_201_CREATED)


@extend_schema_view(
    get=extend_schema(
        tags=["Spaces"],
        summary="Get a space",
        parameters=[_SLUG_PARAM],
        responses={
            200: SpaceSerializer,
            404: _NOT_FOUND,
            **error_responses(401, 403),
        },
        examples=[
            OpenApiExample(
                "Space",
                value=_EXAMPLE_SPACE,
                response_only=True,
                status_codes=["200"],
            )
        ],
    ),
    patch=extend_schema(
        tags=["Spaces"],
        summary="Update a space",
        parameters=[_SLUG_PARAM],
        request=SpaceUpdateSerializer,
        responses={
            200: SpaceSerializer,
            400: field_error_response(
                OpenApiExample(
                    "Duplicate name",
                    value={"name": ["A space with this name already exists."]},
                    response_only=True,
                    status_codes=["400"],
                ),
            ),
            404: _NOT_FOUND,
            **error_responses(401, 403),
        },
    ),
)
class SpaceRetrieveUpdateView(generics.RetrieveUpdateAPIView):
    """Retrieve or partially update a space by slug."""

    serializer_class = SpaceSerializer
    lookup_field = "slug"
    lookup_url_kwarg = "slug"
    http_method_names = ["get", "patch", "head", "options"]

    def get_permissions(self):
        if self.request.method == "PATCH":
            return [permissions.IsAuthenticated(), IsCentralAdmin()]
        return [permissions.IsAuthenticated(), IsSpaceViewer()]

    def get_queryset(self):
        org = self.request.user.profile.org
        qs = Space.objects.filter(org=org)
        profile = self.request.user.profile
        if profile.user_type == UserProfile.UserType.SPACE_INCHARGE:
            if profile.space_id:
                qs = qs.filter(pk=profile.space_id)
            else:
                qs = qs.none()
        return qs

    def get_serializer_class(self):
        if self.request.method == "PATCH":
            return SpaceUpdateSerializer
        return SpaceSerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["org"] = self.request.user.profile.org
        return ctx

    def update(self, request, *args, **kwargs):
        space = self.get_object()
        serializer = self.get_serializer(space, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        space = serializer.save()
        return Response(SpaceSerializer(space).data)


class _SpaceStatusView(generics.GenericAPIView):
    """Shared POST-by-slug machinery for suspend / unsuspend."""

    permission_classes = [permissions.IsAuthenticated, IsCentralAdmin]
    serializer_class = EmptySerializer
    lookup_field = "slug"
    lookup_url_kwarg = "slug"
    queryset = Space.objects.all()
    service = None
    success_detail = ""

    def get_queryset(self):
        return Space.objects.filter(org=self.request.user.profile.org)

    def post(self, request, *args, **kwargs):
        slug = self.kwargs[self.lookup_url_kwarg]
        try:
            self.service(org=request.user.profile.org, slug=slug)
        except Space.DoesNotExist:
            return Response(
                {"detail": "Not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        except DjangoValidationError as exc:
            return Response(
                {"detail": _detail_from_validation_error(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({"detail": self.success_detail})


@extend_schema(
    tags=["Spaces"],
    summary="Suspend a space",
    request=EmptySerializer,
    parameters=[_SLUG_PARAM],
    responses={
        200: detail_response("Space suspended.", "Suspended", {"detail": SPACE_SUSPENDED}),
        400: detail_response(
            "Space is already suspended.",
            "Already suspended",
            {"detail": ALREADY_SUSPENDED},
            status_code="400",
        ),
        404: _NOT_FOUND,
        **error_responses(401, 403),
    },
)
class SpaceSuspendView(_SpaceStatusView):
    """Set is_active=False."""

    service = staticmethod(suspend_space)
    success_detail = SPACE_SUSPENDED


@extend_schema(
    tags=["Spaces"],
    summary="Unsuspend a space",
    request=EmptySerializer,
    parameters=[_SLUG_PARAM],
    responses={
        200: detail_response(
            "Space unsuspended.",
            "Unsuspended",
            {"detail": SPACE_UNSUSPENDED},
        ),
        400: detail_response(
            "Space is not suspended.",
            "Not suspended",
            {"detail": NOT_SUSPENDED},
            status_code="400",
        ),
        404: _NOT_FOUND,
        **error_responses(401, 403),
    },
)
class SpaceUnsuspendView(_SpaceStatusView):
    """Set is_active=True."""

    service = staticmethod(unsuspend_space)
    success_detail = SPACE_UNSUSPENDED


@extend_schema_view(
    get=extend_schema(
        tags=["Spaces"],
        summary="List space incharges",
        parameters=[_SLUG_PARAM],
        responses={
            200: OrgMemberSerializer(many=True),
            404: _NOT_FOUND,
            **error_responses(401, 403),
        },
    ),
    post=extend_schema(
        tags=["Spaces"],
        summary="Assign a space incharge",
        parameters=[_SLUG_PARAM],
        request=SpaceAssignSerializer,
        responses={
            200: OrgMemberSerializer,
            400: field_error_response(
                OpenApiExample(
                    "Wrong role",
                    value={"member": [NOT_SPACE_INCHARGE]},
                    response_only=True,
                    status_codes=["400"],
                ),
                OpenApiExample(
                    "Already assigned",
                    value={"detail": ALREADY_ASSIGNED},
                    response_only=True,
                    status_codes=["400"],
                ),
            ),
            404: _NOT_FOUND,
            **error_responses(401, 403),
        },
    ),
)
class SpaceInchargeListCreateView(generics.GenericAPIView):
    """List or assign space_incharge members on a space. Central admin writes."""

    lookup_field = "slug"
    lookup_url_kwarg = "slug"

    def get_permissions(self):
        if self.request.method == "POST":
            return [permissions.IsAuthenticated(), IsCentralAdmin()]
        return [permissions.IsAuthenticated(), IsSpaceViewer()]

    def get_queryset(self):
        org = self.request.user.profile.org
        qs = Space.objects.filter(org=org)
        profile = self.request.user.profile
        if profile.user_type == UserProfile.UserType.SPACE_INCHARGE:
            if profile.space_id:
                qs = qs.filter(pk=profile.space_id)
            else:
                qs = qs.none()
        return qs

    def get(self, request, *args, **kwargs):
        space = self.get_object()
        profiles = (
            UserProfile.objects.filter(org=request.user.profile.org, space=space)
            .select_related("user", "space")
            .order_by("first_name", "last_name")
        )
        return Response(OrgMemberSerializer(profiles, many=True).data)

    def post(self, request, *args, **kwargs):
        space = self.get_object()
        serializer = SpaceAssignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            profile = assign_space_incharge(
                org=request.user.profile.org,
                space_slug=space.slug,
                member_slug=serializer.validated_data["member"],
            )
        except UserProfile.DoesNotExist:
            return Response(
                {"detail": "Not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        except DjangoValidationError as exc:
            if hasattr(exc, "message_dict"):
                data = {
                    key: (val[0] if isinstance(val, list) and len(val) == 1 else val)
                    for key, val in exc.message_dict.items()
                }
                return Response(data, status=status.HTTP_400_BAD_REQUEST)
            return Response(
                {"detail": _detail_from_validation_error(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        profile = (
            UserProfile.objects.select_related("user", "space").get(pk=profile.pk)
        )
        return Response(OrgMemberSerializer(profile).data)


@extend_schema(
    tags=["Spaces"],
    summary="Unassign a space incharge",
    request=EmptySerializer,
    parameters=[_SLUG_PARAM, _MEMBER_PARAM],
    responses={
        200: detail_response(
            "Incharge unassigned.",
            "Unassigned",
            {"detail": INCHARGE_UNASSIGNED},
        ),
        400: detail_response(
            "Member is not assigned to this space.",
            "Not assigned",
            {"detail": NOT_ASSIGNED},
            status_code="400",
        ),
        404: _NOT_FOUND,
        **error_responses(401, 403),
    },
)
class SpaceInchargeUnassignView(generics.GenericAPIView):
    """Clear UserProfile.space for a member on this space."""

    permission_classes = [permissions.IsAuthenticated, IsCentralAdmin]
    serializer_class = EmptySerializer
    lookup_field = "slug"
    lookup_url_kwarg = "slug"

    def get_queryset(self):
        return Space.objects.filter(org=self.request.user.profile.org)

    def post(self, request, *args, **kwargs):
        space = self.get_object()
        member_slug = self.kwargs["member"]
        try:
            unassign_space_incharge(
                org=request.user.profile.org,
                space_slug=space.slug,
                member_slug=member_slug,
            )
        except UserProfile.DoesNotExist:
            return Response(
                {"detail": "Not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        except DjangoValidationError as exc:
            return Response(
                {"detail": _detail_from_validation_error(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({"detail": INCHARGE_UNASSIGNED})
