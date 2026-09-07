from copy import deepcopy
from types import SimpleNamespace

import pytest
import trimesh

from platform_core.cad_manufacturing import compare_feature_sets_v2
from platform_core.cad_shape_scoring import BLOCK_POLICY, compare_shape
from platform_core.cad_similarity_v2 import extract_shape_descriptor


def descriptor(mesh):
    return extract_shape_descriptor(mesh, sample_count=1024)


def compare(left, right, **kwargs):
    return compare_shape(left.features, right.features, left.vector, right.vector, **kwargs)


def test_rigid_transform_and_scale_preserve_shape_score():
    mesh = trimesh.creation.box(extents=[8, 3, 1])
    original = descriptor(mesh)
    mesh.apply_transform(trimesh.transformations.rotation_matrix(0.73, [1, 2, 3]))
    mesh.apply_scale(12)
    mesh.apply_translation([93, -31, 7])
    score = compare(original, descriptor(mesh))
    assert score["score"] == pytest.approx(1, abs=1e-6)
    assert score["policy"] == BLOCK_POLICY
    assert score["block_coverage"] == 1


@pytest.mark.parametrize(
    "mesh",
    [
        trimesh.creation.cylinder(radius=0.5, height=1),
        trimesh.creation.icosphere(subdivisions=2, radius=0.5),
        trimesh.creation.box(extents=[1, 1, 0.04]),
    ],
)
def test_obvious_shape_controls_do_not_inherit_high_global_cosine(mesh):
    result = compare(descriptor(trimesh.creation.box()), descriptor(mesh))
    assert result["coarse_cosine"] > 0.8  # Regression witness for the previous metric.
    assert result["score"] < 0.75
    assert result["block_scores"]


def test_remeshing_is_not_a_design_difference():
    mesh = trimesh.creation.box(extents=[8, 3, 1])
    result = compare(descriptor(mesh), descriptor(mesh.subdivide()))
    assert result["score"] > 0.9


def test_missing_and_invalid_blocks_are_explicit_not_perfect_evidence():
    original = descriptor(trimesh.creation.box())
    damaged = deepcopy(original.features)
    damaged["shape_invariants"]["solidity"] = None
    damaged["shape_invariants"]["normal_angle_histogram"] = [float("nan")] * 8
    result = compare_shape(original.features, damaged, original.vector, original.vector)
    assert "solidity" not in result["block_scores"]
    assert "normal_angle_histogram" not in result["block_scores"]
    assert result["block_coverage"] == 0.7
    fallback = compare_shape({}, {}, original.vector, original.vector)
    assert fallback["policy"] == "cosine-v2"
    assert fallback["fallback_reason"] == "STRUCTURED_BLOCKS_MISSING"


@pytest.mark.parametrize("vector", [[0] * 32, [float("nan")] * 32, [1] * 12])
def test_corrupt_vectors_fail_closed(vector):
    with pytest.raises(ValueError):
        compare_shape({}, {}, vector, vector)


def test_stl_counts_never_create_topology_evidence_and_step_aliases_compare():
    data = descriptor(trimesh.creation.box(extents=[8, 3, 1]))
    features = {
        **data.features,
        "dimension": {"unit_system": "unknown", "sorted": [8, 3, 1]},
        "topology": {"face_count": 12, "edge_count": 18, "surface_type_histogram": {"plane": 6}},
        "manufacturing": {"availability": "NOT_AVAILABLE"},
    }
    query = SimpleNamespace(
        id="q", features=features, vector=data.vector, cad_model=SimpleNamespace(cad_format="stl")
    )
    candidate = deepcopy(query)
    candidate.id = "c"
    profile = SimpleNamespace(
        weights={"geometry": 0.5, "topology": 0.5}, profile_key="test", schema_version="2.0"
    )
    result = compare_feature_sets_v2(query, candidate, profile)
    assert result["sub_scores"]["topology"] is None
    assert result["geometry_ranking"]["policy"] == BLOCK_POLICY
    assert result["evidence_coverage"] == 0.5
    assert result["geometry_validation_status"] == "not_evaluated_on_human_holdout"
    query.cad_model.cad_format = "step"
    candidate.cad_model.cad_format = "stp"
    assert compare_feature_sets_v2(query, candidate, profile)["sub_scores"]["topology"] == 1
