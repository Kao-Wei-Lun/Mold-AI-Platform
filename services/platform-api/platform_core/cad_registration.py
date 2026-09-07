"""Bounded CPU PCA/ICP registration, deviation cloud and ROI comparison."""

from __future__ import annotations

import hashlib
import io
import itertools
import json
import math
from dataclasses import dataclass

import numpy as np
import trimesh
from django.core.files.storage import default_storage
from scipy.spatial import cKDTree

from .models import CADModel, FeatureSet, SimilarityComparison, SimilaritySearch

ALGORITHM_VERSION = "cpu-registration@1.0"
SAMPLE_COUNT = 1536
RANDOM_SEED = 20260907
ICP_SCORE_THRESHOLD = 0.80
ICP_MAX_ITERATIONS = 50
ICP_DELTA_THRESHOLD = 0.001


class RegistrationValidationError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.user_message = message


@dataclass(frozen=True)
class RegistrationResult:
    alignment_status: str
    transform: list[list[float]]
    result: dict[str, object]


def _load_mesh(cad_model: CADModel) -> trimesh.Trimesh:
    preview = cad_model.preview_artifact_version
    if preview is None or not default_storage.exists(preview.storage_key):
        raise RegistrationValidationError(
            "CAD_PREVIEW_NOT_AVAILABLE", "Both CAD records require governed preview geometry."
        )
    with default_storage.open(preview.storage_key, "rb") as source:
        mesh = trimesh.load(io.BytesIO(source.read()), file_type="stl", force="mesh")
    if not isinstance(mesh, trimesh.Trimesh) or mesh.is_empty:
        raise RegistrationValidationError("CAD_PREVIEW_INVALID", "CAD preview is not a mesh.")
    return mesh


def _principal_axes(points: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    center = points.mean(axis=0)
    centered = points - center
    values, vectors = np.linalg.eigh(np.cov(centered, rowvar=False, bias=True))
    order = np.argsort(values)[::-1]
    return center, np.maximum(values[order], 0.0), vectors[:, order]


def _matrix(rotation: np.ndarray, translation: np.ndarray) -> np.ndarray:
    transform = np.eye(4)
    transform[:3, :3] = rotation
    transform[:3, 3] = translation
    return transform


def _apply(points: np.ndarray, transform: np.ndarray) -> np.ndarray:
    return points @ transform[:3, :3].T + transform[:3, 3]


def _pca_alignment(query: np.ndarray, candidate: np.ndarray) -> tuple[np.ndarray, float, bool]:
    query_center, query_values, query_axes = _principal_axes(query)
    candidate_center, candidate_values, candidate_axes = _principal_axes(candidate)
    symmetric = any(
        abs(query_values[index] - query_values[index + 1])
        / max(query_values[index], query_values[index + 1], 1e-12)
        < 0.03
        for index in (0, 1)
    )
    tree = cKDTree(query)
    best_transform: np.ndarray | None = None
    best_rmse = math.inf
    for signs in itertools.product((-1.0, 1.0), repeat=3):
        sign_matrix = np.diag(signs)
        rotation = query_axes @ sign_matrix @ candidate_axes.T
        if np.linalg.det(rotation) < 0:
            continue
        translation = query_center - rotation @ candidate_center
        transform = _matrix(rotation, translation)
        distances, _ = tree.query(_apply(candidate, transform), workers=1)
        rmse = float(np.sqrt(np.mean(np.square(distances))))
        if rmse < best_rmse:
            best_rmse, best_transform = rmse, transform
    if best_transform is None:
        raise RegistrationValidationError(
            "PCA_ALIGNMENT_FAILED", "No rigid PCA transform was valid."
        )
    return best_transform, best_rmse, symmetric


def _rigid_update(source: np.ndarray, target: np.ndarray) -> np.ndarray:
    source_center, target_center = source.mean(axis=0), target.mean(axis=0)
    covariance = (source - source_center).T @ (target - target_center)
    left, _, right = np.linalg.svd(covariance)
    rotation = right.T @ left.T
    if np.linalg.det(rotation) < 0:
        right[-1, :] *= -1
        rotation = right.T @ left.T
    return _matrix(rotation, target_center - rotation @ source_center)


def _icp(
    query: np.ndarray, candidate: np.ndarray, initial: np.ndarray
) -> tuple[np.ndarray, float, int, bool]:
    transform = initial.copy()
    tree = cKDTree(query)
    previous = math.inf
    for iteration in range(1, ICP_MAX_ITERATIONS + 1):
        aligned = _apply(candidate, transform)
        distances, indices = tree.query(aligned, workers=1)
        rmse = float(np.sqrt(np.mean(np.square(distances))))
        if abs(previous - rmse) < ICP_DELTA_THRESHOLD:
            return transform, rmse, iteration, True
        update = _rigid_update(aligned, query[indices])
        transform = update @ transform
        previous = rmse
    return transform, previous, ICP_MAX_ITERATIONS, False


def _validate_roi(roi: dict[str, object] | None) -> dict[str, list[float]]:
    if not roi:
        return {}
    try:
        minimum = [float(value) for value in roi["min"]]
        maximum = [float(value) for value in roi["max"]]
    except (KeyError, TypeError, ValueError) as exc:
        raise RegistrationValidationError(
            "VALIDATION_ROI", "roi requires numeric min and max arrays."
        ) from exc
    if (
        len(minimum) != 3
        or len(maximum) != 3
        or any(a >= b for a, b in zip(minimum, maximum, strict=True))
    ):
        raise RegistrationValidationError(
            "VALIDATION_ROI", "roi min must be lower than max on all three axes."
        )
    return {"min": minimum, "max": maximum}


def compute_registration(
    query_mesh: trimesh.Trimesh,
    candidate_mesh: trimesh.Trimesh,
    *,
    overall_score: float,
    roi: dict[str, object] | None = None,
    sample_count: int = SAMPLE_COUNT,
    seed: int = RANDOM_SEED,
) -> RegistrationResult:
    roi_contract = _validate_roi(roi)
    query_points, query_faces = trimesh.sample.sample_surface(query_mesh, sample_count, seed=seed)
    candidate_points, _ = trimesh.sample.sample_surface(candidate_mesh, sample_count, seed=seed)
    query_points = np.asarray(query_points, dtype=float)
    candidate_points = np.asarray(candidate_points, dtype=float)
    transform, pca_rmse, symmetric = _pca_alignment(query_points, candidate_points)
    icp_iterations = 0
    icp_converged = False
    if overall_score >= ICP_SCORE_THRESHOLD:
        transform, alignment_rmse, icp_iterations, icp_converged = _icp(
            query_points, candidate_points, transform
        )
        alignment_status = "full" if icp_converged else "partial"
    else:
        alignment_rmse = pca_rmse
        alignment_status = "skipped"

    aligned = _apply(candidate_points, transform)
    if roi_contract:
        minimum, maximum = np.asarray(roi_contract["min"]), np.asarray(roi_contract["max"])
        query_mask = np.all((query_points >= minimum) & (query_points <= maximum), axis=1)
        candidate_mask = np.all((aligned >= minimum) & (aligned <= maximum), axis=1)
        if int(query_mask.sum()) < 16 or int(candidate_mask.sum()) < 16:
            raise RegistrationValidationError(
                "ROI_INSUFFICIENT_GEOMETRY",
                "The ROI must contain at least 16 samples from each model.",
            )
        query_points = query_points[query_mask]
        query_faces = query_faces[query_mask]
        aligned = aligned[candidate_mask]

    tree = cKDTree(query_points)
    distances, nearest = tree.query(aligned, workers=1)
    signed_available = bool(query_mesh.is_watertight and query_mesh.is_winding_consistent)
    if signed_available:
        nearest_normals = np.asarray(query_mesh.face_normals)[np.asarray(query_faces)[nearest]]
        deviations = distances * np.sign(
            np.sum((aligned - query_points[nearest]) * nearest_normals, axis=1)
        )
        distance_mode = "signed"
    else:
        deviations = distances
        distance_mode = "unsigned"
    rmse = float(np.sqrt(np.mean(np.square(deviations))))
    model_scale = max(float(np.linalg.norm(query_mesh.extents)), 1e-12)
    roi_score = math.exp(-rmse / model_scale)
    heatmap_step = max(1, len(aligned) // 1024)
    heatmap_points = aligned[::heatmap_step][:1024]
    heatmap_deviations = deviations[::heatmap_step][:1024]
    result = {
        "schema_version": "1.0",
        "alignment_status": alignment_status,
        "alignment": {
            "pca_rmse": round(pca_rmse, 6),
            "final_rmse": round(alignment_rmse, 6),
            "icp_attempted": overall_score >= ICP_SCORE_THRESHOLD,
            "icp_converged": icp_converged,
            "icp_iterations": icp_iterations,
            "symmetry_ambiguity": symmetric,
        },
        "deviation": {
            "mode": distance_mode,
            "minimum": round(float(deviations.min()), 6),
            "maximum": round(float(deviations.max()), 6),
            "rmse": round(rmse, 6),
            "sample_count": int(len(deviations)),
            "tolerance": 0.05,
        },
        "roi": roi_contract or None,
        "roi_similarity_score": round(roi_score, 6) if roi_contract else None,
        "heatmap": {
            "positions": [[round(float(v), 6) for v in point] for point in heatmap_points],
            "deviations": [round(float(value), 6) for value in heatmap_deviations],
        },
        "manifest": {
            "algorithm_version": ALGORITHM_VERSION,
            "sample_count": sample_count,
            "random_seed": seed,
            "icp_score_threshold": ICP_SCORE_THRESHOLD,
            "icp_max_iterations": ICP_MAX_ITERATIONS,
            "icp_delta_threshold": ICP_DELTA_THRESHOLD,
        },
    }
    return RegistrationResult(
        alignment_status=alignment_status,
        transform=[[round(float(value), 10) for value in row] for row in transform],
        result=result,
    )


def create_or_get_comparison(
    search: SimilaritySearch,
    candidate: FeatureSet,
    *,
    overall_score: float,
    roi: dict[str, object] | None,
    actor_id: str,
) -> tuple[SimilarityComparison, bool]:
    roi_contract = _validate_roi(roi)
    roi_checksum = hashlib.sha256(
        json.dumps(roi_contract, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    existing = SimilarityComparison.objects.filter(
        search=search,
        candidate_feature_set=candidate,
        roi_checksum=roi_checksum,
        algorithm_version=ALGORITHM_VERSION,
    ).first()
    if existing:
        return existing, False
    computed = compute_registration(
        _load_mesh(search.query_feature_set.cad_model),
        _load_mesh(candidate.cad_model),
        overall_score=overall_score,
        roi=roi_contract,
    )
    comparison = SimilarityComparison.objects.create(
        search=search,
        candidate_feature_set=candidate,
        roi=roi_contract,
        roi_checksum=roi_checksum,
        alignment_status=computed.alignment_status,
        transform=computed.transform,
        result=computed.result,
        algorithm_version=ALGORITHM_VERSION,
        created_by=actor_id[:128],
    )
    return comparison, True
