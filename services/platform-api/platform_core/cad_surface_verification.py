"""Bounded, sampled CPU surface evidence, independent of coarse similarity scores."""

from __future__ import annotations

import itertools
import math
import time

import numpy as np
import trimesh
from scipy.spatial import cKDTree

from .cad_registration import _apply, _matrix, _principal_axes, _rigid_update

ALGORITHM = "cpu-surface-verification@1.0"
SAMPLE_COUNT = 1536
SEED = 20260907
TOLERANCE = 0.08  # Fractions of surface RMS radius, NOT mm or a calibrated decision threshold.
MAX_FACES = 1_000_000
MAX_ITERATIONS = 30
START_COUNT = 3


class SurfaceVerificationError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def check_deadline(deadline: float | None) -> None:
    if deadline is not None and time.monotonic() >= deadline:
        raise SurfaceVerificationError("SURFACE_BUDGET_EXCEEDED")


def sample_shape(
    mesh: trimesh.Trimesh, *, sample_count: int = SAMPLE_COUNT, deadline: float | None = None
) -> np.ndarray:
    check_deadline(deadline)
    if not 128 <= sample_count <= 4096:
        raise SurfaceVerificationError("SURFACE_SAMPLE_LIMIT")
    if (
        not isinstance(mesh, trimesh.Trimesh)
        or mesh.is_empty
        or len(mesh.faces) > MAX_FACES
        or not np.all(np.isfinite(mesh.vertices))
        or not math.isfinite(mesh.area)
        or mesh.area <= 0
    ):
        raise SurfaceVerificationError("SURFACE_INVALID_MESH")
    points, _ = trimesh.sample.sample_surface(mesh, sample_count, seed=SEED)
    centered = points - points.mean(axis=0)
    scale = float(np.sqrt(np.mean(np.sum(centered**2, axis=1))))
    if not math.isfinite(scale) or scale <= 1e-12:
        raise SurfaceVerificationError("SURFACE_DEGENERATE_SCALE")
    check_deadline(deadline)
    return centered / scale


def _distances(query: np.ndarray, candidate: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    return (
        cKDTree(candidate).query(query, workers=1)[0],
        cKDTree(query).query(candidate, workers=1)[0],
    )


def surface_metrics(query: np.ndarray, aligned: np.ndarray, tolerance: float = TOLERANCE) -> dict:
    """Both directions include ALL evaluation samples, not only ICP inliers."""
    forward, reverse = _distances(query, aligned)
    first = float(np.mean(forward <= tolerance))
    second = float(np.mean(reverse <= tolerance))
    mean = float((forward.mean() + reverse.mean()) / 2)
    p95 = float(max(np.percentile(forward, 95), np.percentile(reverse, 95)))
    factor = (
        min(first, second)
        * math.exp(-mean / (2.5 * tolerance))
        * math.exp(-max(p95 - tolerance, 0) / (5 * tolerance))
    )
    return {
        "query_coverage": first,
        "candidate_coverage": second,
        "f_score": 2 * first * second / (first + second) if first + second else 0.0,
        "mean_distance": mean,
        "p95_distance": p95,
        "score_factor": float(np.clip(factor, 0, 1)),
    }


def verify_samples(
    query: np.ndarray,
    candidate: np.ndarray,
    *,
    deadline: float | None = None,
    tolerance: float = TOLERANCE,
) -> dict:
    if not math.isfinite(tolerance) or tolerance <= 0:
        raise SurfaceVerificationError("SURFACE_INVALID_TOLERANCE")
    for points in (query, candidate):
        if (
            points.ndim != 2
            or points.shape[1] != 3
            or not 128 <= len(points) <= 4096
            or not np.all(np.isfinite(points))
            or np.linalg.norm(np.std(points, axis=0)) < 1e-12
        ):
            raise SurfaceVerificationError("SURFACE_INVALID_SAMPLES")
    check_deadline(deadline)
    qcenter, qvalues, qaxes = _principal_axes(query)
    ccenter, cvalues, caxes = _principal_axes(candidate)
    initial = []
    for permutation in itertools.permutations(range(3)):
        for signs in itertools.product((-1.0, 1.0), repeat=3):
            rotation = qaxes @ np.eye(3)[:, permutation] @ np.diag(signs) @ caxes.T
            if np.linalg.det(rotation) < 0:
                continue
            check_deadline(deadline)
            transform = _matrix(rotation, qcenter - rotation @ ccenter)
            metric = surface_metrics(query, _apply(candidate, transform), tolerance)
            initial.append((metric["mean_distance"], transform, metric))
    initial.sort(key=lambda item: item[0])
    best_distance, best_transform, best_metric = initial[0]
    best_converged = False
    tree = cKDTree(query)
    for _, start, _metric in initial[:START_COUNT]:
        transform = start.copy()
        previous = math.inf
        for _iteration in range(MAX_ITERATIONS):
            check_deadline(deadline)
            aligned = _apply(candidate, transform)
            metric = surface_metrics(query, aligned, tolerance)
            objective = metric["mean_distance"]
            converged = abs(previous - objective) < 1e-6
            if objective <= best_distance + 1e-12:
                best_distance, best_transform, best_metric = objective, transform.copy(), metric
                best_converged = converged
            if converged:
                break
            # Symmetric correspondences avoid optimizing just the subset-to-whole direction.
            _, nearest_query = tree.query(aligned, workers=1)
            _, nearest_candidate = cKDTree(aligned).query(query, workers=1)
            source = np.concatenate((aligned, aligned[nearest_candidate]))
            target = np.concatenate((query[nearest_query], query))
            transform = _rigid_update(source, target) @ transform
            previous = objective
    check_deadline(deadline)
    ambiguous = any(
        abs(values[i] - values[i + 1]) / max(float(values[i]), 1e-12) < 0.03
        for values in (qvalues, cvalues)
        for i in (0, 1)
    )
    return {
        "status": "computed",
        "algorithm": ALGORITHM,
        "mode": "normalized_shape",
        "distance_unit": "normalized_rms_radius",
        "tolerance": tolerance,
        "sample_count": len(query),
        "candidate_sample_count": len(candidate),
        "random_seed": SEED,
        "initial_orientation_count": len(initial),
        "refined_orientation_count": START_COUNT,
        "max_iterations": MAX_ITERATIONS,
        "converged": best_converged,
        "symmetry_ambiguity": ambiguous,
        "calibration_status": "not_calibrated",
        "normalized_transform": best_transform.tolist(),
        **{key: round(value, 8) for key, value in best_metric.items()},
    }


def verify_meshes(
    query: trimesh.Trimesh,
    candidate: trimesh.Trimesh,
    *,
    sample_count: int = SAMPLE_COUNT,
    deadline: float | None = None,
) -> dict:
    return verify_samples(
        sample_shape(query, sample_count=sample_count, deadline=deadline),
        sample_shape(candidate, sample_count=sample_count, deadline=deadline),
        deadline=deadline,
    )
