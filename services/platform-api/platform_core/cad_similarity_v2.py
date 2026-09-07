"""Deterministic CPU-only shape descriptors for the CAD similarity v2 shadow index."""

from __future__ import annotations

import hashlib
import io
import json
import math
from dataclasses import dataclass

import numpy as np
import trimesh
from django.conf import settings
from django.core.files.storage import default_storage
from django.utils import timezone
from scipy.special import eval_jacobi, sph_harm_y

from .models import CADModel, FeatureSet
from .vector_store import upsert_named_vector

FEATURE_SCHEMA_VERSION = "2.0"
EXTRACTOR_NAME = "deterministic-cpu-shape-invariants"
EXTRACTOR_VERSION = "2.0.0"
VECTOR_DIMENSION = 32
SAMPLE_COUNT = 4096
RANDOM_SEED = 20260907
ZERNIKE_PAIRS = ((0, 0), (1, 1), (2, 0), (2, 2), (3, 1), (3, 3), (4, 0), (4, 2))


class CADSimilarityV2Error(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.user_message = message


@dataclass(frozen=True)
class DescriptorResult:
    vector: list[float]
    features: dict[str, object]


def _normalize(vector: np.ndarray) -> list[float]:
    magnitude = float(np.linalg.norm(vector))
    normalized = vector if magnitude <= 1e-15 else vector / magnitude
    return [round(float(value), 10) for value in normalized]


def _histogram(values: np.ndarray, bins: int = 8) -> np.ndarray:
    counts, _ = np.histogram(np.clip(values, 0.0, 1.0), bins=bins, range=(0.0, 1.0))
    total = int(counts.sum())
    return counts.astype(float) / total if total else np.zeros(bins, dtype=float)


def _principal_frame(points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    centered = points - points.mean(axis=0)
    covariance = np.cov(centered, rowvar=False, bias=True)
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    order = np.argsort(eigenvalues)[::-1]
    eigenvalues = np.maximum(eigenvalues[order], 0.0)
    frame = centered @ eigenvectors[:, order]
    return eigenvalues, frame


def _zernike_power(points: np.ndarray) -> np.ndarray:
    """Return low-order rotation-invariant 3D surface Zernike power coefficients.

    The radial basis uses the Jacobi-polynomial form of the 3D Zernike basis. Taking
    the L2 norm over every m component removes orientation while retaining the (n,l)
    frequency content. Surface samples are used so open meshes remain processable.
    """

    centered = points - points.mean(axis=0)
    radii = np.linalg.norm(centered, axis=1)
    scale = float(radii.max(initial=0.0))
    if scale <= 1e-15:
        return np.zeros(len(ZERNIKE_PAIRS), dtype=float)
    unit = centered / scale
    radii = np.linalg.norm(unit, axis=1)
    polar = np.arccos(np.clip(unit[:, 2] / np.maximum(radii, 1e-15), -1.0, 1.0))
    azimuth = np.mod(np.arctan2(unit[:, 1], unit[:, 0]), 2.0 * math.pi)
    coefficients: list[float] = []
    for n, degree in ZERNIKE_PAIRS:
        radial_order = (n - degree) // 2
        radial = np.power(radii, degree) * eval_jacobi(
            radial_order, 0.0, degree + 0.5, 2.0 * np.square(radii) - 1.0
        )
        components = []
        for order in range(-degree, degree + 1):
            harmonic = sph_harm_y(degree, order, polar, azimuth)
            components.append(np.mean(radial * np.conjugate(harmonic)))
        coefficients.append(float(np.sqrt(np.sum(np.abs(components) ** 2))))
    return np.asarray(coefficients, dtype=float)


def extract_shape_descriptor(
    mesh: trimesh.Trimesh,
    *,
    sample_count: int = SAMPLE_COUNT,
    seed: int = RANDOM_SEED,
) -> DescriptorResult:
    if mesh.is_empty or len(mesh.faces) == 0:
        raise CADSimilarityV2Error("CAD_DESCRIPTOR_EMPTY_MESH", "CAD preview has no mesh faces.")
    if sample_count < 128:
        raise ValueError("sample_count must be at least 128")

    points, face_indices = trimesh.sample.sample_surface(mesh, sample_count, seed=seed)
    points = np.asarray(points, dtype=float)
    eigenvalues, principal_points = _principal_frame(points)
    principal_extents = np.ptp(principal_points, axis=0)
    principal_extents = np.sort(principal_extents)[::-1]
    largest_extent = max(float(principal_extents[0]), 1e-15)
    extent_ratios = principal_extents / largest_extent
    inertia_total = max(float(eigenvalues.sum()), 1e-15)
    inertia_shares = eigenvalues / inertia_total

    hull = mesh.convex_hull
    hull_volume = abs(float(hull.volume))
    mesh_volume = abs(float(mesh.volume))
    solidity_available = bool(mesh.is_watertight and hull_volume > 1e-15)
    solidity = min(mesh_volume / hull_volume, 1.0) if solidity_available else 0.0
    mesh_area = float(mesh.area)
    convexity = min(float(hull.area) / mesh_area, 1.0) if mesh_area > 1e-15 else 0.0

    paired = np.roll(points, sample_count // 2, axis=0)
    distances = np.linalg.norm(points - paired, axis=1)
    d2 = _histogram(distances / max(float(distances.max(initial=0.0)), 1e-15))

    normals = np.asarray(mesh.face_normals[face_indices], dtype=float)
    paired_normals = np.roll(normals, sample_count // 2, axis=0)
    normal_cosines = np.abs(np.sum(normals * paired_normals, axis=1))
    normal_angle = _histogram(normal_cosines)
    zernike = _zernike_power(points)

    raw_vector = np.concatenate(
        (
            extent_ratios,
            inertia_shares,
            np.asarray([solidity, convexity]),
            d2,
            zernike,
            normal_angle,
        )
    )
    if len(raw_vector) != VECTOR_DIMENSION or not np.all(np.isfinite(raw_vector)):
        raise CADSimilarityV2Error(
            "CAD_DESCRIPTOR_INVALID", "CAD descriptor did not satisfy the 32-dimensional contract."
        )
    vector = _normalize(raw_vector)
    features: dict[str, object] = {
        "shape_invariants": {
            "principal_extent_ratios": extent_ratios.tolist(),
            "principal_inertia_shares": inertia_shares.tolist(),
            "solidity": solidity if solidity_available else None,
            "convexity": convexity,
            "d2_histogram": d2.tolist(),
            "zernike_power": zernike.tolist(),
            "normal_angle_histogram": normal_angle.tolist(),
        },
        "availability": {
            "solidity": "AVAILABLE" if solidity_available else "NOT_AVAILABLE",
            "surface_zernike": "AVAILABLE",
        },
        "missing_value_policy": {"solidity": 0.0},
        "extraction_manifest": {
            "algorithm": EXTRACTOR_NAME,
            "extractor_version": EXTRACTOR_VERSION,
            "schema_version": FEATURE_SCHEMA_VERSION,
            "sample_count": sample_count,
            "random_seed": seed,
            "sampling": "deterministic-area-weighted-surface",
            "orientation_policy": "principal-frame-and-rotation-invariant-power",
            "scale_policy": "unit-radius-and-ratio-normalized",
            "vector_dimension": VECTOR_DIMENSION,
        },
    }
    return DescriptorResult(vector=vector, features=features)


def _load_preview_mesh(cad_model: CADModel) -> trimesh.Trimesh:
    preview = cad_model.preview_artifact_version
    if preview is None or not default_storage.exists(preview.storage_key):
        raise CADSimilarityV2Error(
            "CAD_PREVIEW_NOT_AVAILABLE", "A governed STL preview is required for v2 extraction."
        )
    with default_storage.open(preview.storage_key, "rb") as source:
        loaded = trimesh.load(io.BytesIO(source.read()), file_type="stl", force="mesh")
    if isinstance(loaded, trimesh.Scene):
        loaded = loaded.to_geometry()
    if not isinstance(loaded, trimesh.Trimesh):
        raise CADSimilarityV2Error("CAD_PREVIEW_INVALID", "CAD preview is not a triangle mesh.")
    return loaded


def extract_feature_set_v2(cad_model: CADModel) -> FeatureSet:
    if cad_model.geometry_status != CADModel.GeometryStatus.SUCCEEDED:
        raise CADSimilarityV2Error(
            "SIMILARITY_GEOMETRY_NOT_READY", "CAD geometry must finish before feature extraction."
        )
    result = extract_shape_descriptor(_load_preview_mesh(cad_model))
    artifact = cad_model.artifact_version.artifact
    features = {
        **result.features,
        "metadata": {
            "dataset_id": artifact.dataset_id,
            "product_type": artifact.product_type,
            "material_code": artifact.material_code,
            "classification": artifact.classification,
        },
        "quality_flags": list(cad_model.quality_flags),
        "source": {
            "artifact_version_id": str(cad_model.artifact_version_id),
            "preview_artifact_version_id": str(cad_model.preview_artifact_version_id),
            "preview_sha256": cad_model.preview_artifact_version.sha256,
            "unit_system": cad_model.unit_system,
        },
    }
    vector_checksum = hashlib.sha256(
        json.dumps(result.vector, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    feature_set, created = FeatureSet.objects.get_or_create(
        cad_model=cad_model,
        feature_type="cad_similarity",
        schema_version=FEATURE_SCHEMA_VERSION,
        extractor_version=EXTRACTOR_VERSION,
        defaults={
            "extractor_name": EXTRACTOR_NAME,
            "features": features,
            "vector": result.vector,
            "vector_dimension": VECTOR_DIMENSION,
            "vector_checksum": vector_checksum,
            "index_collection": settings.QDRANT_CAD_COLLECTION_V2,
            "index_version": settings.SIMILARITY_INDEX_VERSION_V2,
        },
    )
    if not created and feature_set.vector_checksum != vector_checksum:
        raise CADSimilarityV2Error(
            "CAD_DESCRIPTOR_NONDETERMINISTIC",
            "The same extractor manifest produced a different vector checksum.",
        )
    return feature_set


def index_feature_set_v2(feature_set: FeatureSet) -> FeatureSet:
    artifact = feature_set.cad_model.artifact_version.artifact
    try:
        upsert_named_vector(
            collection_name=feature_set.index_collection,
            dimension=feature_set.vector_dimension,
            point_id=str(feature_set.id),
            vector=[float(value) for value in feature_set.vector],
            payload={
                "artifact_version_id": str(feature_set.cad_model.artifact_version_id),
                "classification": artifact.classification,
                "dataset_id": artifact.dataset_id,
                "product_type": artifact.product_type,
                "material_code": artifact.material_code,
                "index_version": feature_set.index_version,
                "feature_schema_version": feature_set.schema_version,
            },
        )
    except Exception as exc:
        feature_set.index_status = FeatureSet.IndexStatus.FAILED
        feature_set.index_error_code = getattr(exc, "code", "VECTOR_INDEX_FAILED")
        feature_set.indexed_at = None
        feature_set.save(update_fields=["index_status", "index_error_code", "indexed_at"])
        raise
    feature_set.index_status = FeatureSet.IndexStatus.INDEXED
    feature_set.index_error_code = ""
    feature_set.indexed_at = timezone.now()
    feature_set.save(update_fields=["index_status", "index_error_code", "indexed_at"])
    return feature_set


def extract_and_index_cad_model_v2(cad_model: CADModel) -> FeatureSet:
    return index_feature_set_v2(extract_feature_set_v2(cad_model))
