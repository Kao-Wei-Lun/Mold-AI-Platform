import numpy as np
import pytest
import trimesh

from platform_core.cad_brep_structure import compare_structure
from platform_core.cad_local_geometry import local_evidence, sample_payload, verify_payloads
from platform_core.cad_surface_verification import SurfaceVerificationError


def test_size_mode_preserves_size_and_converts_units_without_stretching():
    mesh = trimesh.creation.box(extents=[4, 2, 1])
    a = sample_payload(mesh, sample_count=512)
    scaled = mesh.copy()
    scaled.apply_scale(10)
    b = sample_payload(scaled, sample_count=512)
    assert verify_payloads(a, b)["score_factor"] == pytest.approx(1)
    different = verify_payloads(
        a, b, mode="engineering_size", query_unit="mm", candidate_unit="mm", tolerance_mm=0.1
    )
    assert different["score_factor"] < 0.1
    same = verify_payloads(a, b, mode="engineering_size", query_unit="cm", candidate_unit="mm")
    assert same["score_factor"] == pytest.approx(1)
    assert same["distance_unit"] == "mm"
    assert same["tolerance"] == pytest.approx(0.5)
    with pytest.raises(SurfaceVerificationError, match="KNOWN_UNITS"):
        verify_payloads(a, b, mode="engineering_size")


def test_local_displaced_region_has_lower_coverage_than_unchanged_regions():
    a = np.random.default_rng(25).uniform(-1, 1, (1536, 3))
    b = a.copy()
    b[(b[:, 0] > 0.5) & (b[:, 1] > 0.5)] += [0, 0, 1]
    result = local_evidence(a, b, 0.08)
    assert result["score_factor"] < 1
    assert result["levels"][1]["worst_patches"][0]["coverage"] < 0.5
    assert local_evidence(a, a, 0.08)["score_factor"] == 1


def test_multiscale_curve_is_monotonic_and_remesh_is_not_structural_change():
    mesh = trimesh.creation.box(extents=[4, 2, 1])
    result = verify_payloads(sample_payload(mesh), sample_payload(mesh.subdivide()))
    scores = [row["f_score"] for row in result["tolerance_curve"]]
    assert scores == sorted(scores)
    assert result["score_factor"] > 0.5
    assert compare_structure({}, {})["status"] == "unavailable"


def test_adjacency_is_not_inferred_from_mesh_triangle_counts():
    a = {
        "status": "available",
        "adjacency": {"plane|plane": 12},
        "surface_area_by_type": {"plane": 24},
    }
    b = {
        "status": "available",
        "adjacency": {"cylinder|plane": 4},
        "surface_area_by_type": {"cylinder": 24},
    }
    assert compare_structure(a, a)["agreement"] == 1
    assert compare_structure(a, b)["agreement"] == 0
    assert compare_structure(a, {"face_count": 10000})["status"] == "unavailable"
