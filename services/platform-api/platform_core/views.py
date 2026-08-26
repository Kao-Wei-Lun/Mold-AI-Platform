from django.conf import settings
from django.core.files.storage import default_storage
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .contracts import artifact_payload, job_payload
from .health import collect_readiness
from .ingestion import UploadValidationError, create_upload_records
from .models import Artifact, ArtifactVersion, Job
from .tasks import mark_job_failed, process_cad_job


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


def _error_response(code: str, message: str, http_status: int) -> Response:
    return Response(
        {"error": {"code": code, "message": message, "retryable": False}},
        status=http_status,
    )


class CADArtifactListCreateView(APIView):
    authentication_classes: list = []
    permission_classes: list = []
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request: Request) -> Response:
        artifacts = (
            Artifact.objects.filter(kind=Artifact.Kind.CAD_SOURCE)
            .prefetch_related(
                "versions__input_jobs", "versions__cad_model__preview_artifact_version"
            )
            .order_by("-created_at")[:25]
        )
        return Response(
            {"schema_version": "1.0", "items": [artifact_payload(a) for a in artifacts]}
        )

    def post(self, request: Request) -> Response:
        upload = request.FILES.get("file")
        if upload is None:
            return _error_response(
                "VALIDATION_FILE_REQUIRED",
                "A multipart file field is required.",
                status.HTTP_400_BAD_REQUEST,
            )

        idempotency_key = request.data.get("idempotency_key") or request.headers.get(
            "Idempotency-Key"
        )
        if idempotency_key and len(str(idempotency_key)) > 255:
            return _error_response(
                "VALIDATION_IDEMPOTENCY_KEY",
                "The idempotency key must be 255 characters or fewer.",
                status.HTTP_400_BAD_REQUEST,
            )

        try:
            records = create_upload_records(
                upload,
                artifact_name=str(request.data.get("artifact_name", "")),
                idempotency_key=str(idempotency_key) if idempotency_key else None,
            )
        except UploadValidationError as exc:
            http_status = (
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
                if exc.code == "VALIDATION_FILE_TOO_LARGE"
                else status.HTTP_400_BAD_REQUEST
            )
            return _error_response(exc.code, exc.user_message, http_status)

        if records.created:
            try:
                process_cad_job.apply_async(args=[str(records.job.id)], queue="cad")
            except Exception:
                mark_job_failed(
                    records.job.id,
                    "JOB_QUEUE_UNAVAILABLE",
                    "The CAD job could not be queued. Try again after the worker service recovers.",
                )
                return _error_response(
                    "JOB_QUEUE_UNAVAILABLE",
                    "The CAD job could not be queued.",
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                )

        response_status = status.HTTP_202_ACCEPTED
        return Response(
            {
                "schema_version": "1.0",
                "status": "accepted",
                "artifact_id": str(records.artifact.id),
                "artifact_version_id": str(records.version.id),
                "job_id": str(records.job.id),
                "idempotent_replay": not records.created,
                "warnings": [
                    "Basic signature screening passed; "
                    "a full malware scanner is not configured yet."
                ],
                "links": {
                    "artifact": f"/api/v1/cad-artifacts/{records.artifact.id}",
                    "status": f"/api/v1/jobs/{records.job.id}",
                    "ui": f"/cad/jobs/{records.job.id}",
                },
            },
            status=response_status,
        )


class CADArtifactDetailView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request: Request, artifact_id: str) -> Response:
        artifact = get_object_or_404(
            Artifact.objects.prefetch_related(
                "versions__input_jobs", "versions__cad_model__preview_artifact_version"
            ),
            pk=artifact_id,
            kind=Artifact.Kind.CAD_SOURCE,
        )
        return Response(artifact_payload(artifact))


class JobDetailView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request: Request, job_id: str) -> Response:
        job = get_object_or_404(
            Job.objects.select_related(
                "input_artifact_version__cad_model__preview_artifact_version"
            ),
            pk=job_id,
        )
        return Response(job_payload(job))


class ArtifactVersionDownloadView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request: Request, artifact_version_id: str) -> FileResponse:
        version = get_object_or_404(ArtifactVersion, pk=artifact_version_id)
        if not default_storage.exists(version.storage_key):
            return _error_response(
                "ARTIFACT_CONTENT_MISSING",
                "The artifact content is not available.",
                status.HTTP_404_NOT_FOUND,
            )
        source = default_storage.open(version.storage_key, "rb")
        response = FileResponse(
            source,
            content_type=version.media_type,
            as_attachment=version.artifact.kind != Artifact.Kind.CAD_PREVIEW,
            filename=version.original_filename,
        )
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Security-Policy"] = "default-src 'none'; sandbox"
        return response
