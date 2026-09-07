"""CPU-only mold-manufacturing descriptors and governed similarity profiles."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import trimesh
from django.conf import settings

from .models import CADModel, FeatureSet, SimilarityProfile

MANUFACTURING_EXTRACTOR_VERSION = "1.0.0"
MANUFACTURING_SAMPLE_COUNT = 128
MANUFACTURING_SEED = 20260907
MANUFACTURING_FACE_RAY_LIMIT = 256

PROFILE_DEFINITIONS: dict[str, dict[str, float]] = {
    "cpu-general@2.0": {
        "geometry": 0.25,
        "dimension": 0.20,
        "manufacturing": 0.25,
        "topology": 0.20,
        "metadata": 0.10,
    },
    "housing-standard@2.0": {
        "geometry": 0.22,
        "dimension": 0.16,
        "manufacturing": 0.36,
        "topology": 0.18,
        "metadata": 0.08,
    },
    "precision-connector@2.0": {
        "geometry": 0.24,
        "dimension": 0.30,
        "manufacturing": 0.20,
        "topology": 0.20,
        "metadata": 0.06,
    },
    "optical-lens@2.0": {
        "geometry": 0.30,
        "dimension": 0.18,
        "manufacturing": 0.32,
        "topology": 0.14,
        "metadata": 0.06,
    },
}


@dataclass(frozen=True)
class ProfileResolution:
    profile: SimilarityProfile
    resolution: dict[str, object]


def _ray_distances(
    mesh: trimesh.Trimesh,
    origins: np.ndarray,
    directions: np.ndarray,
    source_faces: np.ndarray,
) -> np.ndarray:
    """Brute-force Möller–Trumbore rays with bounded memory and no R-tree dependency."""

    triangles = np.asarray(mesh.triangles, dtype=float)
    v0 = triangles[:, 0]
    edge1 = triangles[:, 1] - v0
    edge2 = triangles[:, 2] - v0
    distances = np.full(len(origins), np.inf, dtype=float)
    epsilon = max(float(np.linalg.norm(mesh.extents)) * 1e-8, 1e-9)
    for index, (origin, direction, source_face) in enumerate(
        zip(origins, directions, source_faces, strict=True)
    ):
        pvec = np.cross(np.broadcast_to(direction, edge2.shape), edge2)
        determinant = np.einsum("ij,ij->i", edge1, pvec)
        usable = np.abs(determinant) > 1e-12
        inverse = np.zeros_like(determinant)
        inverse[usable] = 1.0 / determinant[usable]
        tvec = origin - v0
        u = np.einsum("ij,ij->i", tvec, pvec) * inverse
        qvec = np.cross(tvec, edge1)
        v = np.einsum("j,ij->i", direction, qvec) * inverse
        ray_t = np.einsum("ij,ij->i", edge2, qvec) * inverse
        hits = usable & (u >= 0.0) & (v >= 0.0) & ((u + v) <= 1.0) & (ray_t > epsilon)
        hits[int(source_face)] = False
        if np.any(hits):
            distances[index] = float(np.min(ray_t[hits]))
    return distances


def _draw_axis(mesh: trimesh.Trimesh) -> tuple[np.ndarray, str]:
    normals = np.asarray(mesh.face_normals, dtype=float)
    areas = np.asarray(mesh.area_faces, dtype=float)
    axes = np.eye(3)
    projected = [float(np.sum(np.abs(normals @ axis) * areas) / 2.0) for axis in axes]
    axis_index = int(np.argmax(projected))
    return axes[axis_index], ("X", "Y", "Z")[axis_index]


def _parting_features(mesh: trimesh.Trimesh, axis: np.ndarray) -> dict[str, object]:
    normals = np.asarray(mesh.face_normals, dtype=float)
    side = (normals @ axis) >= 0.0
    adjacency = np.asarray(mesh.face_adjacency, dtype=int)
    crossing = adjacency[side[adjacency[:, 0]] != side[adjacency[:, 1]]]
    if len(crossing) == 0:
        return {"classification": "NOT_AVAILABLE", "length": None, "height_ratio": None}
    shared_edges = np.asarray(mesh.face_adjacency_edges)[
        side[adjacency[:, 0]] != side[adjacency[:, 1]]
    ]
    vertices = np.asarray(mesh.vertices, dtype=float)
    edge_vectors = vertices[shared_edges[:, 1]] - vertices[shared_edges[:, 0]]
    length = float(np.linalg.norm(edge_vectors, axis=1).sum())
    edge_points = vertices[np.unique(shared_edges)]
    heights = edge_points @ axis
    draw_span = max(float(np.ptp(vertices @ axis)), 1e-12)
    height_ratio = float(np.ptp(heights) / draw_span)
    if height_ratio <= 0.02:
        classification = "FLAT_PLANE"
    elif height_ratio <= 0.15:
        classification = "STEPPED"
    else:
        classification = "3D_SURFACE"
    return {
        "classification": classification,
        "length": length,
        "height_ratio": height_ratio,
    }


def _component_count(mesh: trimesh.Trimesh, selected_faces: np.ndarray) -> int:
    selected = set(np.flatnonzero(selected_faces).tolist())
    if not selected:
        return 0
    adjacency: dict[int, set[int]] = {face: set() for face in selected}
    for first, second in np.asarray(mesh.face_adjacency, dtype=int):
        if int(first) in selected and int(second) in selected:
            adjacency[int(first)].add(int(second))
            adjacency[int(second)].add(int(first))
    count = 0
    while selected:
        count += 1
        stack = [selected.pop()]
        while stack:
            for neighbour in adjacency[stack.pop()]:
                if neighbour in selected:
                    selected.remove(neighbour)
                    stack.append(neighbour)
    return count


def extract_manufacturing_features(
    mesh: trimesh.Trimesh,
    *,
    source_format: str,
    allow_stl_approximation: bool = False,
    sample_count: int = MANUFACTURING_SAMPLE_COUNT,
    seed: int = MANUFACTURING_SEED,
) -> dict[str, object]:
    normalized_format = source_format.lower().lstrip(".")
    if normalized_format == "stl" and not allow_stl_approximation:
        return {
            "availability": "NOT_AVAILABLE",
            "precision": "NOT_AVAILABLE",
            "reason_code": "STL_HAS_NO_BREP_TOPOLOGY",
            "wall_thickness": None,
            "undercut": None,
            "parting": None,
            "manifest": {
                "extractor_version": MANUFACTURING_EXTRACTOR_VERSION,
                "source_format": normalized_format,
                "stl_approximation_enabled": False,
            },
        }
    if mesh.is_empty or len(mesh.faces) == 0:
        return {
            "availability": "NOT_AVAILABLE",
            "precision": "NOT_AVAILABLE",
            "reason_code": "EMPTY_PREVIEW_MESH",
            "wall_thickness": None,
            "undercut": None,
            "parting": None,
            "manifest": {"extractor_version": MANUFACTURING_EXTRACTOR_VERSION},
        }

    points, face_indices = trimesh.sample.sample_surface(mesh, sample_count, seed=seed)
    normals = np.asarray(mesh.face_normals[face_indices], dtype=float)
    epsilon = max(float(np.linalg.norm(mesh.extents)) * 1e-7, 1e-8)
    thickness = _ray_distances(
        mesh,
        np.asarray(points, dtype=float) - normals * epsilon,
        -normals,
        np.asarray(face_indices, dtype=int),
    )
    valid_thickness = thickness[np.isfinite(thickness) & (thickness > epsilon)]
    wall = None
    if len(valid_thickness):
        nominal = float(np.median(valid_thickness))
        wall = {
            "nominal": nominal,
            "max_ratio": float(valid_thickness.max() / max(valid_thickness.min(), epsilon)),
            "coefficient_of_variation": float(
                np.std(valid_thickness) / max(float(np.mean(valid_thickness)), epsilon)
            ),
            "sample_count": int(len(valid_thickness)),
        }

    if normalized_format == "stl":
        return {
            "availability": "APPROXIMATE" if wall else "NOT_AVAILABLE",
            "precision": "APPROXIMATE" if wall else "NOT_AVAILABLE",
            "reason_code": "STL_APPROXIMATE_THICKNESS_ONLY",
            "wall_thickness": wall,
            "undercut": None,
            "parting": None,
            "manifest": {
                "extractor_version": MANUFACTURING_EXTRACTOR_VERSION,
                "source_format": normalized_format,
                "sample_count": sample_count,
                "random_seed": seed,
                "stl_approximation_enabled": True,
            },
        }

    axis, axis_name = _draw_axis(mesh)
    vertices = np.asarray(mesh.vertices, dtype=float)
    all_face_centers = np.asarray(mesh.triangles_center, dtype=float)
    all_face_count = len(mesh.faces)
    if all_face_count > MANUFACTURING_FACE_RAY_LIMIT:
        face_ids = np.linspace(0, all_face_count - 1, MANUFACTURING_FACE_RAY_LIMIT, dtype=int)
    else:
        face_ids = np.arange(all_face_count, dtype=int)
    face_centers = all_face_centers[face_ids]
    positive = _ray_distances(
        mesh, face_centers + axis * epsilon, np.tile(axis, (len(face_ids), 1)), face_ids
    )
    negative = _ray_distances(
        mesh, face_centers - axis * epsilon, np.tile(-axis, (len(face_ids), 1)), face_ids
    )
    all_projected_area = np.abs(np.asarray(mesh.face_normals) @ axis) * np.asarray(mesh.area_faces)
    projected_area = all_projected_area[face_ids]
    projection_tolerance = max(float(np.asarray(mesh.area_faces).sum()) * 1e-10, 1e-12)
    trapped = (
        np.isfinite(positive) & np.isfinite(negative) & (projected_area > projection_tolerance)
    )
    sampled_projected_total = max(float(projected_area.sum()), 1e-12)
    projected_total = max(float(all_projected_area.sum() / 2.0), 1e-12)
    undercut_area = float(projected_area[trapped].sum() / sampled_projected_total)
    undercut_area *= float(all_projected_area.sum())
    slide_count = 1 if bool(np.any(trapped)) else 0
    parting = _parting_features(mesh, axis)
    return {
        "availability": "APPROXIMATE",
        "precision": "APPROXIMATE",
        "reason_code": "STEP_DERIVED_TESSELLATION",
        "wall_thickness": wall,
        "undercut": {
            "draw_axis": axis_name,
            "projected_area": undercut_area,
            "projected_area_ratio": min(undercut_area / projected_total, 1.0),
            "estimated_slide_count": slide_count,
        },
        "parting": parting,
        "manifest": {
            "extractor_version": MANUFACTURING_EXTRACTOR_VERSION,
            "source_format": normalized_format,
            "mesh_watertight": bool(mesh.is_watertight),
            "sample_count": sample_count,
            "face_ray_count": int(len(face_ids)),
            "face_ray_limit": MANUFACTURING_FACE_RAY_LIMIT,
            "face_sampling": "deterministic-even-index",
            "random_seed": seed,
            "draw_axis_policy": "maximum-projected-area",
            "vertices": int(len(vertices)),
        },
    }


def resolve_similarity_profile(cad_model: CADModel) -> ProfileResolution:
    product_type = cad_model.artifact_version.artifact.product_type.strip().lower()
    if "connector" in product_type:
        key, reason = "precision-connector@2.0", "PRODUCT_FAMILY_CONNECTOR"
    elif "lens" in product_type or "optical" in product_type:
        key, reason = "optical-lens@2.0", "PRODUCT_FAMILY_OPTICAL"
    elif any(token in product_type for token in ("housing", "cover", "tray")):
        key, reason = "housing-standard@2.0", "PRODUCT_FAMILY_HOUSING"
    else:
        key, reason = "cpu-general@2.0", "DEFAULT_FAMILY_PROFILE"
    profile, _ = SimilarityProfile.objects.get_or_create(
        profile_key=key,
        defaults={
            "schema_version": "2.0",
            "weights": PROFILE_DEFINITIONS[key],
            "candidate_collection": settings.QDRANT_CAD_COLLECTION_V2,
            "index_version": settings.SIMILARITY_INDEX_VERSION_V2,
            "status": "approved_demo",
        },
    )
    return ProfileResolution(
        profile=profile,
        resolution={
            "mode": "automatic",
            "product_type": product_type or None,
            "reason_code": reason,
            "selected_profile": key,
            "weights": profile.weights,
        },
    )


def _ratio(first: float | int | None, second: float | int | None) -> float | None:
    if first is None or second is None:
        return None
    first_value, second_value = abs(float(first)), abs(float(second))
    if first_value == 0 and second_value == 0:
        return 1.0
    if first_value <= 0 or second_value <= 0:
        return 0.0
    return math.exp(-abs(math.log(first_value / second_value)))


def manufacturing_similarity(
    first: FeatureSet, second: FeatureSet
) -> tuple[float | None, list[str]]:
    left = first.features.get("manufacturing", {})
    right = second.features.get("manufacturing", {})
    if left.get("availability") == "NOT_AVAILABLE" or right.get("availability") == "NOT_AVAILABLE":
        return None, ["Manufacturing lane excluded because one source has no comparable evidence."]
    scores: list[float] = []
    evidence: list[str] = []
    left_wall, right_wall = left.get("wall_thickness"), right.get("wall_thickness")
    if left_wall and right_wall:
        scores.extend(
            value
            for value in (
                _ratio(left_wall.get("nominal"), right_wall.get("nominal")),
                _ratio(left_wall.get("max_ratio"), right_wall.get("max_ratio")),
                _ratio(
                    left_wall.get("coefficient_of_variation"),
                    right_wall.get("coefficient_of_variation"),
                ),
            )
            if value is not None
        )
    left_undercut, right_undercut = left.get("undercut"), right.get("undercut")
    if left_undercut and right_undercut:
        scores.extend(
            value
            for value in (
                _ratio(
                    left_undercut.get("projected_area_ratio"),
                    right_undercut.get("projected_area_ratio"),
                ),
                _ratio(
                    left_undercut.get("estimated_slide_count"),
                    right_undercut.get("estimated_slide_count"),
                ),
            )
            if value is not None
        )
        if left_undercut.get("estimated_slide_count") == right_undercut.get(
            "estimated_slide_count"
        ):
            evidence.append(
                "Similar undercut count "
                f"({left_undercut.get('estimated_slide_count')} slides required)."
            )
    left_parting, right_parting = left.get("parting"), right.get("parting")
    if left_parting and right_parting:
        same_parting = left_parting.get("classification") == right_parting.get("classification")
        scores.append(1.0 if same_parting else 0.0)
        if same_parting and left_parting.get("classification") == "FLAT_PLANE":
            evidence.append("Parting line is planar on both parts.")
    return (sum(scores) / len(scores) if scores else None), evidence


def _average(values: list[float | None]) -> float | None:
    available = [value for value in values if value is not None]
    return sum(available) / len(available) if available else None


def _histogram_similarity(first: dict[str, int], second: dict[str, int]) -> float | None:
    first_total, second_total = sum(first.values()), sum(second.values())
    if first_total <= 0 or second_total <= 0:
        return None
    return sum(
        min(first.get(key, 0) / first_total, second.get(key, 0) / second_total)
        for key in set(first) | set(second)
    )


def compare_feature_sets_v2(
    query: FeatureSet, candidate: FeatureSet, profile: SimilarityProfile
) -> dict[str, object]:
    query_vector = np.asarray(query.vector, dtype=float)
    candidate_vector = np.asarray(candidate.vector, dtype=float)
    if query_vector.shape != candidate_vector.shape or query_vector.size != 32:
        raise ValueError("v2 comparison requires matching 32-dimensional descriptors")
    geometry_score = float(np.clip(np.dot(query_vector, candidate_vector), 0.0, 1.0))

    query_dimension = query.features.get("dimension", {})
    candidate_dimension = candidate.features.get("dimension", {})
    dimension_score = None
    query_unit = str(query_dimension.get("unit_system", "")).strip().lower()
    candidate_unit = str(candidate_dimension.get("unit_system", "")).strip().lower()
    if query_unit not in {"", "unknown"} and query_unit == candidate_unit:
        dimension_score = _average(
            [
                _ratio(first, second)
                for first, second in zip(
                    query_dimension.get("sorted", []),
                    candidate_dimension.get("sorted", []),
                    strict=True,
                )
            ]
        )

    query_topology = query.features.get("topology", {})
    candidate_topology = candidate.features.get("topology", {})
    query_format = query.cad_model.cad_format.strip().lower()
    candidate_format = candidate.cad_model.cad_format.strip().lower()
    topology_comparable = bool(query_format and query_format == candidate_format)
    topology_score = (
        _average(
            [
                _ratio(query_topology.get("face_count"), candidate_topology.get("face_count")),
                _ratio(query_topology.get("edge_count"), candidate_topology.get("edge_count")),
                _histogram_similarity(
                    query_topology.get("surface_type_histogram", {}),
                    candidate_topology.get("surface_type_histogram", {}),
                ),
            ]
        )
        if topology_comparable
        else None
    )
    query_metadata = query.features.get("metadata", {})
    candidate_metadata = candidate.features.get("metadata", {})
    metadata_values = [
        1.0 if query_metadata.get(key) == candidate_metadata.get(key) else 0.0
        for key in ("product_type", "material_code")
        if query_metadata.get(key) and candidate_metadata.get(key)
    ]
    metadata_score = _average(metadata_values)
    manufacturing_score, manufacturing_evidence = manufacturing_similarity(query, candidate)
    lane_scores = {
        "geometry": geometry_score,
        "dimension": dimension_score,
        "manufacturing": manufacturing_score,
        "topology": topology_score,
        "metadata": metadata_score,
    }
    available_weights = {
        lane: float(profile.weights.get(lane, 0.0))
        for lane, score in lane_scores.items()
        if score is not None and float(profile.weights.get(lane, 0.0)) > 0
    }
    weight_total = sum(available_weights.values())
    if weight_total <= 0:
        raise ValueError("similarity profile has no weight for available lanes")
    profile_weight_total = sum(max(float(weight), 0.0) for weight in profile.weights.values())
    available_lane_score = (
        sum(float(lane_scores[lane]) * weight for lane, weight in available_weights.items())
        / weight_total
    )
    evidence_coverage = weight_total / profile_weight_total if profile_weight_total > 0 else 0.0
    overall = available_lane_score * evidence_coverage

    similarities: list[dict[str, object]] = []
    differences: list[dict[str, object]] = []

    def evidence(lane: str, message: str) -> dict[str, object]:
        return {
            "type": lane,
            "message": message,
            "evidence_ref": f"feature-set:{candidate.id}:{lane}",
        }

    if geometry_score >= 0.85:
        similarities.append(
            evidence(
                "geometry",
                "The global shape descriptor is close; confirm it with topology and 3D "
                "deviation evidence.",
            )
        )
    else:
        differences.append(evidence("geometry", "The global shape descriptor differs materially."))

    if dimension_score is None:
        differences.append(
            evidence(
                "dimension",
                "Absolute dimensions were not compared because a unit is unknown or the unit "
                "systems differ.",
            )
        )
    elif dimension_score >= 0.85:
        similarities.append(evidence("dimension", "Overall dimensions are within a similar range."))
    else:
        differences.append(evidence("dimension", "Overall dimensions differ materially."))

    if topology_score is None:
        differences.append(
            evidence(
                "topology",
                "Topology was not compared because the CAD representations use different formats.",
            )
        )
    elif topology_score >= 0.85:
        similarities.append(
            evidence("topology", "Face, edge and surface-type distributions are similar.")
        )
    else:
        differences.append(
            evidence("topology", "Face, edge or surface-type distributions differ materially.")
        )

    if metadata_score is None:
        differences.append(
            evidence(
                "metadata",
                "Product type or material metadata is missing on one or both CAD records.",
            )
        )
    elif metadata_score >= 0.5:
        similarities.append(evidence("metadata", "Available product and material metadata match."))
    else:
        differences.append(evidence("metadata", "Available product or material metadata differs."))

    if manufacturing_score is None:
        differences.append(
            evidence(
                "manufacturing",
                "Manufacturing evidence is unavailable or not comparable for one of the CAD "
                "records.",
            )
        )
    elif manufacturing_score >= 0.85:
        similarities.append(
            evidence("manufacturing", "Available manufacturing evidence is similar.")
        )
    else:
        differences.append(evidence("manufacturing", "Manufacturing evidence differs materially."))
    if evidence_coverage < 0.6:
        differences.append(
            evidence(
                "evidence_coverage",
                "Evidence coverage is limited, so the overall score has been reduced.",
            )
        )
    return {
        "overall_score": round(overall, 6),
        "available_lane_score": round(available_lane_score, 6),
        "evidence_coverage": round(evidence_coverage, 6),
        "score_policy": "evidence-coverage-adjusted@1.0",
        "sub_scores": {
            lane: round(score, 6) if score is not None else None
            for lane, score in lane_scores.items()
        },
        "effective_weights": {
            lane: round(weight / weight_total, 6) for lane, weight in available_weights.items()
        },
        "feature_availability": {lane: score is not None for lane, score in lane_scores.items()},
        "similarities": similarities,
        "differences": differences,
        "manufacturing_evidence": manufacturing_evidence,
        "profile_resolution": {
            "profile_key": profile.profile_key,
            "schema_version": profile.schema_version,
            "original_weights": profile.weights,
        },
    }
