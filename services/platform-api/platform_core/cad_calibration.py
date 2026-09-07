"""Opt-in, dataset-scoped decisions; absent or invalid human calibration fails closed."""

import json
from pathlib import Path

from django.conf import settings

from .cad_review import digest, fit_threshold, validate_holdout


def load_calibration() -> dict:
    location = getattr(settings, "SIMILARITY_CALIBRATION_BUNDLE", "")
    if not location:
        return {"status": "not_calibrated"}
    try:
        path = Path(location)
        if path.stat().st_size > 32 * 1024 * 1024:
            raise ValueError("Bundle too large")
        bundle = json.loads(path.read_text(encoding="utf-8"))
        release = bundle["release"]
        expected = validate_holdout(
            fit_threshold(bundle["development_report"]),
            bundle["development_report"],
            bundle["holdout_report"],
            reviewer=release["reviewer"],
        )
        datasets = bundle["dataset_ids"]
        if release != expected or not isinstance(datasets, list) or not datasets:
            raise ValueError("Invalid release or empty scope")
        if any(not isinstance(d, str) or not d or len(d) > 128 for d in datasets):
            raise ValueError("Invalid dataset scope")
        return {
            "status": "validated_holdout",
            "threshold": release["threshold"],
            "algorithm": release["algorithm"],
            "mode": release["mode"],
            "dataset_ids": datasets,
            "bundle_sha256": digest(bundle),
        }
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return {"status": "invalid_calibration"}


def apply_calibration(matches: list[dict], calibration: dict, query_dataset: str) -> dict:
    qualified, applicable = 0, 0
    for match in matches:
        evidence = match.get("geometric_verification", {})
        in_scope = (
            calibration.get("status") == "validated_holdout"
            and query_dataset in calibration.get("dataset_ids", [])
            and match["dataset_id"] in calibration.get("dataset_ids", [])
            and evidence.get("algorithm") == calibration.get("algorithm")
            and evidence.get("mode") == calibration.get("mode")
        )
        if in_scope and evidence.get("status") == "computed":
            applicable += 1
            accepted = evidence["score_factor"] >= calibration["threshold"]
            qualified += int(accepted)
            match["match_decision"] = "candidate" if accepted else "below_threshold"
        else:
            match["match_decision"] = "not_evaluated"
    return {
        "status": calibration.get("status", "not_calibrated"),
        "decision": (
            "no_reliable_match"
            if matches and applicable == len(matches) and not qualified
            else "candidates"
            if qualified
            else "insufficient_evidence"
        ),
        "scope": "returned_candidates_only",
        "qualified_count": qualified,
        "threshold": calibration.get("threshold"),
        "bundle_sha256": calibration.get("bundle_sha256"),
    }
