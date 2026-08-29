import uuid
from datetime import date

from django.conf import settings
from django.core.files.storage import default_storage
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .assistant import AssistantValidationError, create_assistant_response
from .assistant_providers import get_assistant_provider
from .cad_fixtures import (
    AUTOMATED_CAD_SMOKE_DATASET,
    MANUAL_CAD_DATASET,
    curated_cad_status,
)
from .cae import (
    CAEValidationError,
    cae_study_payload,
    cae_study_queryset,
    compare_cae_runs,
)
from .cae_connectors import SyntheticCAEConnector, seed_demo_cae_studies
from .capabilities import engineering_capabilities_payload
from .contracts import (
    artifact_payload,
    job_payload,
    review_decision_payload,
    review_payload,
    rule_profile_payload,
)
from .design_review import (
    PROFILE_KEY as DESIGN_REVIEW_PROFILE_KEY,
)
from .design_review import (
    DesignReviewValidationError,
    create_design_review_records,
    create_review_decision,
    get_demo_rule_profile,
)
from .health import collect_readiness
from .hmi import (
    HMIValidationError,
    create_demo_hmi_png,
    create_hmi_extraction,
    export_hmi_workbook,
    extraction_payload,
    review_hmi_fields,
)
from .ingestion import UploadValidationError, create_upload_records
from .job_recovery import stale_job_snapshot
from .knowledge import (
    AUTHORITY_LEVELS,
    DOCUMENT_TYPES,
    KNOWLEDGE_DATASETS,
    PUBLIC_KNOWLEDGE_DATASET,
    KnowledgeValidationError,
    create_knowledge_upload_records,
    knowledge_document_payload,
    search_knowledge,
)
from .models import (
    Artifact,
    ArtifactVersion,
    CAEComparison,
    CAERun,
    CAEStudy,
    HMIExtraction,
    Job,
    KnowledgeDocument,
    KnowledgeSearch,
    ProcessCaseSearch,
    ReviewFinding,
    ReviewRun,
    SimilaritySearch,
    TrialCase,
)
from .process_connectors import SyntheticProcessTrialConnector, seed_demo_process_trials
from .process_trial import (
    ProcessTrialValidationError,
    search_process_cases,
    trial_case_payload,
    trial_case_queryset,
)
from .security import security_preflight_payload
from .similarity import PROFILE_KEY, SimilarityValidationError, create_similarity_records
from .tasks import (
    mark_job_failed,
    process_cad_job,
    process_knowledge_job,
    run_design_review_job,
    run_similarity_job,
    update_job,
)
from .vector_store import VectorStoreError


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


class EngineeringCapabilitiesView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request: Request) -> Response:
        return Response(engineering_capabilities_payload())


class DemoStatusView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request: Request) -> Response:
        readiness = collect_readiness()
        return Response(
            {
                "schema_version": "1.0",
                "environment": settings.APP_ENV,
                "version": settings.APP_VERSION,
                "status": readiness["status"],
                "services": readiness["services"],
                "demo_data": {
                    "curated_cad": curated_cad_status(),
                    "indexed_knowledge_documents": KnowledgeDocument.objects.filter(
                        ingestion_status=KnowledgeDocument.IngestionStatus.INDEXED,
                        classification="public_demo",
                        artifact_version__artifact__dataset_id="public-knowledge-demo-v1",
                    ).count(),
                    "process_trial_cases": TrialCase.objects.filter(
                        classification="public_demo", connector_key="synthetic-process-trial"
                    ).count(),
                    "cae_studies": CAEStudy.objects.filter(classification="public_demo").count(),
                    "hmi_extractions": HMIExtraction.objects.filter(
                        image_artifact_version__classification="public_demo"
                    ).count(),
                },
                "assistant_provider": get_assistant_provider().health().payload(),
                "job_recovery": stale_job_snapshot(),
                "data_scope": "public_demo",
            }
        )


class SecurityPreflightView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request: Request) -> Response:
        return Response(security_preflight_payload(request._request))


def _hmi_extraction_queryset():
    return HMIExtraction.objects.select_related(
        "image_artifact_version__artifact"
    ).prefetch_related("fields", "exports__artifact_version")


class HMIDemoFixtureView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request: Request) -> HttpResponse:
        variant = request.query_params.get("variant", "low-confidence")
        if variant not in {"low-confidence", "clean"}:
            return _error_response(
                "VALIDATION_HMI_FIXTURE_VARIANT",
                "variant must be low-confidence or clean.",
                status.HTTP_400_BAD_REQUEST,
            )
        response = HttpResponse(
            create_demo_hmi_png(low_confidence=variant == "low-confidence"),
            content_type="image/png",
        )
        response["Content-Disposition"] = f'attachment; filename="demo-hmi-{variant}.png"'
        response["X-Content-Type-Options"] = "nosniff"
        return response


class HMIExtractionListCreateView(APIView):
    authentication_classes: list = []
    permission_classes: list = []
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request: Request) -> Response:
        extractions = _hmi_extraction_queryset().filter(
            image_artifact_version__classification="public_demo"
        )[:25]
        return Response(
            {
                "schema_version": "1.0",
                "items": [extraction_payload(extraction) for extraction in extractions],
            }
        )

    def post(self, request: Request) -> Response:
        upload = request.FILES.get("file")
        if upload is None:
            return _error_response(
                "VALIDATION_FILE_REQUIRED",
                "A multipart file field is required.",
                status.HTTP_400_BAD_REQUEST,
            )
        try:
            extraction = create_hmi_extraction(
                upload,
                profile=str(request.data.get("profile", "demo-generic-injection@1.0")),
            )
        except HMIValidationError as exc:
            return _error_response(exc.code, exc.user_message, status.HTTP_400_BAD_REQUEST)
        extraction = _hmi_extraction_queryset().get(pk=extraction.id)
        return Response(extraction_payload(extraction), status=status.HTTP_201_CREATED)


class HMIExtractionDetailView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request: Request, extraction_id: str) -> Response:
        extraction = get_object_or_404(
            _hmi_extraction_queryset(),
            pk=extraction_id,
            image_artifact_version__classification="public_demo",
        )
        return Response(extraction_payload(extraction))


class HMIExtractionReviewView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request: Request, extraction_id: str) -> Response:
        extraction = get_object_or_404(
            _hmi_extraction_queryset(),
            pk=extraction_id,
            image_artifact_version__classification="public_demo",
        )
        try:
            review_hmi_fields(
                extraction,
                request.data.get("fields"),
                reviewer=str(request.data.get("reviewed_by", "demo-reviewer")),
            )
        except HMIValidationError as exc:
            return _error_response(exc.code, exc.user_message, status.HTTP_400_BAD_REQUEST)
        return Response(extraction_payload(_hmi_extraction_queryset().get(pk=extraction.id)))


class HMIExtractionExportView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request: Request, extraction_id: str) -> Response:
        extraction = get_object_or_404(
            _hmi_extraction_queryset(),
            pk=extraction_id,
            image_artifact_version__classification="public_demo",
        )
        try:
            export = export_hmi_workbook(
                extraction,
                created_by=str(request.data.get("created_by", "demo-reviewer")),
            )
        except HMIValidationError as exc:
            http_status = (
                status.HTTP_409_CONFLICT
                if exc.code.startswith("CONFLICT_")
                else status.HTTP_400_BAD_REQUEST
            )
            return _error_response(exc.code, exc.user_message, http_status)
        return Response(
            {
                "schema_version": "1.0",
                "export_id": str(export.id),
                "artifact_version_id": str(export.artifact_version_id),
                "template_version": export.template_version,
                "download_url": (
                    f"/api/v1/artifact-versions/{export.artifact_version_id}/download"
                ),
            },
            status=status.HTTP_201_CREATED,
        )


class AssistantCapabilitiesView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request: Request) -> Response:
        return Response(
            {
                "schema_version": "1.0",
                "context_version": "1.0",
                "ui_action_protocol_version": "1.0",
                "provider": get_assistant_provider().health().payload(),
                "supported_intents": [
                    "explain_similarity",
                    "explain_design_review",
                    "summarize_knowledge",
                    "summarize_process_cases",
                    "explain_cae_comparison",
                    "get_job_status",
                ],
            }
        )


class AssistantMessageView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request: Request) -> Response:
        try:
            payload = create_assistant_response(
                str(request.data.get("message", "")), request.data.get("context")
            )
        except AssistantValidationError as exc:
            return _error_response(exc.code, exc.user_message, status.HTTP_400_BAD_REQUEST)
        return Response(payload)


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
        dataset_id = request.query_params.get("dataset_id", "").strip()
        artifacts = Artifact.objects.filter(kind=Artifact.Kind.CAD_SOURCE)
        if dataset_id:
            artifacts = artifacts.filter(dataset_id=dataset_id[:128])
        else:
            artifacts = artifacts.exclude(dataset_id=AUTOMATED_CAD_SMOKE_DATASET)
        artifacts = artifacts.prefetch_related(
            "versions__input_jobs",
            "versions__cad_model__preview_artifact_version",
            "versions__cad_model__feature_sets",
        ).order_by("-created_at")[:25]
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
                dataset_id=str(request.data.get("dataset_id", MANUAL_CAD_DATASET)),
                product_type=str(request.data.get("product_type", "")),
                material_code=str(request.data.get("material_code", "")),
                idempotency_key=str(idempotency_key) if idempotency_key else None,
                mold_revision_id=(
                    str(request.data.get("mold_revision_id"))
                    if request.data.get("mold_revision_id")
                    else None
                ),
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

        duplicate_count = (
            ArtifactVersion.objects.filter(sha256=records.version.sha256)
            .exclude(id=records.version.id)
            .count()
        )
        warnings = [
            "Basic signature screening passed; a full malware scanner is not configured yet."
        ]
        if duplicate_count:
            warnings.append(
                f"Duplicate content detected in {duplicate_count} existing artifact version(s)."
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
                "warnings": warnings,
                "links": {
                    "artifact": f"/api/v1/cad-artifacts/{records.artifact.id}",
                    "status": f"/api/v1/jobs/{records.job.id}",
                    "ui": f"/engineering/cad?artifact_id={records.artifact.id}",
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
                "versions__input_jobs",
                "versions__cad_model__preview_artifact_version",
                "versions__cad_model__feature_sets",
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
                "input_artifact_version__cad_model__preview_artifact_version",
                "similarity_search",
                "design_review__cad_model__preview_artifact_version",
                "design_review__profile",
                "input_artifact_version__knowledge_document",
            ).prefetch_related(
                "design_review__profile__rules",
                "design_review__findings__rule_version",
                "design_review__findings__decisions",
            ),
            pk=job_id,
        )
        return Response(job_payload(job))


class KnowledgeDocumentListCreateView(APIView):
    authentication_classes: list = []
    permission_classes: list = []
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request: Request) -> Response:
        documents = (
            KnowledgeDocument.objects.select_related("artifact_version__artifact")
            .order_by("-created_at")
            .filter(artifact_version__artifact__dataset_id=PUBLIC_KNOWLEDGE_DATASET)[:50]
        )
        return Response(
            {
                "schema_version": "1.0",
                "items": [knowledge_document_payload(document) for document in documents],
            }
        )

    def post(self, request: Request) -> Response:
        upload = request.FILES.get("file")
        if upload is None:
            return _error_response(
                "VALIDATION_FILE_REQUIRED",
                "A multipart file field is required.",
                status.HTTP_400_BAD_REQUEST,
            )

        def optional_date(field: str) -> date | None:
            raw = str(request.data.get(field, "")).strip()
            if not raw:
                return None
            try:
                return date.fromisoformat(raw)
            except ValueError as exc:
                raise KnowledgeValidationError(
                    "VALIDATION_EFFECTIVE_DATE", f"{field} must use YYYY-MM-DD."
                ) from exc

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
            records = create_knowledge_upload_records(
                upload,
                title=str(request.data.get("title", "")),
                document_type=str(request.data.get("document_type", "demo_sop")),
                authority_level=str(request.data.get("authority_level", "demo")),
                owner=str(request.data.get("owner", "demo-knowledge-curator")),
                language=str(request.data.get("language", "en")),
                effective_from=optional_date("effective_from"),
                effective_to=optional_date("effective_to"),
                idempotency_key=str(idempotency_key) if idempotency_key else None,
                dataset_id=str(request.data.get("dataset_id", PUBLIC_KNOWLEDGE_DATASET)),
                publication_status="draft",
                document_key=(
                    str(request.data.get("document_key"))
                    if request.data.get("document_key")
                    else None
                ),
                supersedes_document_id=(
                    str(request.data.get("supersedes_document_id"))
                    if request.data.get("supersedes_document_id")
                    else None
                ),
            )
        except KnowledgeValidationError as exc:
            conflict = exc.code.startswith("CONFLICT_")
            return _error_response(
                exc.code,
                exc.user_message,
                status.HTTP_409_CONFLICT if conflict else status.HTTP_400_BAD_REQUEST,
            )
        if records.created:
            try:
                process_knowledge_job.apply_async(args=[str(records.job.id)], queue="general")
            except Exception:
                records.document.ingestion_status = KnowledgeDocument.IngestionStatus.FAILED
                records.document.error_code = "JOB_QUEUE_UNAVAILABLE"
                records.document.save(
                    update_fields=["ingestion_status", "error_code", "updated_at"]
                )
                update_job(
                    records.job.id,
                    state=Job.State.FAILED,
                    stage="failed",
                    progress=100,
                    error_code="JOB_QUEUE_UNAVAILABLE",
                    error_message="The knowledge ingestion job could not be queued.",
                )
                return _error_response(
                    "JOB_QUEUE_UNAVAILABLE",
                    "The knowledge ingestion job could not be queued.",
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                )
        return Response(
            {
                "schema_version": "1.0",
                "status": "accepted",
                "artifact_id": str(records.artifact.id),
                "artifact_version_id": str(records.version.id),
                "document_id": str(records.document.id),
                "job_id": str(records.job.id),
                "idempotent_replay": not records.created,
                "links": {
                    "status": f"/api/v1/jobs/{records.job.id}",
                    "document": f"/api/v1/knowledge-documents/{records.document.id}",
                },
            },
            status=status.HTTP_202_ACCEPTED,
        )


class KnowledgeDocumentDetailView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request: Request, document_id: str) -> Response:
        document = get_object_or_404(
            KnowledgeDocument.objects.select_related("artifact_version__artifact"), pk=document_id
        )
        return Response(knowledge_document_payload(document))


class KnowledgeSearchListCreateView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request: Request) -> Response:
        def string_list(field: str, allowed: set[str]) -> list[str]:
            value = request.data.get(field, [])
            if value is None:
                return []
            if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                raise KnowledgeValidationError(
                    "VALIDATION_KNOWLEDGE_FILTER", f"{field} must be an array of strings."
                )
            normalized = [item.strip() for item in value if item.strip()]
            if set(normalized) - allowed:
                raise KnowledgeValidationError(
                    "VALIDATION_KNOWLEDGE_FILTER", f"{field} contains an unsupported value."
                )
            return normalized

        try:
            top_k = int(request.data.get("top_k", 5))
            search = search_knowledge(
                str(request.data.get("query", "")),
                top_k=top_k,
                document_types=string_list("document_types", DOCUMENT_TYPES),
                authority_levels=string_list("authority_levels", AUTHORITY_LEVELS),
                dataset_ids=string_list("dataset_ids", KNOWLEDGE_DATASETS),
            )
        except (TypeError, ValueError):
            return _error_response(
                "VALIDATION_TOP_K", "top_k must be an integer.", status.HTTP_400_BAD_REQUEST
            )
        except KnowledgeValidationError as exc:
            return _error_response(exc.code, exc.user_message, status.HTTP_400_BAD_REQUEST)
        except VectorStoreError as exc:
            return _error_response(exc.code, exc.user_message, status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response({"search_id": str(search.id), **search.result}, status=status.HTTP_200_OK)


class KnowledgeSearchDetailView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request: Request, search_id: str) -> Response:
        search = get_object_or_404(KnowledgeSearch, pk=search_id)
        return Response({"search_id": str(search.id), **search.result})


class RuleProfileListView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request: Request) -> Response:
        profile = get_demo_rule_profile()
        return Response({"schema_version": "1.0", "items": [rule_profile_payload(profile)]})


class CAEDemoFixtureView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request: Request) -> Response:
        return Response(
            {
                "schema_version": "1.0",
                "connector": SyntheticCAEConnector().health(),
                "loaded_study_count": CAEStudy.objects.filter(
                    connector_key="synthetic-cae-structured-export"
                ).count(),
            }
        )

    def post(self, request: Request) -> Response:
        try:
            result = seed_demo_cae_studies()
        except ValueError as exc:
            return _error_response(
                "CONFLICT_CAE_FIXTURE_VERSION", str(exc), status.HTTP_409_CONFLICT
            )
        return Response(
            {
                "schema_version": "1.0",
                "connector_key": result.connector_key,
                "source_version": result.source_version,
                "created": result.created,
                "existing": result.existing,
                "study_ids": result.study_ids,
            },
            status=status.HTTP_201_CREATED if result.created else status.HTTP_200_OK,
        )


class CAEStudyListView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request: Request) -> Response:
        studies = cae_study_queryset().order_by("study_code")[:50]
        items = [cae_study_payload(item) for item in studies if "public-demo" in item.acl_scopes]
        return Response({"schema_version": "1.0", "items": items})


class CAEStudyDetailView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request: Request, study_id: str) -> Response:
        study = get_object_or_404(cae_study_queryset(), pk=study_id)
        if "public-demo" not in study.acl_scopes:
            return _error_response(
                "RESOURCE_NOT_FOUND",
                "The requested resource is not available.",
                status.HTTP_404_NOT_FOUND,
            )
        return Response(cae_study_payload(study))


class CAEComparisonListCreateView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request: Request) -> Response:
        try:
            baseline_id = uuid.UUID(str(request.data.get("baseline_run_id", "")))
            candidate_id = uuid.UUID(str(request.data.get("candidate_run_id", "")))
        except (TypeError, ValueError):
            return _error_response(
                "VALIDATION_CAE_RUN_ID",
                "baseline_run_id and candidate_run_id must be UUIDs.",
                status.HTTP_400_BAD_REQUEST,
            )
        runs = CAERun.objects.select_related("study").prefetch_related("results")
        baseline = get_object_or_404(runs, pk=baseline_id, study__classification="public_demo")
        candidate = get_object_or_404(runs, pk=candidate_id, study__classification="public_demo")
        if "public-demo" not in baseline.study.acl_scopes or "public-demo" not in (
            candidate.study.acl_scopes
        ):
            return _error_response(
                "RESOURCE_NOT_FOUND",
                "The requested resource is not available.",
                status.HTTP_404_NOT_FOUND,
            )
        try:
            comparison = compare_cae_runs(baseline, candidate)
        except CAEValidationError as exc:
            return _error_response(exc.code, exc.user_message, status.HTTP_400_BAD_REQUEST)
        return Response(comparison.result, status=status.HTTP_200_OK)


class CAEComparisonDetailView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request: Request, comparison_id: str) -> Response:
        comparison = get_object_or_404(
            CAEComparison.objects.select_related("baseline_run__study", "candidate_run__study"),
            pk=comparison_id,
            baseline_run__study__classification="public_demo",
            candidate_run__study__classification="public_demo",
        )
        if "public-demo" not in comparison.baseline_run.study.acl_scopes or "public-demo" not in (
            comparison.candidate_run.study.acl_scopes
        ):
            return _error_response(
                "RESOURCE_NOT_FOUND",
                "The requested resource is not available.",
                status.HTTP_404_NOT_FOUND,
            )
        return Response(comparison.result)


class ProcessTrialDemoFixtureView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request: Request) -> Response:
        return Response(
            {
                "schema_version": "1.0",
                "connector": SyntheticProcessTrialConnector().health(),
                "loaded_case_count": TrialCase.objects.filter(
                    connector_key="synthetic-process-trial"
                ).count(),
            }
        )

    def post(self, request: Request) -> Response:
        try:
            result = seed_demo_process_trials()
        except ValueError as exc:
            return _error_response(
                "CONFLICT_PROCESS_FIXTURE_VERSION",
                str(exc),
                status.HTTP_409_CONFLICT,
            )
        return Response(
            {
                "schema_version": "1.0",
                "connector_key": result.connector_key,
                "source_version": result.source_version,
                "created": result.created,
                "existing": result.existing,
                "case_ids": result.case_ids,
            },
            status=status.HTTP_201_CREATED if result.created else status.HTTP_200_OK,
        )


class TrialCaseListView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request: Request) -> Response:
        trials = trial_case_queryset().order_by("case_code")[:50]
        items = [trial_case_payload(trial) for trial in trials if "public-demo" in trial.acl_scopes]
        return Response({"schema_version": "1.0", "items": items})


class TrialCaseDetailView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request: Request, trial_case_id: str) -> Response:
        trial = get_object_or_404(trial_case_queryset(), pk=trial_case_id)
        if "public-demo" not in trial.acl_scopes:
            return _error_response(
                "RESOURCE_NOT_FOUND",
                "The requested resource is not available.",
                status.HTTP_404_NOT_FOUND,
            )
        return Response(trial_case_payload(trial))


class ProcessCaseSearchListCreateView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request: Request) -> Response:
        try:
            search = search_process_cases(request.data)
        except ProcessTrialValidationError as exc:
            return _error_response(exc.code, exc.user_message, status.HTTP_400_BAD_REQUEST)
        return Response(search.result, status=status.HTTP_200_OK)


class ProcessCaseSearchDetailView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request: Request, search_id: str) -> Response:
        search = get_object_or_404(ProcessCaseSearch, pk=search_id)
        return Response(search.result)


class DesignReviewListCreateView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request: Request) -> Response:
        version_value = request.data.get("cad_artifact_version_id")
        if not version_value:
            return _error_response(
                "VALIDATION_REVIEW_ARTIFACT",
                "cad_artifact_version_id is required.",
                status.HTTP_400_BAD_REQUEST,
            )
        try:
            version_id = uuid.UUID(str(version_value))
        except (TypeError, ValueError):
            return _error_response(
                "VALIDATION_REVIEW_ARTIFACT",
                "cad_artifact_version_id must be a UUID.",
                status.HTTP_400_BAD_REQUEST,
            )
        requested_profile = str(request.data.get("profile", DESIGN_REVIEW_PROFILE_KEY))
        if requested_profile != DESIGN_REVIEW_PROFILE_KEY:
            return _error_response(
                "VALIDATION_REVIEW_PROFILE",
                f"Only {DESIGN_REVIEW_PROFILE_KEY} is available in the Demo environment.",
                status.HTTP_400_BAD_REQUEST,
            )
        version = get_object_or_404(
            ArtifactVersion.objects.select_related("artifact", "cad_model"),
            pk=version_id,
            artifact__kind=Artifact.Kind.CAD_SOURCE,
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
            records = create_design_review_records(
                version,
                context=request.data.get("context"),
                idempotency_key=str(idempotency_key) if idempotency_key else None,
            )
        except DesignReviewValidationError as exc:
            conflict = exc.code.startswith("CONFLICT_") or exc.code.endswith("MISMATCH")
            return _error_response(
                exc.code,
                exc.user_message,
                status.HTTP_409_CONFLICT if conflict else status.HTTP_400_BAD_REQUEST,
            )

        if records.created:
            try:
                run_design_review_job.apply_async(args=[str(records.job.id)], queue="cad")
            except Exception:
                records.review.review_status = ReviewRun.Status.FAILED
                records.review.save(update_fields=["review_status"])
                update_job(
                    records.job.id,
                    state=Job.State.FAILED,
                    stage="failed",
                    progress=100,
                    error_code="JOB_QUEUE_UNAVAILABLE",
                    error_message="The design review job could not be queued.",
                )
                return _error_response(
                    "JOB_QUEUE_UNAVAILABLE",
                    "The design review job could not be queued.",
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                )

        return Response(
            {
                "schema_version": "1.0",
                "status": "accepted",
                "review_id": str(records.review.id),
                "job_id": str(records.job.id),
                "idempotent_replay": not records.created,
                "links": {
                    "status": f"/api/v1/jobs/{records.job.id}",
                    "result": f"/api/v1/design-reviews/{records.review.id}",
                    "ui": f"/design-reviews/{records.review.id}",
                },
            },
            status=status.HTTP_202_ACCEPTED,
        )


class DesignReviewDetailView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request: Request, review_id: str) -> Response:
        review = get_object_or_404(
            ReviewRun.objects.select_related(
                "job",
                "profile",
                "cad_model__preview_artifact_version",
            ).prefetch_related("profile__rules", "findings__rule_version", "findings__decisions"),
            pk=review_id,
        )
        return Response(review_payload(review))


class ReviewFindingDecisionCreateView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request: Request, review_id: str, finding_id: str) -> Response:
        finding = get_object_or_404(
            ReviewFinding.objects.select_related("review_run", "rule_version"),
            pk=finding_id,
            review_run_id=review_id,
        )
        try:
            decision = create_review_decision(
                finding,
                decision=str(request.data.get("decision", "")),
                reason=str(request.data.get("reason", ""))[:2000],
                decided_by=str(request.data.get("decided_by", "demo-reviewer"))[:128],
                approved_by=str(request.data.get("approved_by", ""))[:128],
            )
        except DesignReviewValidationError as exc:
            return _error_response(exc.code, exc.user_message, status.HTTP_400_BAD_REQUEST)
        return Response(
            {
                "schema_version": "1.0",
                "finding_result": finding.result,
                "record": review_decision_payload(decision),
            },
            status=status.HTTP_201_CREATED,
        )


class SimilaritySearchListCreateView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request: Request) -> Response:
        query = request.data.get("query", {})
        if not isinstance(query, dict) or not query.get("cad_artifact_version_id"):
            return _error_response(
                "VALIDATION_QUERY_ARTIFACT",
                "query.cad_artifact_version_id is required.",
                status.HTTP_400_BAD_REQUEST,
            )
        try:
            query_version_id = uuid.UUID(str(query["cad_artifact_version_id"]))
        except (TypeError, ValueError):
            return _error_response(
                "VALIDATION_QUERY_ARTIFACT",
                "query.cad_artifact_version_id must be a UUID.",
                status.HTTP_400_BAD_REQUEST,
            )
        requested_profile = str(request.data.get("profile", PROFILE_KEY))
        if requested_profile != PROFILE_KEY:
            return _error_response(
                "VALIDATION_SIMILARITY_PROFILE",
                f"Only {PROFILE_KEY} is available in the Demo environment.",
                status.HTTP_400_BAD_REQUEST,
            )
        query_version = get_object_or_404(
            ArtifactVersion.objects.select_related("artifact", "cad_model"),
            pk=query_version_id,
            artifact__kind=Artifact.Kind.CAD_SOURCE,
        )
        try:
            top_k = int(request.data.get("top_k", 10))
        except (TypeError, ValueError):
            return _error_response(
                "VALIDATION_TOP_K", "top_k must be an integer.", status.HTTP_400_BAD_REQUEST
            )
        filters = request.data.get("filters", {})
        if not isinstance(filters, dict):
            return _error_response(
                "VALIDATION_FILTER", "filters must be an object.", status.HTTP_400_BAD_REQUEST
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
            records = create_similarity_records(
                query_version,
                top_k=top_k,
                filters=filters,
                idempotency_key=str(idempotency_key) if idempotency_key else None,
            )
        except SimilarityValidationError as exc:
            conflict = exc.code.startswith("CONFLICT_")
            return _error_response(
                exc.code,
                exc.user_message,
                status.HTTP_409_CONFLICT if conflict else status.HTTP_400_BAD_REQUEST,
            )

        if records.created:
            try:
                run_similarity_job.apply_async(args=[str(records.job.id)], queue="cad")
            except Exception:
                update_job(
                    records.job.id,
                    state=Job.State.FAILED,
                    stage="failed",
                    progress=100,
                    error_code="JOB_QUEUE_UNAVAILABLE",
                    error_message="The similarity job could not be queued.",
                )
                return _error_response(
                    "JOB_QUEUE_UNAVAILABLE",
                    "The similarity job could not be queued.",
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                )

        return Response(
            {
                "schema_version": "1.0",
                "status": "accepted",
                "search_id": str(records.search.id),
                "job_id": str(records.job.id),
                "idempotent_replay": not records.created,
                "links": {
                    "status": f"/api/v1/jobs/{records.job.id}",
                    "result": f"/api/v1/similarity-searches/{records.search.id}",
                    "ui": f"/similarity/jobs/{records.job.id}",
                },
            },
            status=status.HTTP_202_ACCEPTED,
        )


class SimilaritySearchDetailView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request: Request, search_id: str) -> Response:
        search = get_object_or_404(SimilaritySearch.objects.select_related("job"), pk=search_id)
        return Response(
            {
                "schema_version": "1.0",
                "search_id": str(search.id),
                "state": search.job.state,
                "job_id": str(search.job.id),
                "result": search.result if search.job.state == Job.State.SUCCEEDED else None,
            }
        )


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
            as_attachment=version.artifact.kind
            not in {Artifact.Kind.CAD_PREVIEW, Artifact.Kind.KNOWLEDGE_SOURCE},
            filename=version.original_filename,
        )
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Security-Policy"] = "default-src 'none'; sandbox"
        return response
