from __future__ import annotations

import hashlib
import json
import re

from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.authentication import SessionAuthentication
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .cae import cae_study_payload, cae_study_queryset
from .hmi import get_published_hmi_profile
from .identity import audit_identity_event
from .models import (
    CAEResult,
    CAERun,
    CAEStudy,
    CorrectiveAction,
    DefectObservation,
    HMIProfileVersion,
    MasterDataItem,
    MasterDataMappingBacklog,
    MoldRevision,
    ProcessParameter,
    ProcessRun,
    TrialCase,
    TrialCorrectionRecord,
)
from .process_trial import trial_case_payload, trial_case_queryset

CODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$")


def trial_case_summary(trial: TrialCase) -> dict[str, object]:
    return {
        "trial_case_id": str(trial.id),
        "case_code": trial.case_code,
        "mold_revision_ref": trial.mold_revision_ref,
        "machine_code": trial.machine_code,
        "material_code": trial.material_code,
        "product_type": trial.product_type,
        "outcome": trial.outcome,
        "started_at": trial.started_at.isoformat(),
        "lifecycle_status": trial.lifecycle_status,
        "row_version": trial.row_version,
        "run_count": len(trial.runs.all()),
        "correction_count": len(trial.corrections.all()),
    }


def cae_study_summary(study: CAEStudy) -> dict[str, object]:
    runs = list(study.runs.all())
    return {
        "study_id": str(study.id),
        "study_code": study.study_code,
        "solver_name": study.solver_name,
        "mold_revision_ref": study.mold_revision_ref,
        "material_model_code": study.material_model_code,
        "mesh_family": study.mesh_family,
        "objective": study.objective,
        "lifecycle_status": study.lifecycle_status,
        "row_version": study.row_version,
        "run_count": len(runs),
        "result_count": sum(len(run.results.all()) for run in runs),
    }


def _error(request: Request, code: str, message: str, http_status: int, **detail) -> Response:
    return Response(
        {
            "error": {
                "code": code,
                "message": message,
                "retryable": http_status >= 500,
                "request_id": getattr(request._request, "mold_ai_request_id", ""),
                **detail,
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


def _canonical(kind: str, code: object, *, required: bool = True) -> tuple[str, bool]:
    value = str(code or "").strip()
    if not value:
        return "", not required
    exists = MasterDataItem.objects.filter(kind=kind, code=value, status="active").exists()
    return value, exists


def _record_mapping_backlog(
    *, source_domain: str, source_record_ref: str, field_name: str, raw_value: str, target_kind: str
) -> None:
    item, created = MasterDataMappingBacklog.objects.get_or_create(
        source_domain=source_domain,
        field_name=field_name,
        raw_value=raw_value,
        target_kind=target_kind,
        defaults={"source_record_ref": source_record_ref},
    )
    if not created:
        item.occurrence_count += 1
        item.source_record_ref = source_record_ref
        item.save(update_fields=["occurrence_count", "source_record_ref", "last_seen_at"])


def _payload_hash(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


class GovernedTrialCaseListView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def get(self, request: Request) -> Response:
        trials = trial_case_queryset().order_by("case_code")[:100]
        serializer = (
            trial_case_summary
            if request.query_params.get("view") == "summary"
            else trial_case_payload
        )
        items = [serializer(item) for item in trials if "public-demo" in item.acl_scopes]
        return Response({"schema_version": "1.0", "items": items})

    def post(self, request: Request) -> Response:
        if denied := _require(request, "engineering-data:manage"):
            return denied
        reason, invalid = _reason(request)
        if invalid:
            return invalid
        case_code = str(request.data.get("case_code", "")).strip()
        if not CODE_RE.fullmatch(case_code):
            return _error(request, "VALIDATION_CASE_CODE", "A valid case_code is required.", 400)
        machine_code, machine_valid = _canonical("machine", request.data.get("machine_code"))
        material_code, material_valid = _canonical("material", request.data.get("material_code"))
        product_type, product_valid = _canonical("product_type", request.data.get("product_type"))
        if not all((machine_valid, material_valid, product_valid)):
            for field_name, value, kind, valid in (
                ("machine_code", machine_code, "machine", machine_valid),
                ("material_code", material_code, "material", material_valid),
                ("product_type", product_type, "product_type", product_valid),
            ):
                if not valid:
                    _record_mapping_backlog(
                        source_domain="trial",
                        source_record_ref=case_code,
                        field_name=field_name,
                        raw_value=value,
                        target_kind=kind,
                    )
            return _error(
                request,
                "MASTER_DATA_MAPPING_REQUIRED",
                "Machine, material and product type must use active canonical codes.",
                400,
            )
        revision = (
            MoldRevision.objects.select_related("mold")
            .filter(id=request.data.get("mold_revision_id"))
            .first()
        )
        if revision is None:
            return _error(request, "VALIDATION_MOLD_REVISION", "Mold revision is required.", 400)
        started_at = parse_datetime(str(request.data.get("started_at", "")))
        if started_at is None:
            return _error(request, "VALIDATION_STARTED_AT", "started_at must be ISO-8601.", 400)
        if timezone.is_naive(started_at):
            started_at = timezone.make_aware(started_at)
        source_record_id = f"manual:{case_code}"
        source_version = str(request.data.get("source_version", "1"))[:64]
        actor = _actor(request)
        try:
            trial = TrialCase.objects.create(
                case_code=case_code,
                connector_key="manual-platform-entry",
                source_record_id=source_record_id,
                source_version=source_version,
                source_hash=_payload_hash(request.data),
                mapping_version="canonical-master-data@1.0",
                classification="public_demo",
                acl_scopes=["public-demo"],
                mold_revision_ref=f"{revision.mold.mold_code}@{revision.revision_code}",
                part_revision_ref=str(request.data.get("part_revision_ref", ""))[:128],
                machine_code=machine_code,
                material_code=material_code,
                material_lot=str(request.data.get("material_lot", ""))[:64],
                product_type=product_type,
                operator_ref=actor,
                purpose=str(request.data.get("purpose", ""))[:255],
                outcome=str(request.data.get("outcome", "pending"))[:64],
                started_at=started_at,
                data_quality={"status": "draft", "source": "manual_platform_entry"},
                lifecycle_status=TrialCase.LifecycleStatus.DRAFT,
            )
        except IntegrityError:
            return _error(request, "TRIAL_CASE_CONFLICT", "Trial case code already exists.", 409)
        audit_identity_event(
            "trial_case.created.v1",
            actor_id=actor,
            target_refs=[f"trial-case:{trial.id}", f"mold-revision:{revision.id}"],
            detail={"reason": reason, "case_code": case_code},
        )
        return Response(trial_case_payload(trial_case_queryset().get(id=trial.id)), status=201)


class GovernedTrialCaseDetailView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def get(self, request: Request, trial_case_id: str) -> Response:
        trial = trial_case_queryset().filter(id=trial_case_id).first()
        if trial is None or "public-demo" not in trial.acl_scopes:
            return _error(request, "NOT_FOUND", "Trial case not found.", 404)
        return Response(trial_case_payload(trial))

    def patch(self, request: Request, trial_case_id: str) -> Response:
        if denied := _require(request, "engineering-data:manage"):
            return denied
        trial = TrialCase.objects.filter(id=trial_case_id).first()
        if trial is None:
            return _error(request, "NOT_FOUND", "Trial case not found.", 404)
        reason, invalid = _reason(request)
        if invalid:
            return invalid
        if int(request.data.get("row_version", 0)) != trial.row_version:
            return _error(request, "CONCURRENT_MODIFICATION", "Trial case changed.", 409)
        action = str(request.data.get("action", "update"))
        actor = _actor(request)
        if action == "correct":
            if trial.lifecycle_status != TrialCase.LifecycleStatus.CLOSED:
                return _error(
                    request,
                    "INVALID_STATE_TRANSITION",
                    "Only a closed trial accepts correction records.",
                    409,
                )
            changes = request.data.get("changes")
            if not isinstance(changes, dict) or not changes:
                return _error(request, "VALIDATION_CORRECTION", "changes must be an object.", 400)
            allowed = {"purpose", "outcome", "material_lot", "data_quality"}
            if set(changes) - allowed:
                return _error(
                    request, "VALIDATION_CORRECTION", "Correction contains unsupported fields.", 400
                )
            before = {field: getattr(trial, field) for field in changes}
            TrialCorrectionRecord.objects.create(
                trial=trial,
                before_values=before,
                after_values=changes,
                reason=reason,
                corrected_by=actor,
            )
        elif action == "close":
            if trial.lifecycle_status not in {
                TrialCase.LifecycleStatus.DRAFT,
                TrialCase.LifecycleStatus.REOPENED,
            }:
                return _error(request, "INVALID_STATE_TRANSITION", "Trial cannot close.", 409)
            trial.lifecycle_status = TrialCase.LifecycleStatus.CLOSED
            trial.closed_at = timezone.now()
        elif action == "reopen":
            if trial.lifecycle_status != TrialCase.LifecycleStatus.CLOSED:
                return _error(
                    request, "INVALID_STATE_TRANSITION", "Only closed trial can reopen.", 409
                )
            trial.lifecycle_status = TrialCase.LifecycleStatus.REOPENED
        elif action == "archive":
            trial.lifecycle_status = TrialCase.LifecycleStatus.ARCHIVED
            trial.archive_reason = reason
        elif action == "update":
            if trial.lifecycle_status not in {
                TrialCase.LifecycleStatus.DRAFT,
                TrialCase.LifecycleStatus.REOPENED,
            }:
                return _error(
                    request,
                    "TRIAL_IMMUTABLE_AFTER_CLOSE",
                    "Closed trial data requires a correction record.",
                    409,
                )
            for field in ("purpose", "outcome", "material_lot"):
                if field in request.data:
                    setattr(trial, field, str(request.data[field]).strip())
        else:
            return _error(request, "VALIDATION_ACTION", "Unsupported trial action.", 400)
        trial.row_version += 1
        trial.save()
        audit_identity_event(
            f"trial_case.{action}.v1",
            actor_id=actor,
            target_refs=[f"trial-case:{trial.id}"],
            detail={"reason": reason, "lifecycle_status": trial.lifecycle_status},
        )
        return Response(trial_case_payload(trial_case_queryset().get(id=trial.id)))


class GovernedProcessRunCreateView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def post(self, request: Request, trial_case_id: str) -> Response:
        if denied := _require(request, "engineering-data:manage"):
            return denied
        reason, invalid = _reason(request)
        if invalid:
            return invalid
        trial = TrialCase.objects.filter(id=trial_case_id).first()
        if trial is None:
            return _error(request, "NOT_FOUND", "Trial case not found.", 404)
        if trial.lifecycle_status not in {
            TrialCase.LifecycleStatus.DRAFT,
            TrialCase.LifecycleStatus.REOPENED,
        }:
            return _error(
                request,
                "TRIAL_IMMUTABLE_AFTER_CLOSE",
                "Process runs can only be appended to a draft or reopened trial.",
                409,
            )
        if int(request.data.get("row_version", 0)) != trial.row_version:
            return _error(request, "CONCURRENT_MODIFICATION", "Trial case changed.", 409)
        parameters = request.data.get("parameters", [])
        defects = request.data.get("defects", [])
        actions = request.data.get("corrective_actions", [])
        if not all(isinstance(items, list) for items in (parameters, defects, actions)):
            return _error(request, "VALIDATION_PROCESS_RUN", "Child records must be arrays.", 400)
        try:
            run_number = int(request.data.get("run_number"))
            if run_number < 1:
                raise ValueError("run_number must be positive.")
            with transaction.atomic():
                run = ProcessRun.objects.create(
                    trial=trial,
                    run_number=run_number,
                    cycle_start=request.data.get("cycle_start"),
                    cycle_end=request.data.get("cycle_end"),
                    environment=request.data.get("environment", {}),
                    result=str(request.data.get("result", "pending"))[:64],
                    data_quality={"source": "manual_platform_entry"},
                )
                for item in parameters:
                    ProcessParameter.objects.create(
                        process_run=run,
                        canonical_code=str(item["canonical_code"])[:64],
                        raw_name=str(item.get("raw_name", item["canonical_code"]))[:128],
                        value=float(item["value"]),
                        unit=str(item["unit"])[:32],
                        value_kind=str(item.get("value_kind", "setpoint")),
                        sampling_method=str(item.get("sampling_method", "manual"))[:64],
                    )
                for item in defects:
                    DefectObservation.objects.create(
                        process_run=run,
                        defect_code=str(item["defect_code"])[:64],
                        severity=str(item.get("severity", "observation"))[:32],
                        location=str(item.get("location", ""))[:128],
                        quantity_rate=item.get("quantity_rate"),
                        quantity_unit=str(item.get("quantity_unit", ""))[:32],
                        inspection_method=str(item.get("inspection_method", "manual"))[:128],
                        evidence_refs=item.get("evidence_refs", []),
                    )
                for item in actions:
                    CorrectiveAction.objects.create(
                        process_run=run,
                        action_code=str(item["action_code"])[:64],
                        description=str(item.get("description", "")),
                        before_values=item.get("before_values", {}),
                        after_values=item.get("after_values", {}),
                        rationale_source=item.get("rationale_source", {}),
                        approved_by=str(item.get("approved_by", ""))[:128],
                        executed=bool(item.get("executed", False)),
                        observed_outcome=item.get("observed_outcome", {}),
                        expected_effect=str(item.get("expected_effect", "")),
                        stop_condition=str(item.get("stop_condition", "")),
                        evidence_refs=item.get("evidence_refs", []),
                    )
                trial.row_version += 1
                trial.save(update_fields=["row_version", "updated_at"])
        except (IntegrityError, KeyError, TypeError, ValueError) as exc:
            return _error(request, "VALIDATION_PROCESS_RUN", str(exc), 400)
        audit_identity_event(
            "trial_case.process_run_appended.v1",
            actor_id=_actor(request),
            target_refs=[f"trial-case:{trial.id}", f"process-run:{run.id}"],
            detail={"reason": reason, "run_number": run.run_number},
        )
        return Response(trial_case_payload(trial_case_queryset().get(id=trial.id)), status=201)


class GovernedCAEStudyListView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def get(self, request: Request) -> Response:
        studies = cae_study_queryset().order_by("study_code")[:100]
        serializer = (
            cae_study_summary
            if request.query_params.get("view") == "summary"
            else cae_study_payload
        )
        return Response(
            {"schema_version": "1.0", "items": [serializer(item) for item in studies]}
        )

    def post(self, request: Request) -> Response:
        if denied := _require(request, "engineering-data:manage"):
            return denied
        reason, invalid = _reason(request)
        if invalid:
            return invalid
        study_code = str(request.data.get("study_code", "")).strip()
        if not CODE_RE.fullmatch(study_code):
            return _error(request, "VALIDATION_STUDY_CODE", "A valid study_code is required.", 400)
        required = ["solver_name", "mold_revision_ref", "material_model_code", "mesh_family"]
        if any(not str(request.data.get(field, "")).strip() for field in required):
            return _error(request, "VALIDATION_REQUIRED_FIELDS", "CAE metadata is incomplete.", 400)
        material_model_code, material_valid = _canonical(
            "material", request.data.get("material_model_code")
        )
        revision_ref = str(request.data.get("mold_revision_ref", "")).strip()
        try:
            mold_code, revision_code = revision_ref.rsplit("@", 1)
        except ValueError:
            mold_code, revision_code = "", ""
        revision_valid = MoldRevision.objects.filter(
            mold__mold_code=mold_code, revision_code=revision_code
        ).exists()
        if not material_valid:
            _record_mapping_backlog(
                source_domain="cae",
                source_record_ref=study_code,
                field_name="material_model_code",
                raw_value=material_model_code,
                target_kind="material",
            )
        if not material_valid or not revision_valid:
            return _error(
                request,
                "MASTER_DATA_MAPPING_REQUIRED",
                "CAE material and mold revision must reference governed records.",
                400,
            )
        actor = _actor(request)
        try:
            study = CAEStudy.objects.create(
                study_code=study_code,
                connector_key="manual-structured-import",
                integration_level="structured_metadata",
                source_record_id=f"manual:{study_code}",
                source_version=str(request.data.get("source_version", "1"))[:64],
                source_hash=_payload_hash(request.data),
                mapping_version="cae-manual@1.0",
                solver_name=str(request.data["solver_name"])[:128],
                product_ref=str(request.data.get("product_ref", ""))[:128],
                mold_revision_ref=revision_ref[:128],
                material_model_code=material_model_code[:128],
                mesh_family=str(request.data["mesh_family"])[:128],
                objective=str(request.data.get("objective", "")),
                owner=actor,
                classification="public_demo",
                acl_scopes=["public-demo"],
                data_quality={"status": "metadata_only"},
            )
        except IntegrityError:
            return _error(request, "CAE_STUDY_CONFLICT", "CAE study code already exists.", 409)
        audit_identity_event(
            "cae_study.created.v1",
            actor_id=actor,
            target_refs=[f"cae-study:{study.id}"],
            detail={"reason": reason, "study_code": study_code},
        )
        return Response(cae_study_payload(cae_study_queryset().get(id=study.id)), status=201)


class GovernedCAEStudyDetailView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def get(self, request: Request, study_id: str) -> Response:
        study = cae_study_queryset().filter(id=study_id).first()
        if study is None:
            return _error(request, "NOT_FOUND", "CAE study not found.", 404)
        return Response(cae_study_payload(study))

    def patch(self, request: Request, study_id: str) -> Response:
        if denied := _require(request, "engineering-data:manage"):
            return denied
        study = CAEStudy.objects.filter(id=study_id).first()
        if study is None:
            return _error(request, "NOT_FOUND", "CAE study not found.", 404)
        reason, invalid = _reason(request)
        if invalid:
            return invalid
        if int(request.data.get("row_version", 0)) != study.row_version:
            return _error(request, "CONCURRENT_MODIFICATION", "CAE study changed.", 409)
        action = str(request.data.get("action", ""))
        if action == "archive":
            study.lifecycle_status = "archived"
            study.archive_reason = reason
            study.archived_at = timezone.now()
        elif action == "restore":
            study.lifecycle_status = "active"
            study.archive_reason = ""
            study.archived_at = None
        else:
            return _error(request, "VALIDATION_ACTION", "Use archive or restore.", 400)
        study.row_version += 1
        study.save()
        audit_identity_event(
            f"cae_study.{action}.v1",
            actor_id=_actor(request),
            target_refs=[f"cae-study:{study.id}"],
            detail={"reason": reason},
        )
        return Response(cae_study_payload(cae_study_queryset().get(id=study.id)))


class GovernedCAERunCreateView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def post(self, request: Request, study_id: str) -> Response:
        if denied := _require(request, "engineering-data:manage"):
            return denied
        reason, invalid = _reason(request)
        if invalid:
            return invalid
        study = CAEStudy.objects.filter(id=study_id, lifecycle_status="active").first()
        if study is None:
            return _error(request, "NOT_FOUND", "Active CAE study not found.", 404)
        results = request.data.get("results", [])
        if not isinstance(results, list):
            return _error(request, "VALIDATION_RESULTS", "results must be an array.", 400)
        run_code = str(request.data.get("run_code", "")).strip()
        if not CODE_RE.fullmatch(run_code):
            return _error(request, "VALIDATION_RUN_CODE", "A valid run_code is required.", 400)
        status = str(request.data.get("status", CAERun.Status.SUCCEEDED))
        if status not in CAERun.Status.values:
            return _error(request, "VALIDATION_RUN_STATUS", "CAE run status is invalid.", 400)
        try:
            with transaction.atomic():
                run = CAERun.objects.create(
                    study=study,
                    run_code=run_code,
                    solver_name=str(request.data.get("solver_name", study.solver_name))[:128],
                    solver_version=str(request.data.get("solver_version", "unknown"))[:64],
                    mesh_artifact_ref=str(request.data.get("mesh_artifact_ref", "manual"))[:255],
                    mesh_checksum=str(request.data.get("mesh_checksum", ""))[:64],
                    material_model_code=str(
                        request.data.get("material_model_code", study.material_model_code)
                    )[:128],
                    boundary_settings=request.data.get("boundary_settings", {}),
                    process_settings=request.data.get("process_settings", {}),
                    unit_system=str(request.data.get("unit_system", "SI"))[:32],
                    status=status,
                    input_hash=_payload_hash(request.data),
                    data_quality={"source": "manual_structured_import"},
                )
                for item in results:
                    if not isinstance(item, dict):
                        raise ValueError("Each CAE result must be an object.")
                    result_type = str(item.get("result_type", CAEResult.ResultType.SCALAR))
                    if result_type not in CAEResult.ResultType.values:
                        raise ValueError("CAE result_type is invalid.")
                    CAEResult.objects.create(
                        run=run,
                        metric_code=str(item["metric_code"])[:128],
                        result_type=result_type,
                        value=float(item["value"]),
                        unit=str(item["unit"])[:32],
                        location=item.get("location", {}),
                        field_summary=item.get("field_summary", {}),
                        quality_flags=item.get("quality_flags", []),
                        parser_name="manual-structured-import",
                        parser_version="1.0",
                        source_locator=item.get("source_locator", {}),
                    )
        except (IntegrityError, KeyError, TypeError, ValueError) as exc:
            return _error(request, "VALIDATION_CAE_RUN", str(exc), 400)
        audit_identity_event(
            "cae_run.imported.v1",
            actor_id=_actor(request),
            target_refs=[f"cae-run:{run.id}", f"cae-study:{study.id}"],
            detail={"reason": reason, "result_count": len(results)},
        )
        return Response(cae_study_payload(cae_study_queryset().get(id=study.id)), status=201)


def hmi_profile_payload(profile: HMIProfileVersion) -> dict[str, object]:
    return {
        "profile_id": str(profile.id),
        "profile_key": profile.profile_key,
        "version": profile.version,
        "status": profile.status,
        "field_specs": profile.field_specs,
        "profile_checksum": profile.profile_checksum,
        "change_summary": profile.change_summary,
        "created_by": profile.created_by,
        "published_by": profile.published_by or None,
        "published_at": profile.published_at.isoformat() if profile.published_at else None,
        "row_version": profile.row_version,
        "updated_at": profile.updated_at.isoformat(),
        "extraction_count": profile.extractions.count(),
    }


class HMIProfileListCreateView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def get(self, request: Request) -> Response:
        get_published_hmi_profile()
        profiles = HMIProfileVersion.objects.prefetch_related("extractions")
        return Response(
            {"schema_version": "1.0", "items": [hmi_profile_payload(item) for item in profiles]}
        )

    def post(self, request: Request) -> Response:
        if denied := _require(request, "engineering-data:manage"):
            return denied
        reason, invalid = _reason(request)
        if invalid:
            return invalid
        source = HMIProfileVersion.objects.filter(id=request.data.get("source_profile_id")).first()
        if source is None:
            return _error(request, "NOT_FOUND", "Source HMI profile not found.", 404)
        version = str(request.data.get("version", "")).strip()
        if not CODE_RE.fullmatch(version):
            return _error(request, "VALIDATION_VERSION", "A valid version is required.", 400)
        try:
            profile = HMIProfileVersion.objects.create(
                profile_key=source.profile_key,
                version=version,
                status=HMIProfileVersion.Status.DRAFT,
                field_specs=source.field_specs,
                profile_checksum=source.profile_checksum,
                change_summary=str(request.data.get("change_summary", "")),
                created_by=_actor(request),
            )
        except IntegrityError:
            return _error(request, "HMI_PROFILE_CONFLICT", "HMI profile version exists.", 409)
        audit_identity_event(
            "hmi_profile.cloned.v1",
            actor_id=_actor(request),
            target_refs=[f"hmi-profile:{profile.id}"],
            detail={"reason": reason, "version": version},
        )
        return Response(hmi_profile_payload(profile), status=201)


class HMIProfileActionView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def post(self, request: Request, profile_id: str) -> Response:
        if denied := _require(request, "engineering-data:manage"):
            return denied
        profile = HMIProfileVersion.objects.filter(id=profile_id).first()
        if profile is None:
            return _error(request, "NOT_FOUND", "HMI profile not found.", 404)
        reason, invalid = _reason(request)
        if invalid:
            return invalid
        if int(request.data.get("row_version", 0)) != profile.row_version:
            return _error(request, "CONCURRENT_MODIFICATION", "HMI profile changed.", 409)
        action = str(request.data.get("action", ""))
        if action == "publish" and profile.status == HMIProfileVersion.Status.DRAFT:
            HMIProfileVersion.objects.filter(
                profile_key=profile.profile_key, status=HMIProfileVersion.Status.PUBLISHED
            ).update(status=HMIProfileVersion.Status.RETIRED)
            profile.status = HMIProfileVersion.Status.PUBLISHED
            profile.published_by = _actor(request)
            profile.published_at = timezone.now()
        elif action == "retire" and profile.status == HMIProfileVersion.Status.PUBLISHED:
            profile.status = HMIProfileVersion.Status.RETIRED
        else:
            return _error(request, "INVALID_STATE_TRANSITION", "HMI transition is invalid.", 409)
        profile.row_version += 1
        profile.save()
        audit_identity_event(
            f"hmi_profile.{action}.v1",
            actor_id=_actor(request),
            target_refs=[f"hmi-profile:{profile.id}"],
            detail={"reason": reason},
        )
        return Response(hmi_profile_payload(profile))


class HMIProfileDetailView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes: list = []

    def get(self, request: Request, profile_id: str) -> Response:
        profile = (
            HMIProfileVersion.objects.prefetch_related("extractions")
            .filter(id=profile_id)
            .first()
        )
        if profile is None:
            return _error(request, "NOT_FOUND", "HMI profile not found.", 404)
        return Response(hmi_profile_payload(profile))

    def patch(self, request: Request, profile_id: str) -> Response:
        if denied := _require(request, "engineering-data:manage"):
            return denied
        profile = HMIProfileVersion.objects.filter(id=profile_id).first()
        if profile is None:
            return _error(request, "NOT_FOUND", "HMI profile not found.", 404)
        reason, invalid = _reason(request)
        if invalid:
            return invalid
        if profile.status != HMIProfileVersion.Status.DRAFT:
            return _error(
                request,
                "PUBLISHED_CONTENT_IMMUTABLE",
                "Clone a published profile before editing.",
                409,
            )
        if int(request.data.get("row_version", 0)) != profile.row_version:
            return _error(request, "CONCURRENT_MODIFICATION", "HMI profile changed.", 409)
        field_specs = request.data.get("field_specs", profile.field_specs)
        if not isinstance(field_specs, list) or not all(
            isinstance(item, dict) for item in field_specs
        ):
            return _error(
                request,
                "VALIDATION_FIELD_SPECS",
                "field_specs must be an array of objects.",
                400,
            )
        profile.field_specs = field_specs
        if "change_summary" in request.data:
            profile.change_summary = str(request.data["change_summary"])
        profile.profile_checksum = hashlib.sha256(
            json.dumps(field_specs, sort_keys=True).encode()
        ).hexdigest()
        profile.row_version += 1
        profile.save()
        audit_identity_event(
            "hmi_profile.updated.v1",
            actor_id=_actor(request),
            target_refs=[f"hmi-profile:{profile.id}"],
            detail={"reason": reason, "field_count": len(field_specs)},
        )
        return Response(hmi_profile_payload(profile))
