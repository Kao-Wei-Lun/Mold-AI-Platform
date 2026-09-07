from copy import deepcopy

import pytest
from django.test import override_settings

from platform_core.cad_calibration import apply_calibration, load_calibration
from platform_core.cad_local_geometry import ALGORITHM
from platform_core.cad_review import fit_threshold, merge_reviews, review_template, validate_holdout
from platform_core.tests.test_cad_evaluation import corpus  # noqa: F401


def report(split, *, negative=0.1):
    rows = []
    for index in range(20):
        no_match = split == "holdout" and index < 3
        pairs = [
            {"model_id": "n1", "grade": 0, "surface_score_factor": negative},
            {"model_id": "n2", "grade": 0, "surface_score_factor": negative},
        ]
        if not no_match:
            pairs += [
                {"model_id": "p1", "grade": 3, "surface_score_factor": 0.9},
                {"model_id": "p2", "grade": 2, "surface_score_factor": 0.8},
            ]
        rows.append(
            {
                "query_id": str(index),
                "reviewer": "synthetic-unit-test-not-real-review",
                "kind": "human_geometry",
                "status": "evaluated",
                "expected_no_match": no_match,
                "pair_scores": pairs,
            }
        )
    return {
        "split": split,
        "status": "evaluated",
        "policy": ALGORITHM,
        "sample_count": 1536,
        "queries": rows,
        "failures": [],
        "model_provenance": [{"family_id": split, "sha256": split}],
    }


def test_blank_reviews_cannot_become_human_labels(corpus, tmp_path):  # noqa: F811
    template = review_template(corpus, tmp_path)
    assert template["queries"][0]["judgments"][0]["grade"] is None
    with pytest.raises(ValueError, match="No completed"):
        merge_reviews(corpus, template, tmp_path)
    row = template["queries"][0]
    row["judgments"][0].update(grade=3, reason="synthetic fixture explanation")
    with pytest.raises(ValueError, match="reviewer"):
        merge_reviews(corpus, template, tmp_path)
    row["reviewer"] = "test reviewer"
    merged = merge_reviews(corpus, template, tmp_path)
    assert merged["queries"][0]["kind"] == "human_geometry"
    assert len(merged["queries"]) == 1
    corrupted = deepcopy(template)
    corrupted["manifest_sha256"] = "changed"
    with pytest.raises(ValueError, match="manifest"):
        merge_reviews(corpus, corrupted, tmp_path)


def test_calibration_cannot_fit_on_holdout_or_unjudged_smoke():
    with pytest.raises(ValueError, match="complete"):
        fit_threshold(report("holdout"))
    data = report("development")
    data["queries"] = []
    with pytest.raises(ValueError, match="20 human"):
        fit_threshold(data)


def test_independent_holdout_and_frozen_threshold_are_required():
    development, holdout = report("development"), report("holdout")
    candidate = fit_threshold(development)
    release = validate_holdout(candidate, development, holdout, reviewer="test")
    assert release["status"] == "validated_holdout"
    assert release["activation"] == "operator_opt_in_required"
    candidate["threshold"] = 0.01
    with pytest.raises(ValueError, match="frozen"):
        validate_holdout(candidate, development, holdout, reviewer="test")
    holdout["model_provenance"] = development["model_provenance"]
    with pytest.raises(ValueError, match="leakage"):
        validate_holdout(fit_threshold(development), development, holdout, reviewer="test")


def test_bad_holdout_cannot_be_released_and_no_match_is_required():
    development = report("development")
    with pytest.raises(ValueError, match="gate failed"):
        validate_holdout(
            fit_threshold(development),
            development,
            report("holdout", negative=0.95),
            reviewer="test",
        )
    data = report("holdout")
    for row in data["queries"]:
        row["expected_no_match"] = False
    with pytest.raises(ValueError, match="no-match"):
        validate_holdout(fit_threshold(development), development, data, reviewer="test")


def test_absent_and_invalid_bundle_never_activate_threshold(tmp_path):
    with override_settings(SIMILARITY_CALIBRATION_BUNDLE=""):
        assert load_calibration()["status"] == "not_calibrated"
    with override_settings(SIMILARITY_CALIBRATION_BUNDLE=str(tmp_path / "missing.json")):
        assert load_calibration()["status"] == "invalid_calibration"


def test_unavailable_or_out_of_scope_candidates_prevent_no_match_claim():
    calibration = {
        "status": "validated_holdout",
        "algorithm": ALGORITHM,
        "mode": "normalized_shape",
        "dataset_ids": ["public"],
        "threshold": 0.8,
    }
    match = {
        "dataset_id": "public",
        "geometric_verification": {
            "algorithm": ALGORITHM,
            "mode": "normalized_shape",
            "status": "computed",
            "score_factor": 0.1,
        },
    }
    assert apply_calibration([match], calibration, "public")["decision"] == "no_reliable_match"
    assert apply_calibration([match], calibration, "company")["decision"] == "insufficient_evidence"
    match["geometric_verification"]["status"] = "unavailable"
    assert apply_calibration([match], calibration, "public")["decision"] == "insufficient_evidence"
