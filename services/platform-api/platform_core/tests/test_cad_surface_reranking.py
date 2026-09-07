import hashlib
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import trimesh

from platform_core import cad_surface_reranking as ranking
from platform_core.cad_surface_verification import SurfaceVerificationError, sample_shape


@pytest.fixture(autouse=True)
def clear_caches():
    ranking._samples.clear()
    ranking._comparisons.clear()
    yield
    ranking._samples.clear()
    ranking._comparisons.clear()


def match(name, score):
    return {"artifact_version_id": name, "overall_score": score, "differences": []}


def test_actual_surfaces_rerank_false_high_baseline_and_reuse_numeric_cache():
    query = sample_shape(trimesh.creation.box(extents=[4, 2, 1]))
    wrong = sample_shape(trimesh.creation.cylinder(radius=1, height=4))
    features = {name: SimpleNamespace(cad_model=name) for name in ("q", "right", "wrong")}
    data = {"q": ("qhash", query), "right": ("rhash", query), "wrong": ("whash", wrong)}
    original = [match("wrong", 0.99), match("right", 0.8)]
    with patch.object(ranking, "_load_samples", side_effect=lambda cad, _: data[cad]):
        result = ranking.rerank_surfaces(deepcopy(original), features["q"], features)
        assert [item["artifact_version_id"] for item in result] == ["right", "wrong"]
        assert result[1]["baseline_overall_score"] == 0.99
        assert result[1]["overall_score"] < 0.5
        assert result[1]["differences"][0]["type"] == "surface_verification"
        with patch.object(ranking, "verify_samples") as compute:
            repeated = ranking.rerank_surfaces(deepcopy(original), features["q"], features)
        compute.assert_not_called()
        assert repeated == result


def test_missing_preview_is_reference_only_and_cannot_displace_computed_candidate():
    points = sample_shape(trimesh.creation.box())
    features = {name: SimpleNamespace(cad_model=name) for name in ("q", "ok", "missing")}

    def loader(cad, _):
        if cad == "missing":
            raise SurfaceVerificationError("SURFACE_PREVIEW_MISSING")
        return cad, points

    with patch.object(ranking, "_load_samples", side_effect=loader):
        result = ranking.rerank_surfaces(
            [match("missing", 0.99), match("ok", 0.4)], features["q"], features
        )
    assert result[0]["artifact_version_id"] == "ok"
    assert result[1]["ranking_basis"] == "reference_only"
    assert result[1]["geometric_verification"]["status"] == "unavailable"
    assert "mean_distance" not in result[1]["geometric_verification"]


def test_budget_and_candidate_limit_do_not_invent_success():
    feature = SimpleNamespace(cad_model="q")
    with patch.object(ranking, "BUDGET_SECONDS", -1):
        result = ranking.rerank_surfaces([match("a", 0.9)], feature, {})
    assert result[0]["geometric_verification"]["status"] == "budget_exceeded"
    with patch.object(ranking, "MAX_CANDIDATES", 0), patch.object(ranking, "_load_samples") as load:
        result = ranking.rerank_surfaces([match("a", 0.9)], feature, {})
    load.assert_not_called()
    assert result[0]["geometric_verification"]["error_code"] == "SURFACE_CANDIDATE_LIMIT"


def test_preview_integrity_and_size_checked_before_cached_points_are_used():
    content = trimesh.creation.box().export(file_type="stl")
    checksum = hashlib.sha256(content).hexdigest()
    cad = SimpleNamespace(
        preview_artifact_version=SimpleNamespace(
            size_bytes=len(content), sha256=checksum, storage_key="controlled-preview"
        )
    )
    import io
    import time

    with patch.object(ranking.default_storage, "open", return_value=io.BytesIO(content)):
        ranking._load_samples(cad, time.monotonic() + 5)
    with patch.object(ranking.default_storage, "open", return_value=io.BytesIO(b"corrupt")):
        with pytest.raises(SurfaceVerificationError, match="CHECKSUM_MISMATCH"):
            ranking._load_samples(cad, time.monotonic() + 5)
    cad.preview_artifact_version.size_bytes = ranking.MAX_PREVIEW_BYTES + 1
    with patch.object(ranking.default_storage, "open") as load:
        with pytest.raises(SurfaceVerificationError, match="TOO_LARGE"):
            ranking._load_samples(cad, time.monotonic() + 5)
    load.assert_not_called()


def test_cache_is_bounded():
    for number in range(ranking.CACHE_ITEMS + 5):
        ranking._remember(ranking._comparisons, number, {"score_factor": 1})
    assert len(ranking._comparisons) == ranking.CACHE_ITEMS
    assert 0 not in ranking._comparisons
