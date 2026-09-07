"""Versioned CPU geometry reranking over the existing v2 descriptor blocks."""

import math

import numpy as np

BLOCK_POLICY = "block-distance@1.0"
POLICIES = ("cosine-v2", BLOCK_POLICY)
# Fixed starting weights, not fitted to a purported human-labelled benchmark.
BLOCK_WEIGHTS = {
    "principal_extent_ratios": 0.20,
    "principal_inertia_shares": 0.15,
    "solidity": 0.10,
    "convexity": 0.10,
    "d2_histogram": 0.15,
    "zernike_power": 0.10,
    "normal_angle_histogram": 0.20,
}
BLOCK_LENGTHS = {
    "principal_extent_ratios": 3,
    "principal_inertia_shares": 3,
    "solidity": 1,
    "convexity": 1,
    "d2_histogram": 8,
    "zernike_power": 8,
    "normal_angle_histogram": 8,
}


def compare_shape(
    left_features: dict,
    right_features: dict,
    left_vector,
    right_vector,
    *,
    policy: str = BLOCK_POLICY,
) -> dict:
    if policy not in POLICIES:
        raise ValueError("Unknown geometry ranking policy")
    left, right = np.asarray(left_vector, dtype=float), np.asarray(right_vector, dtype=float)
    if (
        left.shape != (32,)
        or right.shape != (32,)
        or not np.all(np.isfinite(left))
        or not np.all(np.isfinite(right))
    ):
        raise ValueError("Geometry scoring requires finite 32-dimensional descriptors")
    norms = float(np.linalg.norm(left) * np.linalg.norm(right))
    if norms <= 1e-15:
        raise ValueError("Geometry scoring requires nonzero descriptors")
    cosine = float(np.clip(np.dot(left, right) / norms, 0, 1))
    first = left_features.get("shape_invariants")
    second = right_features.get("shape_invariants")
    if policy == "cosine-v2" or not isinstance(first, dict) or not isinstance(second, dict):
        return {
            "score": cosine,
            "policy": "cosine-v2",
            "block_scores": {},
            "block_coverage": None,
            "coarse_cosine": cosine,
            "fallback_reason": "STRUCTURED_BLOCKS_MISSING" if policy != "cosine-v2" else None,
        }
    distances, scores = {}, {}
    for block in BLOCK_WEIGHTS:
        if first.get(block) is None or second.get(block) is None:
            continue
        try:
            a = np.atleast_1d(np.asarray(first[block], dtype=float))
            b = np.atleast_1d(np.asarray(second[block], dtype=float))
        except (ValueError, TypeError):
            continue
        if (
            a.shape != (BLOCK_LENGTHS[block],)
            or b.shape != a.shape
            or not np.all(np.isfinite(a))
            or not np.all(np.isfinite(b))
            or np.any(a < 0)
            or np.any(b < 0)
        ):
            continue
        if block in {"d2_histogram", "normal_angle_histogram", "zernike_power"}:
            if a.sum() <= 1e-15 or b.sum() <= 1e-15:
                continue
            # Hellinger distance treats each histogram independently of its raw scale.
            distance = float(
                np.linalg.norm(np.sqrt(a / a.sum()) - np.sqrt(b / b.sum())) / math.sqrt(2)
            )
        else:
            if np.any(a > 1.000001) or np.any(b > 1.000001):
                continue
            distance = float(np.mean(np.abs(a - b)))
        distances[block] = distance
        scores[block] = round(math.exp(-4.0 * distance), 6)
    coverage = sum(BLOCK_WEIGHTS[block] for block in distances)
    if not distances:
        raise ValueError("No valid shape blocks are available")
    # Geometric mean prevents a perfect constant block from drowning out disagreements.
    score = math.exp(-4 * sum(BLOCK_WEIGHTS[b] * d for b, d in distances.items()) / coverage)
    return {
        "score": score,
        "policy": BLOCK_POLICY,
        "block_scores": scores,
        "block_coverage": round(coverage, 6),
        "coarse_cosine": cosine,
        "fallback_reason": None,
    }
