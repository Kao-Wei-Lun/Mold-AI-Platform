"""Version 2 surface evidence: units, multi-tolerance curves and spatial patches."""

import math

import numpy as np
import trimesh

from .cad_registration import _apply, _principal_axes
from .cad_surface_verification import (
    SAMPLE_COUNT,
    SEED,
    SurfaceVerificationError,
    _distances,
    sample_shape,
    surface_metrics,
    verify_samples,
)

ALGORITHM = "cpu-surface-verification@2.0"
UNIT_MM = {"mm": 1.0, "millimeter": 1.0, "cm": 10.0, "m": 1000.0, "inch": 25.4, "in": 25.4}


def unit_multiplier(unit: str) -> float:
    if str(unit).lower() not in UNIT_MM:
        raise SurfaceVerificationError("SURFACE_KNOWN_UNITS_REQUIRED")
    return UNIT_MM[str(unit).lower()]


def sample_payload(mesh: trimesh.Trimesh, *, deadline=None, sample_count=SAMPLE_COUNT) -> dict:
    points = sample_shape(mesh, deadline=deadline, sample_count=sample_count)
    raw, _ = trimesh.sample.sample_surface(mesh, sample_count, seed=SEED)
    centered = raw - raw.mean(axis=0)
    return {"points": points, "rms_radius": float(np.sqrt(np.mean(np.sum(centered**2, axis=1))))}


def local_evidence(query: np.ndarray, aligned: np.ndarray, tolerance: float) -> dict:
    forward, reverse = _distances(query, aligned)
    center, _, axes = _principal_axes(query)
    a, b = (query - center) @ axes, (aligned - center) @ axes
    minimum, width = a.min(axis=0), np.maximum(np.ptp(a, axis=0), 1e-12)
    levels = []
    for size in (2, 4):
        ac = np.clip(np.floor((a - minimum) / width * size), 0, size - 1).astype(int)
        bc = np.clip(np.floor((b - minimum) / width * size), 0, size - 1).astype(int)
        patches = []
        for cells, distances, direction in ((ac, forward, "query"), (bc, reverse, "candidate")):
            for cell in np.unique(cells, axis=0):
                mask = np.all(cells == cell, axis=1)
                if int(mask.sum()) < 12:
                    continue
                patches.append(
                    {
                        "direction": direction,
                        "cell": cell.tolist(),
                        "samples": int(mask.sum()),
                        "coverage": float(np.mean(distances[mask] <= tolerance)),
                        "p95": float(np.percentile(distances[mask], 95)),
                    }
                )
        ordered = sorted(patches, key=lambda p: (p["coverage"], -p["p95"]))
        tail = ordered[: max(1, math.ceil(len(ordered) * 0.25))]
        levels.append(
            {
                "grid": size,
                "patch_count": len(patches),
                "worst_patches": ordered[:4],
                "lower_quartile_coverage": float(np.mean([p["coverage"] for p in tail]))
                if tail
                else None,
            }
        )
    available = [
        v["lower_quartile_coverage"] for v in levels if v["lower_quartile_coverage"] is not None
    ]
    return {
        "levels": levels,
        "score_factor": math.sqrt(min(available)) if available else 1.0,
        "minimum_patch_samples": 12,
        "algorithm": "spatial-patches@1.0",
    }


def verify_payloads(
    left: dict,
    right: dict,
    *,
    mode="normalized_shape",
    query_unit="unknown",
    candidate_unit="unknown",
    tolerance_mm=0.5,
    deadline=None,
) -> dict:
    if mode not in {"normalized_shape", "engineering_size"}:
        raise SurfaceVerificationError("SURFACE_INVALID_MODE")
    q, c = left["points"], right["points"]
    scale = 1.0
    tolerance = 0.08
    if mode == "engineering_size":
        scale = left["rms_radius"] * unit_multiplier(query_unit)
        candidate_scale = right["rms_radius"] * unit_multiplier(candidate_unit)
        if not math.isfinite(tolerance_mm) or not 0.001 <= tolerance_mm <= 10:
            raise SurfaceVerificationError("SURFACE_INVALID_TOLERANCE")
        c = c * (candidate_scale / scale)  # Both use QUERY scale; no independent rescaling.
        tolerance = tolerance_mm / scale
    result = verify_samples(q, c, tolerance=tolerance, deadline=deadline)
    aligned = _apply(c, np.asarray(result["normalized_transform"]))
    local = local_evidence(q, aligned, tolerance)
    result.update(
        algorithm=ALGORITHM,
        mode=mode,
        local_evidence=local,
        global_score_factor=result["score_factor"],
        score_factor=round(result["score_factor"] * local["score_factor"], 8),
        distance_unit="mm" if mode == "engineering_size" else "normalized_rms_radius",
        normalization_scale_mm=scale if mode == "engineering_size" else None,
    )
    result["tolerance_curve"] = [
        {
            "tolerance": tolerance * factor * scale,
            "f_score": surface_metrics(q, aligned, tolerance * factor)["f_score"],
        }
        for factor in (0.5, 1, 2)
    ]
    for field in ("mean_distance", "p95_distance", "tolerance"):
        result[field] *= scale
    for level in local["levels"]:
        for patch in level["worst_patches"]:
            patch["p95"] *= scale
    return result
