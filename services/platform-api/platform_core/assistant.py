from __future__ import annotations

import hashlib
import json
import uuid
from datetime import timedelta

from django.utils import timezone

from .assistant_providers import get_assistant_provider
from .contracts import job_payload
from .models import AuditEvent, Job, SimilaritySearch

CONTEXT_VERSION = "1.0"
ACTION_PROTOCOL_VERSION = "1.0"
ALLOWED_PAGES = {
    "engineering_workspace",
    "cad_processing",
    "similarity_search",
    "design_review",
    "knowledge_search",
}
ALLOWED_CONTEXT_FIELDS = {
    "context_version",
    "page",
    "query_artifact_version_id",
    "similarity_search_id",
    "selected_candidate_artifact_version_id",
    "job_id",
    "ui_locale",
}
UUID_CONTEXT_FIELDS = {
    "query_artifact_version_id",
    "similarity_search_id",
    "selected_candidate_artifact_version_id",
    "job_id",
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
    explain_terms = ("why", "explain", "rank", "為什麼", "排名", "第一")
    job_terms = ("job", "status", "progress", "工作", "狀態", "進度")

    if any(term in lowered for term in explain_terms):
        answer, ui_actions, tool_calls = _similarity_answer(context)
    elif any(term in lowered for term in job_terms) and context.get("job_id"):
        answer, ui_actions, tool_calls = _job_answer(context)
    else:
        answer = {
            "summary": (
                "The deterministic demo Assistant can explain the selected similarity result "
                "or report the selected job status."
            ),
            "facts": [
                "Only the visible UI references in the context envelope are resolved server-side."
            ],
            "interpretation": [],
            "recommendations": [
                "Select a similarity candidate, then ask why it ranked at its current position."
            ],
            "uncertainties": [
                "Natural-language planning is unavailable while the LLM provider is disabled."
            ],
            "evidence_refs": [],
        }
        ui_actions = []
        tool_calls = []

    serialized = json.dumps({"message": normalized, "context": context}, sort_keys=True)
    target_refs = [f"{key}:{value}" for key, value in context.items() if key.endswith("_id")]
    AuditEvent.objects.create(
        event_type="assistant.message_processed.v1",
        actor_id="demo-web-user",
        target_refs=target_refs,
        detail={
            "provider": get_assistant_provider().health().payload(),
            "tool_names": [call["name"] for call in tool_calls],
            "context_version": CONTEXT_VERSION,
        },
        payload_hash=hashlib.sha256(serialized.encode()).hexdigest(),
    )
    return {
        "schema_version": "1.0",
        "assistant_message_id": str(uuid.uuid4()),
        "context": context,
        "provider": get_assistant_provider().health().payload(),
        "answer": answer,
        "tool_calls": tool_calls,
        "ui_actions": ui_actions,
    }
