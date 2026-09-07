from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import trimesh
from django.db import OperationalError
from django.utils import timezone

from platform_core import cad_surface_cache as cache
from platform_core import cad_surface_reranking as ranking
from platform_core.cad_local_geometry import ALGORITHM, sample_payload, verify_payloads
from platform_core.models import SurfaceVerificationCache

pytestmark = pytest.mark.django_db


@pytest.fixture
def evidence():
    points = sample_payload(trimesh.creation.box(extents=[4, 2, 1]))
    return verify_payloads(points, points)


def test_shared_cache_integrity_expiry_and_collision_bound(evidence, monkeypatch):
    monkeypatch.setattr(cache, "SLOTS", 1)
    first, second = cache.fingerprint("a"), cache.fingerprint("b")
    assert cache.write_shared(first, evidence)
    assert cache.read_shared(first) == evidence
    SurfaceVerificationCache.objects.update(payload={**evidence, "score_factor": 0.1})
    assert cache.read_shared(first) is None
    assert cache.write_shared(first, evidence)
    SurfaceVerificationCache.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
    assert cache.read_shared(first) is None
    assert cache.write_shared(second, evidence)
    assert SurfaceVerificationCache.objects.count() == 1
    assert cache.read_shared(first) is None
    assert cache.read_shared(second) == evidence


def test_cache_rejects_invalid_or_sensitive_payload_and_handles_db_outage(evidence):
    key = cache.fingerprint("test")
    for bad in (
        {**evidence, "score_factor": float("nan")},
        {**evidence, "download_url": "https://secret.example"},
        {**evidence, "status": "unavailable"},
        {**evidence, "sample_count": 128},
    ):
        assert not cache.write_shared(key, bad)
    with patch.object(SurfaceVerificationCache.objects, "filter", side_effect=OperationalError):
        assert cache.read_shared(key) is None
    assert SurfaceVerificationCache.objects.count() == 0


def test_public_operator_benchmark_requires_scope_and_reuses_db(tmp_path):
    import json

    from django.core.management import call_command

    from platform_core.models import FeatureSet, Job
    from platform_core.vector_store import VectorCandidate

    payload = sample_payload(trimesh.creation.box(extents=[4, 2, 1]))
    features = [
        SimpleNamespace(
            id=str(i),
            vector=[1.0] + [0.0] * 31,
            cad_model=SimpleNamespace(
                artifact_version_id=str(i), unit_system="mm", brep_structure={}, name=str(i)
            ),
        )
        for i in range(2)
    ]
    path = tmp_path / "benchmark.json"
    before = Job.objects.count()
    with (
        patch.object(FeatureSet.objects, "filter") as filtered,
        patch(
            "platform_core.management.commands.benchmark_cad_similarity.query_named_vectors",
            return_value=[VectorCandidate(str(i), 1.0) for i in range(2)],
        ),
        patch.object(
            ranking,
            "_load_samples",
            side_effect=lambda cad, deadline, **kwargs: (cad.name * 64, payload),
        ),
    ):
        ordered = filtered.return_value.select_related.return_value.order_by.return_value
        ordered.__getitem__.return_value = features
        call_command(
            "benchmark_cad_similarity",
            dataset="public-test",
            queries=2,
            repeats=2,
            top_k=2,
            output=path,
        )
        assert (
            filtered.call_args.kwargs["cad_model__artifact_version__artifact__classification"]
            == "public_demo"
        )
    report = json.loads(path.read_text())
    assert report["status"] == "complete"
    assert report["shared_cache_hits"] == 2
    assert Job.objects.count() == before


def test_shared_hit_survives_process_cache_clear_and_parameters_isolate_results():
    ranking._samples.clear()
    ranking._comparisons.clear()
    payload = sample_payload(trimesh.creation.box(extents=[4, 2, 1]))
    q = SimpleNamespace(cad_model=SimpleNamespace(unit_system="mm", brep_structure={}, name="q"))
    c = SimpleNamespace(cad_model=SimpleNamespace(unit_system="mm", brep_structure={}, name="c"))
    matches = [{"artifact_version_id": "c", "overall_score": 0.9}]

    def load(cad, deadline, **kwargs):
        return cad.name * 64, payload

    with patch.object(ranking, "_load_samples", side_effect=load):
        first = ranking.rerank_surfaces(deepcopy(matches), q, {"c": c}, policy=ALGORITHM)
        assert first[0]["geometric_verification"]["cache_source"] == "none"
        ranking._comparisons.clear()
        with patch.object(ranking, "verify_payloads", wraps=verify_payloads) as compute:
            second = ranking.rerank_surfaces(deepcopy(matches), q, {"c": c}, policy=ALGORITHM)
            compute.assert_not_called()
            assert second[0]["geometric_verification"]["cache_source"] == "shared"
            assert second[0]["overall_score"] == first[0]["overall_score"]
            ranking.rerank_surfaces(
                deepcopy(matches),
                q,
                {"c": c},
                policy=ALGORITHM,
                mode="engineering_size",
                tolerance_mm=0.25,
            )
            compute.assert_called_once()
        # No cache access can bypass even a missing/corrupt source.
        ranking._comparisons.clear()
        from platform_core.cad_surface_verification import SurfaceVerificationError

        with (
            patch.object(
                ranking,
                "_load_samples",
                side_effect=SurfaceVerificationError("SURFACE_PREVIEW_CHECKSUM_MISMATCH"),
            ),
            patch.object(ranking, "read_shared") as read,
        ):
            broken = ranking.rerank_surfaces(deepcopy(matches), q, {"c": c}, policy=ALGORITHM)
        read.assert_not_called()
        assert broken[0]["ranking_basis"] == "reference_only"
    ranking._samples.clear()
    ranking._comparisons.clear()
