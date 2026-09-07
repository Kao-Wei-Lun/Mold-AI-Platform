"""Offline human judgments and fail-closed threshold release; never fabricate relevance."""

import hashlib
import json
import math
from copy import deepcopy

from .cad_evaluation import validate_manifest
from .cad_local_geometry import ALGORITHM


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def review_template(manifest: dict, root, *, count=25) -> dict:
    validate_manifest(manifest, root)
    if not 1 <= count <= 50:
        raise ValueError("Review count must be 1..50")
    models = manifest["models"]
    return {
        "schema_version": "1.0",
        "manifest_sha256": digest(manifest),
        "instructions": (
            "0 unrelated; 1 weak; 2 similar; 3 highly similar; null means unjudged. "
            "Fill reviewer and per-pair reason. Never infer labels from scores."
        ),
        "queries": [
            {
                "model_id": model["id"],
                "reviewer": "",
                "judgments": [
                    {"candidate_id": other["id"], "grade": None, "reason": ""}
                    for other in models
                    if other["id"] != model["id"] and other["split"] == model["split"]
                ],
            }
            for model in models[:count]
        ],
    }


def merge_reviews(manifest: dict, review: dict, root) -> dict:
    validate_manifest(manifest, root)
    if review.get("manifest_sha256") != digest(manifest):
        raise ValueError("Review source manifest changed")
    result = deepcopy(manifest)
    by_id = {m["id"]: m for m in result["models"]}
    queries = []
    seen = set()
    for row in review.get("queries", []):
        identifier = row.get("model_id")
        if identifier not in by_id or identifier in seen:
            raise ValueError("Invalid or duplicate reviewed query")
        seen.add(identifier)
        judgments, reasons = {}, []
        eligible = {
            m["id"] for m in result["models"] if m["split"] == by_id[identifier]["split"]
        } - {identifier}
        entries = set()
        for item in row.get("judgments", []):
            candidate = item.get("candidate_id")
            if candidate not in eligible or candidate in entries:
                raise ValueError("Invalid or duplicate reviewed candidate")
            entries.add(candidate)
            grade = item.get("grade")
            if grade is None:
                continue
            if (
                type(grade) is not int
                or grade not in range(4)
                or not str(item.get("reason", "")).strip()
            ):
                raise ValueError("Each judgment needs integer grade 0..3 and reason")
            judgments[candidate] = grade
            reasons.append(f"{candidate}: {item['reason']}")
        if not judgments:
            continue
        if not str(row.get("reviewer", "")).strip():
            raise ValueError("Human reviewer is required")
        no_match = set(judgments) == eligible and not any(judgments.values())
        if not any(judgments.values()) and not no_match:
            raise ValueError(
                "Partial all-negative query cannot establish no-match; judge remaining pairs"
            )
        queries.append(
            {
                "id": "human-" + identifier,
                "model_id": identifier,
                "split": by_id[identifier]["split"],
                "kind": "human_geometry",
                "reviewer": row["reviewer"],
                "reason": "\n".join(reasons),
                "judgments": judgments,
                "expected_no_match": no_match,
            }
        )
    if not queries:
        raise ValueError("No completed human judgments; templates cannot calibrate scores")
    result["queries"] = queries
    result["review_sha256"] = digest(review)
    validate_manifest(result, root)
    return result


def _human_pairs(report: dict, split: str, minimum_queries: int):
    if (
        report.get("split") != split
        or report.get("status") != "evaluated"
        or report.get("policy") != ALGORITHM
        or report.get("sample_count") != 1536
        or report.get("failures")
    ):
        raise ValueError("Calibration requires complete current-policy reports with 1536 samples")
    rows = [
        r
        for r in report.get("queries", [])
        if r.get("kind") == "human_geometry" and r.get("status") == "evaluated"
    ]
    if len(rows) < minimum_queries:
        raise ValueError(f"At least {minimum_queries} human queries are required for {split}")
    if len({row.get("query_id") for row in rows}) != len(rows) or any(
        not row.get("reviewer") for row in rows
    ):
        raise ValueError("Unique human queries and reviewer provenance required")
    positive, negative = [], []
    for row in rows:
        for pair in row.get("pair_scores", []):
            score, grade = pair.get("surface_score_factor"), pair.get("grade")
            if score is None or not math.isfinite(score) or not 0 <= score <= 1:
                raise ValueError("Invalid pair score")
            if type(grade) is int and grade in (2, 3):
                positive.append(score)
            elif type(grade) is int and grade == 0:
                negative.append(score)
            # Weak and unjudged pairs are NOT negative examples.
    if len(positive) < 30 or len(negative) < 30:
        raise ValueError("At least 30 positive and 30 negative judged pairs are required")
    return positive, negative


def fit_threshold(report: dict) -> dict:
    positive, negative = _human_pairs(report, "development", 20)
    choices = sorted(set([0.0, 1.0] + positive + [math.nextafter(s, 1.0) for s in negative]))
    candidates = []
    for threshold in choices:
        false_acceptance = sum(s >= threshold for s in negative) / len(negative)
        recall = sum(s >= threshold for s in positive) / len(positive)
        if false_acceptance <= 0.05:
            candidates.append((recall, -false_acceptance, threshold))
    if not candidates:
        raise ValueError("No development threshold meets false-acceptance target")
    recall, negative_fpr, threshold = max(candidates)
    return {
        "schema_version": "1.0",
        "algorithm": ALGORITHM,
        "mode": "normalized_shape",
        "metric": "surface_score_factor",
        "sample_count": 1536,
        "threshold": threshold,
        "status": "candidate_requires_holdout",
        "development_report_sha256": digest(report),
        "development_provenance": report["model_provenance"],
        "development_recall": recall,
        "development_false_acceptance": -negative_fpr,
    }


def validate_holdout(candidate: dict, development: dict, holdout: dict, *, reviewer: str) -> dict:
    # Refit development: changing the threshold to match holdout cannot silently pass.
    if candidate != fit_threshold(development):
        raise ValueError("Candidate differs from frozen development fit")
    if not reviewer.strip():
        raise ValueError("Release reviewer is required")
    positive, negative = _human_pairs(holdout, "holdout", 10)
    for field in ("family_id", "sha256"):
        train = {m[field] for m in development["model_provenance"]}
        test = {m[field] for m in holdout["model_provenance"]}
        if not train or not test or train & test:
            raise ValueError("Development/holdout family or content leakage")
    threshold = candidate["threshold"]
    recall = sum(s >= threshold for s in positive) / len(positive)
    fpr = sum(s >= threshold for s in negative) / len(negative)
    if recall < 0.8 or fpr > 0.05:
        raise ValueError("Holdout gate failed; do not tune on this holdout")
    no_matches = [
        r
        for r in holdout["queries"]
        if r.get("expected_no_match") and r.get("kind") == "human_geometry"
    ]
    if len(no_matches) < 3 or any(
        not r["pair_scores"] or any(p.get("grade") != 0 for p in r["pair_scores"])
        for r in no_matches
    ):
        raise ValueError("At least three fully judged no-match holdout queries required")
    no_match_fpr = sum(
        any(p["surface_score_factor"] >= threshold for p in r["pair_scores"]) for r in no_matches
    ) / len(no_matches)
    if no_match_fpr > 0.05:
        raise ValueError("No-match holdout gate failed")
    return {
        **candidate,
        "status": "validated_holdout",
        "reviewer": reviewer,
        "holdout_report_sha256": digest(holdout),
        "holdout_recall": recall,
        "holdout_false_acceptance": fpr,
        "holdout_no_match_false_acceptance": no_match_fpr,
        "activation": "operator_opt_in_required",
    }
