import time

import numpy as np
import pytest
import trimesh

from platform_core.cad_surface_verification import (
    ALGORITHM,
    SurfaceVerificationError,
    sample_shape,
    surface_metrics,
    verify_meshes,
    verify_samples,
)


def test_same_shape_rigid_transform_and_scale_have_full_bidirectional_match():
    mesh = trimesh.creation.box(extents=[8, 3, 1])
    other = mesh.copy()
    other.apply_transform(trimesh.transformations.rotation_matrix(0.71, [1, 2, 3]))
    other.apply_scale(20)
    other.apply_translation([50, -8, 90])
    result = verify_meshes(mesh, other, sample_count=512)
    assert result["score_factor"] == pytest.approx(1, abs=1e-6)
    assert result["query_coverage"] == result["candidate_coverage"] == 1
    assert result["algorithm"] == ALGORITHM
    assert result["initial_orientation_count"] == 24
    assert np.linalg.det(np.array(result["normalized_transform"])[:3, :3]) == pytest.approx(1)
    assert result["calibration_status"] == "not_calibrated"


@pytest.mark.parametrize(
    "other",
    [trimesh.creation.cylinder(radius=0.5, height=1), trimesh.creation.box(extents=[1, 1, 0.04])],
)
def test_obvious_negative_controls_cannot_inherit_descriptor_high_scores(other):
    result = verify_meshes(trimesh.creation.box(), other, sample_count=512)
    assert result["score_factor"] < 0.5
    assert result["p95_distance"] > 0


def test_subset_matching_requires_both_directions_and_metrics_are_symmetric():
    rng = np.random.default_rng(41)
    small = rng.normal(size=(256, 3)) * 0.01
    full = np.concatenate((small, small + [2, 0, 0]))
    result = surface_metrics(full, small)
    reverse = surface_metrics(small, full)
    assert result["candidate_coverage"] == 1
    assert result["query_coverage"] == 0.5
    assert result["score_factor"] < 0.1
    assert result["score_factor"] == reverse["score_factor"]
    assert result["mean_distance"] == reverse["mean_distance"]


def test_remeshing_retains_substantial_surface_match_without_false_exactness():
    mesh = trimesh.creation.box(extents=[8, 3, 1])
    result = verify_meshes(mesh, mesh.subdivide())
    assert result["query_coverage"] > 0.9
    assert result["candidate_coverage"] > 0.9
    assert result["score_factor"] > 0.7
    assert result["mean_distance"] > 0  # Independent area samples are not identical points.


def test_deadline_and_input_limits_are_explicit():
    mesh = trimesh.creation.box()
    with pytest.raises(SurfaceVerificationError, match="BUDGET"):
        verify_meshes(mesh, mesh, deadline=time.monotonic() - 1)
    with pytest.raises(SurfaceVerificationError, match="SAMPLE_LIMIT"):
        sample_shape(mesh, sample_count=1_000_000)
    with pytest.raises(SurfaceVerificationError, match="INVALID_MESH"):
        sample_shape(trimesh.Trimesh())
    with pytest.raises(SurfaceVerificationError, match="INVALID_SAMPLES"):
        verify_samples(np.zeros((128, 3)), np.full((128, 3), np.nan))


def test_open_mesh_is_supported_without_claiming_signed_volume_evidence():
    mesh = trimesh.creation.box(extents=[3, 2, 1])
    mesh.update_faces(np.arange(8))
    result = verify_meshes(mesh, mesh, sample_count=256)
    assert result["score_factor"] == 1
    assert "signed" not in result
