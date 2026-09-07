import copy
import json
from io import StringIO

import pytest
import trimesh
from django.core.management import call_command

from platform_core.cad_evaluation import (
    evaluate_corpus,
    file_checksum,
    ranking_metrics,
    validate_manifest,
)


@pytest.fixture
def corpus(tmp_path):
    models = []
    for index, extents in enumerate([(2, 3, 4), (1, 9, 1)]):
        path = tmp_path / f"{index}.stl"
        trimesh.creation.box(extents=extents).export(path)
        models.append(
            {
                "id": str(index),
                "path": path.name,
                "sha256": file_checksum(path),
                "source_url": "https://example.org/synthetic-control",
                "unit": "unknown",
                "family_id": str(index),
                "split": "holdout",
            }
        )
    return {
        "schema_version": "1.0",
        "corpus_id": "synthetic-test-only",
        "source": "test",
        "revision": "1",
        "license": "test-generated",
        "models": models,
        "queries": [
            {
                "id": "q1",
                "model_id": "0",
                "split": "holdout",
                "kind": "controlled_identity",
                "judgments": {"0": 3},
            }
        ],
    }


@pytest.mark.parametrize("path", ["../x.stl", "C:/x.stl", "/x.stl", "..\\x.stl"])
def test_paths_cannot_escape(corpus, tmp_path, path):
    corpus["models"][0]["path"] = path
    with pytest.raises(ValueError):
        validate_manifest(corpus, tmp_path)


def test_checksum_and_family_leakage(corpus, tmp_path):
    changed = copy.deepcopy(corpus)
    changed["models"][0]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="Checksum"):
        validate_manifest(changed, tmp_path)
    corpus["models"][1].update(family_id="0", split="development")
    with pytest.raises(ValueError, match="leakage"):
        validate_manifest(corpus, tmp_path)


def test_duplicate_ids_and_cross_split_judgments(corpus, tmp_path):
    changed = copy.deepcopy(corpus)
    changed["models"][1]["id"] = "0"
    with pytest.raises(ValueError, match="Duplicate"):
        validate_manifest(changed, tmp_path)
    corpus["models"][1]["split"] = "development"
    corpus["queries"][0]["judgments"]["1"] = 0
    with pytest.raises(ValueError, match="judgment"):
        validate_manifest(corpus, tmp_path)


def test_human_labels_and_no_match_require_explicit_evidence(corpus, tmp_path):
    query = corpus["queries"][0]
    query.update(kind="human_geometry", judgments={"1": 0}, expected_no_match=True)
    with pytest.raises(ValueError, match="reviewer"):
        validate_manifest(corpus, tmp_path)
    query.update(reviewer="engineer", reason="different geometry")
    validate_manifest(corpus, tmp_path)
    query["judgments"] = {"1": 3}
    with pytest.raises(ValueError, match="No-match"):
        validate_manifest(corpus, tmp_path)


def test_metrics_hand_calculated_and_unjudged_explicit():
    result = ranking_metrics(["unknown", "a", "b"], {"a": 3, "b": 1, "c": 0}, 2)
    assert result["recall_at_k"] == 0.5
    assert result["reciprocal_rank"] == 0.5
    assert result["judged_coverage_at_k"] == 0.5
    assert result["unjudged_at_k"] == ["unknown"]
    assert 0 < result["ndcg_at_k_provisional"] < 1
    assert ranking_metrics([], {"a": 3}, 5)["recall_at_k"] == 0
    assert ranking_metrics(["a"], {"a": 0}, 5)["recall_at_k"] is None


def test_offline_corpus_does_not_claim_human_validation(corpus, tmp_path):
    report = evaluate_corpus(corpus, tmp_path, sample_count=128, k=1)
    assert report["status"] == "evaluated"
    assert report["groups"]["controlled_identity"]["recall_at_k"] == 1
    assert report["groups"]["human_geometry"]["recall_at_k"] is None
    assert report["quality_gate"] == "not_evaluated"
    assert not report["human_holdout_available"]
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(corpus), encoding="utf-8")
    output = StringIO()
    call_command(
        "evaluate_public_cad", str(manifest), root=tmp_path, sample_count=128, stdout=output
    )
    assert json.loads(output.getvalue())["manifest_sha256"] == report["manifest_sha256"]


def test_parse_failure_is_not_silently_removed(corpus, tmp_path):
    path = tmp_path / "0.stl"
    path.write_text("not an stl", encoding="utf-8")
    corpus["models"][0]["sha256"] = file_checksum(path)
    report = evaluate_corpus(corpus, tmp_path, sample_count=128)
    assert report["status"] == "incomplete"
    assert report["failures"]
    assert report["groups"]["controlled_identity"]["evaluated_queries"] == 0


@pytest.mark.parametrize("threshold", [float("nan"), float("inf"), -1, 2])
def test_invalid_threshold(corpus, tmp_path, threshold):
    with pytest.raises(ValueError, match="Threshold"):
        evaluate_corpus(corpus, tmp_path, threshold=threshold)
