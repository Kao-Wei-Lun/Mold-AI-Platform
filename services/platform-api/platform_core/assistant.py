from __future__ import annotations

import hashlib
import json
import uuid
from datetime import timedelta

from django.utils import timezone

from .assistant_providers import AssistantEvidenceEnvelope, get_assistant_provider
from .contracts import job_payload
from .models import (
    AuditEvent,
    CAEComparison,
    Job,
    KnowledgeDocument,
    KnowledgeSearch,
    MoldPlan,
    ProcessCaseSearch,
    ReviewFinding,
    ReviewRun,
    SimilaritySearch,
)

CONTEXT_VERSION = "1.0"
ACTION_PROTOCOL_VERSION = "1.0"
ALLOWED_PAGES = {
    "engineering_workspace",
    "cad_processing",
    "similarity_search",
    "mold_planning",
    "design_review",
    "knowledge_search",
    "process_trial",
    "cae",
}
ALLOWED_CONTEXT_FIELDS = {
    "context_version",
    "page",
    "query_artifact_version_id",
    "similarity_search_id",
    "selected_candidate_artifact_version_id",
    "job_id",
    "review_id",
    "finding_id",
    "knowledge_search_id",
    "process_search_id",
    "cae_comparison_id",
    "metric_code",
    "mold_plan_id",
    "mold_revision_id",
    "cad_artifact_version_id",
    "resolution_id",
    "selected_profile_id",
    "ui_locale",
}
UUID_CONTEXT_FIELDS = {
    "query_artifact_version_id",
    "similarity_search_id",
    "selected_candidate_artifact_version_id",
    "job_id",
    "review_id",
    "finding_id",
    "knowledge_search_id",
    "process_search_id",
    "cae_comparison_id",
    "mold_plan_id",
    "mold_revision_id",
    "cad_artifact_version_id",
    "resolution_id",
    "selected_profile_id",
}


class AssistantValidationError(Exception):
    def __init__(self, code: str, user_message: str) -> None:
        super().__init__(user_message)
        self.code = code
        self.user_message = user_message


def validate_context(raw_context: object) -> dict[str, str]:
    if raw_context is None:
        return {
            "context_version": CONTEXT_VERSION,
            "page": "engineering_workspace",
            "ui_locale": "zh-TW",
        }
    if not isinstance(raw_context, dict):
        raise AssistantValidationError("VALIDATION_ASSISTANT_CONTEXT", "context must be an object.")
    unknown = set(raw_context) - ALLOWED_CONTEXT_FIELDS
    if unknown:
        raise AssistantValidationError(
            "VALIDATION_ASSISTANT_CONTEXT",
            f"Unsupported context fields: {', '.join(sorted(unknown))}.",
        )
    version = str(raw_context.get("context_version", CONTEXT_VERSION))
    if version != CONTEXT_VERSION:
        raise AssistantValidationError(
            "VALIDATION_CONTEXT_VERSION", f"Unsupported context_version: {version}."
        )
    page = str(raw_context.get("page", "engineering_workspace"))
    if page not in ALLOWED_PAGES:
        raise AssistantValidationError("VALIDATION_ASSISTANT_PAGE", "Unsupported Assistant page.")

    context = {
        "context_version": CONTEXT_VERSION,
        "page": page,
        "ui_locale": str(raw_context.get("ui_locale", "zh-TW"))[:16],
    }
    for field in UUID_CONTEXT_FIELDS:
        value = raw_context.get(field)
        if value in {None, ""}:
            continue
        try:
            context[field] = str(uuid.UUID(str(value)))
        except (TypeError, ValueError) as exc:
            raise AssistantValidationError(
                "VALIDATION_ASSISTANT_CONTEXT", f"{field} must be a UUID."
            ) from exc
    metric_code = raw_context.get("metric_code")
    if metric_code not in {None, ""}:
        normalized_metric = str(metric_code)
        if len(normalized_metric) > 128 or not normalized_metric.replace("_", "").isalnum():
            raise AssistantValidationError(
                "VALIDATION_ASSISTANT_CONTEXT", "metric_code has an unsupported format."
            )
        context["metric_code"] = normalized_metric
    return context


def _show_evidence_action(search_id: str, candidate_version_id: str) -> dict[str, object]:
    return {
        "protocol_version": ACTION_PROTOCOL_VERSION,
        "action_id": str(uuid.uuid4()),
        "type": "assistant.show_evidence",
        "target": {
            "search_id": search_id,
            "candidate_artifact_version_id": candidate_version_id,
        },
        "parameters": {},
        "preconditions": [{"type": "page", "equals": "similarity_search"}],
        "requires_confirmation": False,
        "expires_at": (timezone.now() + timedelta(minutes=10)).isoformat(),
        "evidence_refs": [f"similarity-search:{search_id}"],
    }


def _similarity_answer(
    context: dict[str, str],
) -> tuple[dict[str, object], list[dict[str, object]], list[dict[str, object]]]:
    search_id = context.get("similarity_search_id")
    candidate_version_id = context.get("selected_candidate_artifact_version_id")
    if not search_id or not candidate_version_id:
        raise AssistantValidationError(
            "ASSISTANT_CONTEXT_INCOMPLETE",
            "Select a completed similarity candidate before asking for its ranking explanation.",
        )
    try:
        search = SimilaritySearch.objects.select_related("job").get(pk=search_id)
    except SimilaritySearch.DoesNotExist as exc:
        raise AssistantValidationError(
            "ASSISTANT_CONTEXT_NOT_FOUND", "The selected similarity search is not available."
        ) from exc
    if search.job.state != Job.State.SUCCEEDED:
        raise AssistantValidationError(
            "ASSISTANT_RESULT_NOT_READY", "The selected similarity search has not completed."
        )
    matches = search.result.get("results", [])
    match = next(
        (item for item in matches if item.get("artifact_version_id") == candidate_version_id),
        None,
    )
    if match is None:
        raise AssistantValidationError(
            "ASSISTANT_CONTEXT_NOT_FOUND", "The selected candidate is not in this search result."
        )

    lane_facts = []
    for lane, score in match.get("sub_scores", {}).items():
        if score is not None:
            lane_facts.append(f"{lane}: {float(score) * 100:.1f}%")
    similarities = [
        item.get("message", "") for item in match.get("similarities", []) if item.get("message")
    ]
    differences = [
        item.get("message", "") for item in match.get("differences", []) if item.get("message")
    ]
    evidence_refs = [
        item.get("evidence_ref")
        for item in [*match.get("similarities", []), *match.get("differences", [])]
        if item.get("evidence_ref")
    ]
    overall = float(match.get("overall_score", 0)) * 100
    answer = {
        "summary": (
            f"{match.get('artifact_name', 'The selected candidate')} is ranked "
            f"#{match.get('rank')} "
            f"with an overall similarity score of {overall:.1f}%."
        ),
        "facts": [
            f"Computed lane scores: {', '.join(lane_facts) or 'no comparable lanes'}.",
            *similarities,
        ],
        "interpretation": [
            "The deterministic ranking combines only available feature lanes and reweights "
            "missing lanes."
        ],
        "recommendations": [
            "Review the listed geometric differences before reusing this case as a design "
            "reference."
        ],
        "uncertainties": [*search.result.get("limitations", []), *differences],
        "evidence_refs": evidence_refs,
    }
    action = _show_evidence_action(search_id, candidate_version_id)
    tool_calls = [
        {
            "name": "get_similarity_explanation",
            "status": "succeeded",
            "arguments": {
                "search_id": search_id,
                "candidate_artifact_version_id": candidate_version_id,
            },
            "result_ref": f"similarity-search:{search_id}",
        }
    ]
    return answer, [action], tool_calls


def _job_answer(
    context: dict[str, str],
) -> tuple[dict[str, object], list[dict[str, object]], list[dict[str, object]]]:
    job_id = context.get("job_id")
    if not job_id:
        raise AssistantValidationError(
            "ASSISTANT_CONTEXT_INCOMPLETE", "Select a job before asking for its status."
        )
    try:
        job = Job.objects.select_related("input_artifact_version").get(pk=job_id)
    except Job.DoesNotExist as exc:
        raise AssistantValidationError(
            "ASSISTANT_CONTEXT_NOT_FOUND", "The job is not available."
        ) from exc
    payload = job_payload(job)
    answer = {
        "summary": f"The selected job is {job.state} at {job.progress}% ({job.stage}).",
        "facts": [f"Capability: {job.capability_id}@{job.capability_version}."],
        "interpretation": [],
        "recommendations": []
        if job.state == Job.State.SUCCEEDED
        else ["Keep the job panel open to monitor progress."],
        "uncertainties": [job.error_message] if job.error_message else [],
        "evidence_refs": [f"job:{job.id}"],
    }
    return (
        answer,
        [],
        [
            {
                "name": "get_job_status",
                "status": "succeeded",
                "arguments": {"job_id": job_id},
                "result_ref": payload["job_id"],
            }
        ],
    )


def _design_review_answer(
    context: dict[str, str],
) -> tuple[dict[str, object], list[dict[str, object]], list[dict[str, object]]]:
    review_id = context.get("review_id")
    if not review_id:
        raise AssistantValidationError(
            "ASSISTANT_CONTEXT_INCOMPLETE", "Select a completed design review first."
        )
    try:
        review = (
            ReviewRun.objects.select_related("cad_model__artifact_version")
            .prefetch_related("findings__rule_version")
            .get(pk=review_id)
        )
    except ReviewRun.DoesNotExist as exc:
        raise AssistantValidationError(
            "ASSISTANT_CONTEXT_NOT_FOUND", "The selected design review is not available."
        ) from exc
    if review.review_status != ReviewRun.Status.SUCCEEDED:
        raise AssistantValidationError(
            "ASSISTANT_RESULT_NOT_READY", "The selected design review has not completed."
        )
    if review.cad_model.artifact_version.classification != "public_demo":
        raise AssistantValidationError(
            "ASSISTANT_EVIDENCE_NOT_ALLOWED", "Only public Demo review evidence is supported."
        )
    findings = list(review.findings.all())
    finding_id = context.get("finding_id")
    if finding_id:
        findings = [finding for finding in findings if str(finding.id) == finding_id]
        if not findings:
            raise AssistantValidationError(
                "ASSISTANT_CONTEXT_NOT_FOUND", "The selected finding is not in this review."
            )
    counts: dict[str, int] = {}
    for finding in findings:
        counts[finding.result] = counts.get(finding.result, 0) + 1
    failed = [finding for finding in findings if finding.result == ReviewFinding.Result.FAIL]
    answer = {
        "summary": (
            f"Design review {review.id} completed with "
            + ", ".join(f"{key}={value}" for key, value in sorted(counts.items()))
            + "."
        ),
        "facts": [
            f"{finding.rule_version.title}: {finding.result}. {finding.message}"
            for finding in findings
        ],
        "interpretation": [
            "These results were produced by deterministic rules; the Assistant does not change "
            "PASS, FAIL, or NOT_EVALUATED decisions."
        ],
        "recommendations": list(
            dict.fromkeys(finding.rule_version.recommendation for finding in failed)
        ),
        "uncertainties": [
            f"{finding.rule_version.rule_id}: {', '.join(finding.quality_flags)}"
            for finding in findings
            if finding.quality_flags
        ],
        "evidence_refs": [
            f"design-review:{review.id}",
            *[ref for finding in findings for ref in finding.evidence_refs],
        ],
    }
    return (
        answer,
        [],
        [
            {
                "name": "get_design_review",
                "status": "succeeded",
                "arguments": {"review_id": review_id},
                "result_ref": f"design-review:{review.id}",
            }
        ],
    )


def _knowledge_answer(
    context: dict[str, str],
) -> tuple[dict[str, object], list[dict[str, object]], list[dict[str, object]]]:
    search_id = context.get("knowledge_search_id")
    if not search_id:
        raise AssistantValidationError(
            "ASSISTANT_CONTEXT_INCOMPLETE", "Select a completed knowledge search first."
        )
    try:
        search = KnowledgeSearch.objects.get(pk=search_id)
    except KnowledgeSearch.DoesNotExist as exc:
        raise AssistantValidationError(
            "ASSISTANT_CONTEXT_NOT_FOUND", "The selected knowledge search is not available."
        ) from exc
    citations = search.result.get("citations", [])
    document_ids = [item.get("document_id") for item in citations if item.get("document_id")]
    if document_ids:
        authorized_count = KnowledgeDocument.objects.filter(
            id__in=document_ids, classification="public_demo"
        ).count()
        if authorized_count != len(set(document_ids)):
            raise AssistantValidationError(
                "ASSISTANT_EVIDENCE_NOT_ALLOWED", "Only public Demo knowledge is supported."
            )
    claims = search.result.get("claims", [])
    answer = {
        "summary": search.result.get("answer", "No authorized knowledge evidence was found."),
        "facts": [item.get("text", "") for item in claims if item.get("text")],
        "interpretation": [],
        "recommendations": [],
        "uncertainties": list(search.result.get("limitations", [])),
        "evidence_refs": [item.get("citation_id") for item in citations if item.get("citation_id")],
    }
    return (
        answer,
        [],
        [
            {
                "name": "get_knowledge_search",
                "status": "succeeded",
                "arguments": {"knowledge_search_id": search_id},
                "result_ref": f"knowledge-search:{search.id}",
            }
        ],
    )


def _process_answer(
    context: dict[str, str],
) -> tuple[dict[str, object], list[dict[str, object]], list[dict[str, object]]]:
    search_id = context.get("process_search_id")
    if not search_id:
        raise AssistantValidationError(
            "ASSISTANT_CONTEXT_INCOMPLETE", "Select a completed process case search first."
        )
    try:
        search = ProcessCaseSearch.objects.get(pk=search_id)
    except ProcessCaseSearch.DoesNotExist as exc:
        raise AssistantValidationError(
            "ASSISTANT_CONTEXT_NOT_FOUND", "The selected process search is not available."
        ) from exc
    result = search.result
    if result.get("lineage", {}).get("source_type") != "synthetic":
        raise AssistantValidationError(
            "ASSISTANT_EVIDENCE_NOT_ALLOWED", "Only synthetic public Demo cases are supported."
        )
    cases = result.get("results", [])
    recommendation = result.get("recommendation", {})
    answer = {
        "summary": (
            recommendation.get("message")
            or f"Found {result.get('result_count', len(cases))} comparable process cases."
        ),
        "facts": [
            f"{item.get('case_code')}: score {float(item.get('score', 0)) * 100:.1f}%, "
            f"outcome {item.get('outcome')}."
            for item in cases[:5]
        ],
        "interpretation": [
            "Similarity and historical outcomes are associations, not proven root causes."
        ],
        "recommendations": [
            step.get("instruction", "")
            for step in recommendation.get("controlled_trial_steps", [])
            if step.get("instruction")
        ],
        "uncertainties": list(result.get("limitations", [])),
        "evidence_refs": [
            f"process-case-search:{search.id}",
            *[ref for item in cases for ref in item.get("evidence_refs", [])],
        ],
    }
    return (
        answer,
        [],
        [
            {
                "name": "get_process_case_search",
                "status": "succeeded",
                "arguments": {"process_search_id": search_id},
                "result_ref": f"process-case-search:{search.id}",
            }
        ],
    )


def _cae_answer(
    context: dict[str, str],
) -> tuple[dict[str, object], list[dict[str, object]], list[dict[str, object]]]:
    comparison_id = context.get("cae_comparison_id")
    if not comparison_id:
        raise AssistantValidationError(
            "ASSISTANT_CONTEXT_INCOMPLETE", "Select a CAE comparison first."
        )
    try:
        comparison = CAEComparison.objects.select_related(
            "baseline_run__study", "candidate_run__study"
        ).get(pk=comparison_id)
    except CAEComparison.DoesNotExist as exc:
        raise AssistantValidationError(
            "ASSISTANT_CONTEXT_NOT_FOUND", "The selected CAE comparison is not available."
        ) from exc
    if {
        comparison.baseline_run.study.classification,
        comparison.candidate_run.study.classification,
    } != {"public_demo"}:
        raise AssistantValidationError(
            "ASSISTANT_EVIDENCE_NOT_ALLOWED", "Only public Demo CAE evidence is supported."
        )
    result = comparison.result
    metrics = result.get("metric_comparisons", [])
    metric_code = context.get("metric_code")
    if metric_code:
        metrics = [item for item in metrics if item.get("metric_code") == metric_code]
        if not metrics:
            raise AssistantValidationError(
                "ASSISTANT_CONTEXT_NOT_FOUND", "The selected metric is not in this comparison."
            )
    summary = result.get("comparison_summary", {})
    answer = {
        "summary": (
            f"CAE comparison is {'compatible' if comparison.compatible else 'not compatible'}; "
            f"{summary.get('comparable_metric_count', 0)} metrics are comparable."
        ),
        "facts": [
            f"{item.get('metric_label', item.get('metric_code'))}: baseline "
            f"{item.get('baseline', {}).get('value')} {item.get('unit')}, candidate "
            f"{item.get('candidate', {}).get('value')} {item.get('unit')}, delta "
            f"{item.get('delta')} ({item.get('finding')})."
            for item in metrics
        ],
        "interpretation": [
            "Metric deltas are deterministic comparisons and do not establish causal effects."
        ],
        "recommendations": [],
        "uncertainties": [
            *result.get("limitations", []),
            *[str(item) for item in result.get("incompatibilities", [])],
        ],
        "evidence_refs": [
            f"cae-comparison:{comparison.id}",
            *[ref for item in metrics for ref in item.get("evidence_refs", [])],
        ],
    }
    return (
        answer,
        [],
        [
            {
                "name": "get_cae_comparison",
                "status": "succeeded",
                "arguments": {"cae_comparison_id": comparison_id},
                "result_ref": f"cae-comparison:{comparison.id}",
            }
        ],
    )


def _mold_plan_answer(
    context: dict[str, str],
) -> tuple[dict[str, object], list[dict[str, object]], list[dict[str, object]]]:
    plan_id = context.get("mold_plan_id")
    if not plan_id:
        raise AssistantValidationError(
            "ASSISTANT_CONTEXT_INCOMPLETE",
            "Open a saved mold plan before asking for its planning explanation.",
        )
    try:
        plan = (
            MoldPlan.objects.select_related("mold_revision", "cad_artifact_version")
            .prefetch_related(
                "resolutions__selected_profile",
                "resolutions__requirements__rule_version",
            )
            .get(id=plan_id, classification="public_demo")
        )
    except MoldPlan.DoesNotExist as exc:
        raise AssistantValidationError(
            "ASSISTANT_CONTEXT_NOT_FOUND", "The selected mold plan is not available."
        ) from exc
    resolution_id = context.get("resolution_id")
    resolution = next(
        (
            item
            for item in plan.resolutions.all()
            if not resolution_id or str(item.id) == resolution_id
        ),
        None,
    )
    if resolution is None:
        raise AssistantValidationError(
            "ASSISTANT_CONTEXT_NOT_FOUND",
            "The selected mold plan resolution is not available.",
        )
    requirements = list(resolution.requirements.all())
    insufficient = [item for item in requirements if item.planning_status == "insufficient_data"]
    manual = [item for item in requirements if item.planning_status == "manual_confirmation"]
    high_risk = [
        item
        for item in requirements
        if item.rule_version.severity in {"high", "critical"}
    ]
    answer = {
        "summary": (
            f"Mold plan {plan.plan_code} uses "
            f"{resolution.selected_profile.profile_key}@{resolution.selected_profile.version} "
            f"through {resolution.selection_mode} resolution."
        ),
        "facts": [
            resolution.reason,
            f"The immutable resolution contains {len(requirements)} requirements, "
            f"including {len(high_risk)} high-risk requirements.",
            f"Evidence gaps: {len(insufficient)} insufficient-data requirements and "
            f"{len(manual)} manual confirmations.",
        ],
        "interpretation": [
            "Mold planning selects governed requirements; it does not claim that design rules "
            "have passed."
        ],
        "recommendations": [
            *[
                f"Provide evidence for {item.rule_version.rule_id}: "
                f"{item.rule_version.recommendation}"
                for item in insufficient[:5]
            ],
            *[
                f"Confirm {item.rule_version.rule_id} manually before completion."
                for item in manual[:5]
            ],
        ],
        "uncertainties": [
            "The Assistant explains only the persisted resolution and requirement snapshots."
        ],
        "evidence_refs": [
            f"mold-plan:{plan.id}",
            f"mold-plan-resolution:{resolution.id}",
            f"rule-profile:{resolution.selected_profile_id}",
        ],
    }
    return (
        answer,
        [],
        [
            {
                "name": "explain_mold_plan_rule_selection",
                "status": "succeeded",
                "arguments": {
                    "mold_plan_id": str(plan.id),
                    "resolution_id": str(resolution.id),
                },
                "result_ref": f"mold-plan-resolution:{resolution.id}",
            }
        ],
    )


def _evidence_envelope(
    intent: str,
    context: dict[str, str],
    answer: dict[str, object],
    tool_calls: list[dict[str, object]],
) -> AssistantEvidenceEnvelope | None:
    if not tool_calls:
        return None
    record_ref = str(tool_calls[0]["result_ref"])
    content = json.dumps(answer, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    fact_values = [answer.get("summary", ""), *answer.get("facts", [])]
    return AssistantEvidenceEnvelope(
        schema_version="1.0",
        intent=intent,
        locale=context.get("ui_locale", "zh-TW"),
        context_refs={key: value for key, value in context.items() if key.endswith("_id")},
        facts=tuple(
            {
                "fact_id": f"fact:{intent}:{index}",
                "type": "computed_result",
                "value": value,
                "evidence_refs": [record_ref],
            }
            for index, value in enumerate(fact_values)
            if value
        ),
        evidence=(
            {
                "evidence_ref": record_ref,
                "evidence_type": "persisted_domain_result",
                "classification": "public_demo",
                "content": content,
            },
        ),
        required_limitations=tuple(str(item) for item in answer.get("uncertainties", [])),
    )


def create_assistant_response(message: str, raw_context: object) -> dict[str, object]:
    normalized = message.strip()
    if not normalized:
        raise AssistantValidationError("VALIDATION_ASSISTANT_MESSAGE", "message is required.")
    if len(normalized) > 2000:
        raise AssistantValidationError(
            "VALIDATION_ASSISTANT_MESSAGE", "message must be 2000 characters or fewer."
        )
    context = validate_context(raw_context)
    lowered = normalized.casefold()
    job_terms = ("job", "status", "progress", "工作", "狀態", "進度")
    intent = "unsupported"

    if context.get("mold_plan_id"):
        intent = "explain_mold_plan"
        answer, ui_actions, tool_calls = _mold_plan_answer(context)
    elif context.get("review_id"):
        intent = "explain_design_review"
        answer, ui_actions, tool_calls = _design_review_answer(context)
    elif context.get("knowledge_search_id"):
        intent = "summarize_knowledge"
        answer, ui_actions, tool_calls = _knowledge_answer(context)
    elif context.get("process_search_id"):
        intent = "summarize_process_cases"
        answer, ui_actions, tool_calls = _process_answer(context)
    elif context.get("cae_comparison_id"):
        intent = "explain_cae_comparison"
        answer, ui_actions, tool_calls = _cae_answer(context)
    elif context.get("similarity_search_id"):
        intent = "explain_similarity"
        answer, ui_actions, tool_calls = _similarity_answer(context)
    elif any(term in lowered for term in job_terms) and context.get("job_id"):
        intent = "get_job_status"
        answer, ui_actions, tool_calls = _job_answer(context)
    else:
        answer = {
            "summary": (
                "Select a persisted Similarity, Design Review, Knowledge, Process/Trial, CAE, "
                "or Job result before asking the engineering Assistant to explain it."
            ),
            "facts": [
                "Only the visible UI references in the context envelope are resolved server-side."
            ],
            "interpretation": [],
            "recommendations": [
                "Open a completed result in the workspace and ask a question about that result."
            ],
            "uncertainties": [
                "Free-form planning and arbitrary tool execution are outside the Demo scope."
            ],
            "evidence_refs": [],
        }
        ui_actions = []
        tool_calls = []

    provider = get_assistant_provider()
    envelope = _evidence_envelope(intent, context, answer, tool_calls)
    if envelope is None:
        provider_payload = provider.health().payload()
        provider_payload.update(
            {
                "mode": "deterministic_fallback",
                "llm_available": False,
                "status": "degraded",
                "reason": "UNSUPPORTED_OR_UNGROUNDED_INTENT",
            }
        )
    else:
        try:
            generated = provider.generate(envelope)
        except Exception:  # Provider failures must never turn the Assistant endpoint into a 500.
            generated = None
        if generated is None:
            provider_payload = provider.health().payload()
            provider_payload.update(
                {
                    "mode": "deterministic_fallback",
                    "llm_available": False,
                    "status": "degraded",
                    "reason": "PROVIDER_INTERNAL_ERROR",
                }
            )
        else:
            provider_payload = generated.provider_payload()
            if generated.answer is not None:
                answer = generated.answer

    serialized = json.dumps({"message": normalized, "context": context}, sort_keys=True)
    target_refs = [f"{key}:{value}" for key, value in context.items() if key.endswith("_id")]
    AuditEvent.objects.create(
        event_type="assistant.message_processed.v1",
        actor_id="demo-web-user",
        target_refs=target_refs,
        detail={
            "provider": provider_payload,
            "tool_names": [call["name"] for call in tool_calls],
            "context_version": CONTEXT_VERSION,
            "intent": intent,
            "evidence_count": len(envelope.evidence) if envelope else 0,
            "evidence_hash": (
                hashlib.sha256(json.dumps(envelope.payload(), sort_keys=True).encode()).hexdigest()
                if envelope
                else None
            ),
        },
        payload_hash=hashlib.sha256(serialized.encode()).hexdigest(),
    )
    return {
        "schema_version": "1.0",
        "assistant_message_id": str(uuid.uuid4()),
        "context": context,
        "provider": provider_payload,
        "answer": answer,
        "tool_calls": tool_calls,
        "ui_actions": ui_actions,
    }
