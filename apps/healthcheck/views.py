import logging

from django.conf import settings
from django.db import connection
from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from redis import Redis
from redis.exceptions import RedisError
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.openapi import HealthSerializer

logger = logging.getLogger(__name__)


@extend_schema(
    tags=["System"],
    summary="Health check",
    responses={
        200: OpenApiResponse(
            response=HealthSerializer,
            description="API and dependencies are healthy.",
            examples=[
                OpenApiExample(
                    "Healthy",
                    value={"status": "ok", "db": "ok", "redis": "ok"},
                    response_only=True,
                    status_codes=["200"],
                )
            ],
        ),
        503: OpenApiResponse(
            response=HealthSerializer,
            description="One or more dependencies failed.",
            examples=[
                OpenApiExample(
                    "Degraded",
                    value={"status": "degraded", "db": "ok", "redis": "error"},
                    response_only=True,
                    status_codes=["503"],
                )
            ],
        ),
    },
)
class HealthCheckView(APIView):
    """
    GET /api/health/

    Returns the operational status of the API and its dependencies.
    Used by Railway for health probing and by monitoring tools.
    """

    permission_classes = [permissions.AllowAny]

    def get(self, request, *args, **kwargs):
        checks = {
            "status": "ok",
            "db": self._check_db(),
            "redis": self._check_redis(),
        }

        http_status = (
            status.HTTP_200_OK
            if all(v == "ok" for k, v in checks.items() if k != "status")
            else status.HTTP_503_SERVICE_UNAVAILABLE
        )

        if http_status != status.HTTP_200_OK:
            checks["status"] = "degraded"
            logger.error("Healthcheck failed: %s", checks)

        return Response(checks, status=http_status)

    def _check_db(self):
        try:
            connection.ensure_connection()
            return "ok"
        except Exception as exc:
            logger.error("DB healthcheck failed: %s", exc)
            return "error"

    def _check_redis(self):
        try:
            redis_client = Redis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
            redis_client.ping()
            return "ok"
        except RedisError as exc:
            logger.error("Redis healthcheck failed: %s", exc)
            return "error"
