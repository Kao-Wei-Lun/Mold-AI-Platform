from __future__ import annotations

import uuid
from dataclasses import dataclass
from urllib.parse import urlencode, urlsplit, urlunsplit

DEEP_LINK_VERSION = "1.0"

TARGET_REFS: dict[str, tuple[frozenset[str], frozenset[str]]] = {
    "home": (frozenset(), frozenset()),
    "job": (frozenset({"job_id"}), frozenset()),
    "similarity": (frozenset({"search_id"}), frozenset({"candidate_id"})),
    "design_review": (frozenset({"review_id"}), frozenset({"finding_id"})),
    "knowledge": (frozenset({"knowledge_search_id"}), frozenset({"citation_id"})),
    "process_trial": (frozenset({"process_search_id"}), frozenset({"case_id"})),
    "cae": (frozenset({"cae_comparison_id"}), frozenset({"metric_code"})),
    "hmi": (frozenset({"hmi_extraction_id"}), frozenset()),
    "rule_profile": (frozenset({"profile_id"}), frozenset()),
    "mold_plan": (frozenset({"mold_plan_id"}), frozenset({"resolution_id"})),
    "ingestion_batch": (frozenset({"batch_id"}), frozenset()),
}

UUID_REFS = frozenset(
    {
        "job_id",
        "search_id",
        "candidate_id",
        "review_id",
        "finding_id",
        "knowledge_search_id",
        "citation_id",
        "process_search_id",
        "case_id",
        "cae_comparison_id",
        "hmi_extraction_id",
        "profile_id",
        "mold_plan_id",
        "resolution_id",
        "batch_id",
    }
)

FORBIDDEN_FIELDS = frozenset(
    {
        "token",
        "api_key",
        "tunnel_id",
        "workspace_url",
        "return_url",
        "javascript",
        "permission",
    }
)


class DeepLinkConfigurationError(ValueError):
    pass


class DeepLinkValidationError(ValueError):
    pass


def _canonical_uuid(value: str) -> str:
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError) as exc:
        raise DeepLinkValidationError("Deep-link identifiers must be canonical UUIDs.") from exc
    canonical = str(parsed)
    if canonical != value:
        raise DeepLinkValidationError("Deep-link identifiers must be canonical UUIDs.")
    return canonical


def normalize_entry_origin(value: str, *, allow_local: bool = False) -> str:
    candidate = value.strip()
    parsed = urlsplit(candidate)
    host = (parsed.hostname or "").lower()
    local_http = allow_local and parsed.scheme == "http" and host == "localhost"
    if parsed.scheme != "https" and not local_http:
        raise DeepLinkConfigurationError("The Web entry URL must use HTTPS.")
    if not host or (
        not local_http
        and (host == "localhost" or host.endswith(".localhost") or host.endswith(".invalid"))
    ):
        raise DeepLinkConfigurationError("The Web entry URL must use a deployable hostname.")
    if parsed.username or parsed.password:
        raise DeepLinkConfigurationError("The Web entry URL must not contain credentials.")
    if parsed.query or parsed.fragment:
        raise DeepLinkConfigurationError(
            "The Web entry URL must not contain query or fragment data."
        )
    if parsed.path not in {"", "/"}:
        raise DeepLinkConfigurationError("The Web entry URL must be an origin without a path.")
    return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


@dataclass(frozen=True)
class DeepLinkBuilder:
    entry_base_url: str
    allow_local: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "entry_base_url",
            normalize_entry_origin(self.entry_base_url, allow_local=self.allow_local),
        )

    def build(self, target: str, **refs: str | None) -> str:
        if target not in TARGET_REFS:
            raise DeepLinkValidationError("The deep-link target is not supported.")
        if FORBIDDEN_FIELDS.intersection(refs):
            raise DeepLinkValidationError("Sensitive fields are forbidden in deep links.")

        required, optional = TARGET_REFS[target]
        supplied = {key for key, value in refs.items() if value is not None}
        allowed = required | optional
        if not required.issubset(supplied) or not supplied.issubset(allowed):
            raise DeepLinkValidationError(
                "The deep-link references do not match the target schema."
            )

        params: list[tuple[str, str]] = [
            ("deep_link_version", DEEP_LINK_VERSION),
            ("target", target),
        ]
        for key in sorted(supplied):
            raw_value = str(refs[key])
            if key in UUID_REFS:
                raw_value = _canonical_uuid(raw_value)
            elif not raw_value or len(raw_value) > 128 or any(ord(char) < 32 for char in raw_value):
                raise DeepLinkValidationError("The deep-link reference is invalid.")
            params.append((key, raw_value))
        return f"{self.entry_base_url}/open?{urlencode(params)}"


def deep_link_readiness(value: str) -> dict[str, object]:
    try:
        origin = normalize_entry_origin(value)
    except DeepLinkConfigurationError as exc:
        return {
            "ready": False,
            "contract_version": DEEP_LINK_VERSION,
            "entry_origin": None,
            "error": str(exc),
        }
    return {
        "ready": True,
        "contract_version": DEEP_LINK_VERSION,
        "entry_origin": origin,
        "error": None,
    }
