from django.conf import settings
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .health import collect_readiness


class LiveView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request: Request) -> Response:
        return Response({"status": "ok", "service": "platform-api"})


class ReadyView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request: Request) -> Response:
        readiness = collect_readiness()
        http_status = status.HTTP_200_OK
        if readiness["status"] != "ok":
            http_status = status.HTTP_503_SERVICE_UNAVAILABLE
        return Response(readiness, status=http_status)


class SystemInfoView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request: Request) -> Response:
        return Response(
            {
                "name": settings.APP_NAME,
                "environment": settings.APP_ENV,
                "version": settings.APP_VERSION,
                "api_version": "v1",
            }
        )
