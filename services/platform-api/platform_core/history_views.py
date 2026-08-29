from __future__ import annotations

import csv
import json
import uuid

from django.http import HttpResponse
from django.utils import timezone
from rest_framework.authentication import SessionAuthentication
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .cae import compare_cae_runs
from .contracts import job_payload, review_payload
from .design_review import create_design_review_records
from .identity import audit_identity_event
from .knowledge import search_knowledge
from .models import (
    ArtifactVersion,
    AuditEvent,
    CAEComparison,
    HistoryRecordState,
    Job,
    JobEvent,
    KnowledgeSearch,
    LineageEdge,
    ProcessCaseSearch,
    ReviewRun,
    SimilaritySearch,
)
from .process_trial import search_process_cases
from .similarity import create_similarity_records
from .tasks import (
    process_cad_job,
    process_knowledge_job,
    run_design_review_job,
    run_similarity_job,
    update_job,
)


def _error(request: Request, code: str, message: str, http_status: int, **details) -> Response:
    return Response(
        {
            "error": {
                "code": code,
                "message": message,
                "retryable": http_status >= 500,
                "request_id": getattr(request._request, "mold_ai_request_id", ""),
                "details": details,
            }
        },
        status=http_status,
    )


def _require(request: Request, permission: str) -> Response | None:
    if permission in getattr(request._request, "mold_ai_permissions", set()):
        return None
    return _error(request, "ACCESS_DENIED", f"The account does not grant {permission}.", 403)


def _actor(request: Request) -> str:
    return str(getattr(request._request, "mold_ai_actor_id", "anonymous"))


def _reason(request: Request) -> tuple[str, Response | None]:
    reason = str(request.data.get("reason", "")).strip()
    if not reason:
        return "", _error(request, "VALIDATION_REASON_REQUIRED", "A reason is required.", 400)
    return reason[:512], None


def _page(request: Request) -> tuple[int, int] | Response:
    try:
        return (
            max(1, int(request.query_params.get("page", 1))),
            min(100, max(1, int(request.query_params.get("page_size", 25)))),
        )
    except ValueError:
        return _error(request, "VALIDATION_PAGINATION", "Invalid page or page_size.", 400)


def _state(record_type: str, record_id: uuid.UUID) -> dict[str, object]:
    state = HistoryRecordState.objects.filter(
        record_type=record_type, record_id=record_id
    ).first()
    return {
        "status": state.status if state else "active",
        "row_version": state.row_version if state else 1,
        "archive_reason": state.archive_reason if state else None,
        "archived_at": state.archived_at.isoformat() if state and state.archived_at else None,
    }


def _analysis_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for item in SimilaritySearch.objects.select_related("job", "query_feature_set")[:100]:
        rows.append(
            {
                "analysis_type": "similarity",
                "analysis_id": str(item.id),
                "title": f"Similarity · {item.query_feature_set_id}",
                "state": item.job.state,
                "job_id": str(item.job_id),
                "created_at": item.created_at.isoformat(),
                "result_count": len(item.result.get("candidates", [])),
                "lifecycle": _state("similarity", item.id),
            }
        )
    for item in ReviewRun.objects.select_related("job", "profile")[:100]:
        rows.append(
            {
                "analysis_type": "design_review",
                "analysis_id": str(item.id),
                "title": f"Design review · {item.profile.profile_key}@{item.profile.version}",
                "state": item.review_status,
                "job_id": str(item.job_id),
                "created_at": item.created_at.isoformat(),
                "result_count": item.findings.count(),
                "lifecycle": _state("design_review", item.id),
            }
        )
    for item in KnowledgeSearch.objects.all()[:100]:
        rows.append(
            {
                "analysis_type": "knowledge_search",
                "analysis_id": str(item.id),
                "title": f"Knowledge · {item.query[:80]}",
                "state": "abstained" if item.abstained else "completed",
                "job_id": None,
                "created_at": item.created_at.isoformat(),
                "result_count": len(item.result.get("results", [])),
                "lifecycle": _state("knowledge_search", item.id),
            }
        )
    for item in ProcessCaseSearch.objects.all()[:100]:
        rows.append(
            {
                "analysis_type": "process_search",
                "analysis_id": str(item.id),
                "title": "Process / trial case search",
                "state": "abstained" if item.abstained else "completed",
                "job_id": None,
                "created_at": item.created_at.isoformat(),
                "result_count": int(item.result.get("result_count", 0)),
                "lifecycle": _state("process_search", item.id),
            }
        )
    for item in CAEComparison.objects.select_related("baseline_run", "candidate_run")[:100]:
        rows.append(
            {
                "analysis_type": "cae_comparison",
                "analysis_id": str(item.id),
                "title": f"CAE · {item.baseline_run.run_code} vs {item.candidate_run.run_code}",
                "state": "compatible" if item.compatible else "blocked",
                "job_id": None,
                "created_at": item.created_at.isoformat(),
                "result_count": len(item.result.get("metric_deltas", [])),
                "lifecycle": _state("cae_comparison", item.id),
            }
        )
    return sorted(rows, key=lambda item: str(item["created_at"]), reverse=True)


def _analysis_detail(record_type: str, record_id: str) -> dict[str, object] | None:
    if record_type == "similarity":
        item = (
            SimilaritySearch.objects.select_related("job", "query_feature_set__cad_model")
            .filter(id=record_id)
            .first()
        )
        if item:
            return {
                "analysis_type": record_type,
                "analysis_id": str(item.id),
                "job": job_payload(item.job),
                "inputs": {
                    "artifact_version_id": str(
                        item.query_feature_set.cad_model.artifact_version_id
                    ),
                    "profile_id": str(item.profile_id),
                    "top_k": item.top_k,
                    "filters": item.filters,
                },
                "result": item.result,
                "created_at": item.created_at.isoformat(),
                "lifecycle": _state(record_type, item.id),
            }
    elif record_type == "design_review":
        item = (
            ReviewRun.objects.select_related(
                "job", "profile", "cad_model__preview_artifact_version"
            )
            .prefetch_related("profile__rules", "findings__rule_version", "findings__decisions")
            .filter(id=record_id)
            .first()
        )
        if item:
            return {
                "analysis_type": record_type,
                "analysis_id": str(item.id),
                "inputs": item.input_snapshot,
                "result": review_payload(item),
                "created_at": item.created_at.isoformat(),
                "lifecycle": _state(record_type, item.id),
            }
    elif record_type == "knowledge_search":
        item = KnowledgeSearch.objects.filter(id=record_id).first()
        if item:
            return {
                "analysis_type": record_type,
                "analysis_id": str(item.id),
                "inputs": {
                    "query": item.query,
                    "filters": item.filters,
                    "retrieval_config": item.retrieval_config,
                    "principal_scopes": item.principal_scopes,
                },
                "result": item.result,
                "created_at": item.created_at.isoformat(),
                "lifecycle": _state(record_type, item.id),
            }
    elif record_type == "process_search":
        item = ProcessCaseSearch.objects.filter(id=record_id).first()
        if item:
            return {
                "analysis_type": record_type,
                "analysis_id": str(item.id),
                "inputs": item.request_snapshot,
                "result": item.result,
                "created_at": item.created_at.isoformat(),
                "lifecycle": _state(record_type, item.id),
            }
    elif record_type == "cae_comparison":
        item = CAEComparison.objects.select_related("baseline_run", "candidate_run").filter(
            id=record_id
        ).first()
        if item:
            return {
                "analysis_type": record_type,
                "analysis_id": str(item.id),
                "inputs": {
                    "baseline_run_id": str(item.baseline_run_id),
                    "candidate_run_id": str(item.candidate_run_id),
                    "request_snapshot": item.request_snapshot,
                },
                "result": {
                    "compatible": item.compatible,
                    "incompatibilities": item.incompatibilities,
                    **item.result,
                },
                "created_at": item.created_at.isoformat(),
                "lifecycle": _state(record_type, item.id),
            }
    return None


class AnalysisHistoryView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def get(self, request: Request) -> Response:
        if denied := _require(request, "analysis:read"):
            return denied
        paging = _page(request)
        if isinstance(paging, Response):
            return paging
        page, size = paging
        rows = _analysis_rows()
        if record_type := request.query_params.get("type"):
            rows = [item for item in rows if item["analysis_type"] == record_type]
        if status := request.query_params.get("lifecycle"):
            rows = [item for item in rows if item["lifecycle"]["status"] == status]
        total = len(rows)
        start = (page - 1) * size
        return Response(
            {
                "schema_version": "1.0",
                "items": rows[start : start + size],
                "page": {"number": page, "size": size, "total": total},
            }
        )


class AnalysisDetailView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def get(self, request: Request, record_type: str, record_id: str) -> Response:
        if denied := _require(request, "analysis:read"):
            return denied
        detail = _analysis_detail(record_type, record_id)
        if detail is None:
            return _error(request, "NOT_FOUND", "Analysis result not found.", 404)
        return Response(detail)

    def post(self, request: Request, record_type: str, record_id: str) -> Response:
        if denied := _require(request, "analysis:manage"):
            return denied
        reason, invalid = _reason(request)
        if invalid:
            return invalid
        action = str(request.data.get("action", ""))
        if action in {"archive", "restore"}:
            try:
                parsed_id = record_id if isinstance(record_id, uuid.UUID) else uuid.UUID(record_id)
            except ValueError:
                return _error(request, "VALIDATION_ID", "Analysis ID is invalid.", 400)
            if _analysis_detail(record_type, record_id) is None:
                return _error(request, "NOT_FOUND", "Analysis result not found.", 404)
            state, _ = HistoryRecordState.objects.get_or_create(
                record_type=record_type, record_id=parsed_id
            )
            if int(request.data.get("row_version", 0)) != state.row_version:
                return _error(request, "CONCURRENT_MODIFICATION", "Analysis state changed.", 409)
            state.status = "archived" if action == "archive" else "active"
            state.archive_reason = reason if action == "archive" else ""
            state.archived_by = _actor(request) if action == "archive" else ""
            state.archived_at = timezone.now() if action == "archive" else None
            state.row_version += 1
            state.save()
            audit_identity_event(
                f"analysis.{action}.v1",
                actor_id=_actor(request),
                target_refs=[f"{record_type}:{record_id}"],
                detail={"reason": reason},
            )
            return Response(_analysis_detail(record_type, record_id))
        if action != "rerun":
            return _error(request, "VALIDATION_ACTION", "Use rerun, archive or restore.", 400)
        new_type, new_id, job_id = _rerun_analysis(record_type, record_id)
        if not new_id:
            return _error(request, "ANALYSIS_RERUN_UNSUPPORTED", "Analysis cannot be rerun.", 409)
        audit_identity_event(
            "analysis.rerun.v1",
            actor_id=_actor(request),
            target_refs=[f"{record_type}:{record_id}", f"{new_type}:{new_id}"],
            detail={"reason": reason, "job_id": job_id},
        )
        return Response(
            {"analysis_type": new_type, "analysis_id": new_id, "job_id": job_id}, status=201
        )


def _rerun_analysis(record_type: str, record_id: str) -> tuple[str, str, str | None]:
    if record_type == "similarity":
        source = (
            SimilaritySearch.objects.select_related("query_feature_set__cad_model")
            .filter(id=record_id)
            .first()
        )
        if source:
            records = create_similarity_records(
                source.query_feature_set.cad_model.artifact_version,
                top_k=source.top_k,
                filters=source.filters,
            )
            run_similarity_job.apply_async(args=[str(records.job.id)], queue="cad")
            return record_type, str(records.search.id), str(records.job.id)
    elif record_type == "design_review":
        source = ReviewRun.objects.select_related("cad_model").filter(id=record_id).first()
        if source:
            records = create_design_review_records(
                source.cad_model.artifact_version, context=source.context
            )
            run_design_review_job.apply_async(args=[str(records.job.id)], queue="cad")
            return record_type, str(records.review.id), str(records.job.id)
    elif record_type == "knowledge_search":
        source = KnowledgeSearch.objects.filter(id=record_id).first()
        if source:
            filters = source.filters if isinstance(source.filters, dict) else {}
            rerun = search_knowledge(
                source.query,
                top_k=int(source.retrieval_config.get("top_k", 5)),
                document_types=filters.get("document_types", []),
                authority_levels=filters.get("authority_levels", []),
                dataset_ids=filters.get("dataset_ids", []),
            )
            return record_type, str(rerun.id), None
    elif record_type == "process_search":
        source = ProcessCaseSearch.objects.filter(id=record_id).first()
        if source:
            rerun = search_process_cases(source.request_snapshot)
            return record_type, str(rerun.id), None
    elif record_type == "cae_comparison":
        source = CAEComparison.objects.select_related("baseline_run", "candidate_run").filter(
            id=record_id
        ).first()
        if source:
            rerun = compare_cae_runs(source.baseline_run, source.candidate_run)
            return record_type, str(rerun.id), None
    return record_type, "", None


def _job_detail(job: Job) -> dict[str, object]:
    payload = job_payload(job)
    payload["input_snapshot"] = job.input_snapshot
    payload["events"] = [
        {
            "event_id": str(event.id),
            "from_state": event.from_state or None,
            "to_state": event.to_state,
            "stage": event.stage,
            "progress": event.progress,
            "detail": event.detail,
            "created_at": event.created_at.isoformat(),
        }
        for event in job.events.all()
    ]
    return payload


class JobHistoryView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def get(self, request: Request) -> Response:
        if denied := _require(request, "job:read"):
            return denied
        paging = _page(request)
        if isinstance(paging, Response):
            return paging
        page, size = paging
        jobs = Job.objects.select_related("input_artifact_version").order_by("-created_at")
        if state := request.query_params.get("state"):
            jobs = jobs.filter(state=state)
        if capability := request.query_params.get("capability"):
            jobs = jobs.filter(capability_id=capability)
        total = jobs.count()
        start = (page - 1) * size
        return Response(
            {
                "schema_version": "1.0",
                "items": [job_payload(job) for job in jobs[start : start + size]],
                "page": {"number": page, "size": size, "total": total},
            }
        )


class JobHistoryDetailView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def get(self, request: Request, job_id: str) -> Response:
        if denied := _require(request, "job:read"):
            return denied
        job = Job.objects.prefetch_related("events").filter(id=job_id).first()
        if job is None:
            return _error(request, "NOT_FOUND", "Job not found.", 404)
        return Response(_job_detail(job))

    def post(self, request: Request, job_id: str) -> Response:
        action = str(request.data.get("action", ""))
        permission = "job:cancel" if action == "cancel" else "job:retry"
        if denied := _require(request, permission):
            return denied
        reason, invalid = _reason(request)
        if invalid:
            return invalid
        job = Job.objects.prefetch_related("events").filter(id=job_id).first()
        if job is None:
            return _error(request, "NOT_FOUND", "Job not found.", 404)
        if action == "cancel":
            if job.state not in {Job.State.QUEUED, Job.State.RUNNING}:
                return _error(request, "INVALID_STATE_TRANSITION", "Job cannot be cancelled.", 409)
            job = update_job(
                job.id,
                state=Job.State.CANCEL_REQUESTED,
                stage="cancel_requested",
                progress=job.progress,
            )
            audit_identity_event(
                "job.cancel_requested.v1",
                actor_id=_actor(request),
                target_refs=[f"job:{job.id}"],
                detail={"reason": reason},
            )
            return Response(_job_detail(Job.objects.prefetch_related("events").get(id=job.id)))
        if action != "retry" or job.state not in {
            Job.State.FAILED,
            Job.State.CANCELLED,
            Job.State.EXPIRED,
        }:
            return _error(request, "INVALID_STATE_TRANSITION", "Job cannot be retried.", 409)
        if job.capability_id in {"mold.similarity_search", "mold.design_review"}:
            record_type = (
                "similarity" if job.capability_id == "mold.similarity_search" else "design_review"
            )
            source_id = (
                str(job.similarity_search.id)
                if record_type == "similarity"
                else str(job.design_review.id)
            )
            _, _, new_job_id = _rerun_analysis(record_type, source_id)
            new_job = Job.objects.prefetch_related("events").get(id=new_job_id)
        elif job.capability_id in {"cad.parse", "knowledge.ingest"}:
            new_job = Job.objects.create(
                capability_id=job.capability_id,
                capability_version=job.capability_version,
                priority=job.priority,
                resource_class=job.resource_class,
                queue=job.queue,
                max_attempts=job.max_attempts,
                input_artifact_version=job.input_artifact_version,
                input_snapshot={**job.input_snapshot, "retry_of_job_id": str(job.id)},
            )
            JobEvent.objects.create(
                job=new_job,
                from_state="",
                to_state=Job.State.QUEUED,
                stage="queued",
                progress=0,
                detail={"retry_of_job_id": str(job.id)},
            )
            task = process_cad_job if job.capability_id == "cad.parse" else process_knowledge_job
            task.apply_async(args=[str(new_job.id)], queue=job.queue)
        else:
            return _error(request, "JOB_RETRY_UNSUPPORTED", "This job type cannot be retried.", 409)
        audit_identity_event(
            "job.retried.v1",
            actor_id=_actor(request),
            target_refs=[f"job:{job.id}", f"job:{new_job.id}"],
            detail={"reason": reason},
        )
        return Response(_job_detail(new_job), status=201)


def _redact(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: (
                "[REDACTED]"
                if any(
                    word in key.lower()
                    for word in ("token", "secret", "password", "api_key")
                )
                else _redact(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def _audit_payload(event: AuditEvent) -> dict[str, object]:
    return {
        "event_id": str(event.id),
        "event_type": event.event_type,
        "actor_id": event.actor_id,
        "target_refs": event.target_refs,
        "detail": _redact(event.detail),
        "payload_hash": event.payload_hash,
        "created_at": event.created_at.isoformat(),
    }


def _filtered_audit(request: Request):
    events = AuditEvent.objects.order_by("-created_at")
    if event_type := request.query_params.get("event_type"):
        events = events.filter(event_type__icontains=event_type)
    if actor := request.query_params.get("actor"):
        events = events.filter(actor_id__icontains=actor)
    if target := request.query_params.get("target"):
        events = events.filter(target_refs__contains=[target])
    if date_from := request.query_params.get("date_from"):
        events = events.filter(created_at__date__gte=date_from)
    if date_to := request.query_params.get("date_to"):
        events = events.filter(created_at__date__lte=date_to)
    return events


class AuditHistoryView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def get(self, request: Request) -> Response:
        if denied := _require(request, "audit:read"):
            return denied
        paging = _page(request)
        if isinstance(paging, Response):
            return paging
        page, size = paging
        events = _filtered_audit(request)
        total = events.count()
        start = (page - 1) * size
        return Response(
            {
                "schema_version": "1.0",
                "items": [_audit_payload(item) for item in events[start : start + size]],
                "page": {"number": page, "size": size, "total": total},
            }
        )


class AuditDetailView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def get(self, request: Request, event_id: str) -> Response:
        if denied := _require(request, "audit:read"):
            return denied
        event = AuditEvent.objects.filter(id=event_id).first()
        if event is None:
            return _error(request, "NOT_FOUND", "Audit event not found.", 404)
        return Response(_audit_payload(event))


class AuditExportView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def get(self, request: Request) -> HttpResponse:
        if denied := _require(request, "audit:export"):
            return denied
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="mold-ai-audit.csv"'
        writer = csv.writer(response)
        writer.writerow(
            (
                "event_id",
                "created_at",
                "event_type",
                "actor_id",
                "target_refs",
                "detail",
                "payload_hash",
            )
        )
        for event in _filtered_audit(request)[:10000]:
            payload = _audit_payload(event)
            writer.writerow(
                (
                    payload["event_id"],
                    payload["created_at"],
                    payload["event_type"],
                    payload["actor_id"],
                    json.dumps(payload["target_refs"], ensure_ascii=False),
                    json.dumps(payload["detail"], ensure_ascii=False),
                    payload["payload_hash"],
                )
            )
        audit_identity_event(
            "audit.exported.v1",
            actor_id=_actor(request),
            target_refs=["audit:export"],
            detail={"reason": "Authorized audit export", "filters": dict(request.query_params)},
        )
        return response


class LineageHistoryView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def get(self, request: Request) -> Response:
        if denied := _require(request, "lineage:read"):
            return denied
        root_type = str(request.query_params.get("root_type", "artifact_version"))
        root_id = str(request.query_params.get("root_id", ""))
        try:
            parsed_id = root_id if isinstance(root_id, uuid.UUID) else uuid.UUID(root_id)
        except ValueError:
            return _error(request, "VALIDATION_ROOT", "A valid root_id is required.", 400)
        nodes: dict[str, dict[str, object]] = {}
        edges: list[dict[str, object]] = []

        def node(node_type: str, node_id: object, label: str, status: str = "") -> str:
            key = f"{node_type}:{node_id}"
            nodes[key] = {
                "key": key,
                "type": node_type,
                "id": str(node_id),
                "label": label,
                "status": status,
            }
            return key

        if root_type == "artifact_version":
            version = (
                ArtifactVersion.objects.select_related("artifact").filter(id=parsed_id).first()
            )
            if version is None:
                return _error(request, "NOT_FOUND", "Artifact version not found.", 404)
            root = node(
                "artifact_version", version.id, version.original_filename, version.malware_status
            )
            lineage = LineageEdge.objects.select_related(
                "from_artifact_version", "to_artifact_version", "job"
            ).filter(from_artifact_version=version) | LineageEdge.objects.select_related(
                "from_artifact_version", "to_artifact_version", "job"
            ).filter(to_artifact_version=version)
            for edge in lineage:
                source = node(
                    "artifact_version",
                    edge.from_artifact_version_id,
                    edge.from_artifact_version.original_filename,
                )
                target = node(
                    "artifact_version",
                    edge.to_artifact_version_id,
                    edge.to_artifact_version.original_filename,
                )
                job_key = node("job", edge.job_id, edge.job.capability_id, edge.job.state)
                edges.append({"from": source, "to": target, "relation": edge.relationship})
                edges.append({"from": job_key, "to": target, "relation": "produced"})
        elif root_type == "job":
            job = Job.objects.select_related("input_artifact_version").filter(id=parsed_id).first()
            if job is None:
                return _error(request, "NOT_FOUND", "Job not found.", 404)
            root = node("job", job.id, job.capability_id, job.state)
            source = node(
                "artifact_version",
                job.input_artifact_version_id,
                job.input_artifact_version.original_filename,
            )
            edges.append({"from": source, "to": root, "relation": "input_to"})
            for edge in job.lineage_edges.select_related("to_artifact_version"):
                target = node(
                    "artifact_version",
                    edge.to_artifact_version_id,
                    edge.to_artifact_version.original_filename,
                )
                edges.append({"from": root, "to": target, "relation": "produced"})
        else:
            return _error(request, "VALIDATION_ROOT_TYPE", "Use artifact_version or job.", 400)
        return Response(
            {
                "schema_version": "history-lineage-v1",
                "root": {"type": root_type, "id": root_id, "key": root},
                "nodes": list(nodes.values()),
                "edges": edges,
            }
        )
