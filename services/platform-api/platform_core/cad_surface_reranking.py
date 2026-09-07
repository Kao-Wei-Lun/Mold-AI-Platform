"""Authorized-candidate integration; bounded process-local caches contain only numeric evidence."""

import hashlib
import io
import json
import math
import time
from collections import OrderedDict
from copy import deepcopy

import trimesh
from django.core.files.storage import default_storage

from .cad_brep_structure import compare_structure
from .cad_local_geometry import ALGORITHM as DETAIL_ALGORITHM
from .cad_local_geometry import sample_payload, verify_payloads
from .cad_surface_verification import (
    ALGORITHM,
    SurfaceVerificationError,
    check_deadline,
    sample_shape,
    verify_samples,
)

MAX_PREVIEW_BYTES = 64 * 1024 * 1024
MAX_CANDIDATES = 10
BUDGET_SECONDS = 30.0
CACHE_ITEMS = 64
_samples: OrderedDict = OrderedDict()
_comparisons: OrderedDict = OrderedDict()


def _remember(cache: OrderedDict, key, value):
    cache[key] = value
    cache.move_to_end(key)
    while len(cache) > CACHE_ITEMS:
        cache.popitem(last=False)


def _load_samples(cad_model, deadline: float, *, detailed=False):
    check_deadline(deadline)
    preview = cad_model.preview_artifact_version
    if preview is None:
        raise SurfaceVerificationError("SURFACE_PREVIEW_MISSING")
    if preview.size_bytes > MAX_PREVIEW_BYTES:
        raise SurfaceVerificationError("SURFACE_PREVIEW_TOO_LARGE")
    try:
        with default_storage.open(preview.storage_key, "rb") as source:
            content = source.read(MAX_PREVIEW_BYTES + 1)
    except (OSError, ValueError) as exc:
        raise SurfaceVerificationError("SURFACE_PREVIEW_UNREADABLE") from exc
    if len(content) > MAX_PREVIEW_BYTES:
        raise SurfaceVerificationError("SURFACE_PREVIEW_TOO_LARGE")
    checksum = hashlib.sha256(content).hexdigest()
    if checksum != preview.sha256:
        raise SurfaceVerificationError("SURFACE_PREVIEW_CHECKSUM_MISMATCH")
    check_deadline(deadline)
    key = (DETAIL_ALGORITHM if detailed else ALGORITHM, checksum)
    cached = _samples.get(key)
    if cached is not None:
        return checksum, cached
    try:
        mesh = trimesh.load(io.BytesIO(content), file_type="stl", force="mesh")
        points = (
            sample_payload(mesh, deadline=deadline)
            if detailed
            else sample_shape(mesh, deadline=deadline)
        )
    except SurfaceVerificationError:
        raise
    except (ValueError, TypeError, IndexError, RuntimeError) as exc:
        raise SurfaceVerificationError("SURFACE_PREVIEW_INVALID") from exc
    _remember(_samples, key, points)
    return checksum, points


def rerank_surfaces(
    matches: list[dict],
    query_feature,
    candidates: dict,
    *,
    policy=ALGORITHM,
    mode="normalized_shape",
    tolerance_mm=0.5,
) -> list[dict]:
    """Call ONLY after existing authorization, classification and engineering filters."""
    deadline = time.monotonic() + BUDGET_SECONDS
    detailed = policy == DETAIL_ALGORITHM
    ordered = sorted(matches, key=lambda m: (-float(m["overall_score"]), m["artifact_version_id"]))
    query_data = None
    query_error = None
    for index, match in enumerate(ordered):
        match["baseline_overall_score"] = match["overall_score"]
        result = {
            "status": "budget_exceeded",
            "algorithm": policy,
            "mode": mode,
            "error_code": "SURFACE_CANDIDATE_LIMIT",
            "calibration_status": "not_calibrated",
        }
        if index < MAX_CANDIDATES:
            try:
                check_deadline(deadline)
                if query_error:
                    raise SurfaceVerificationError(query_error)
                if query_data is None:
                    try:
                        query_data = (
                            _load_samples(query_feature.cad_model, deadline, detailed=True)
                            if detailed
                            else _load_samples(query_feature.cad_model, deadline)
                        )
                    except SurfaceVerificationError as exc:
                        query_error = exc.code
                        raise
                cad = candidates[match["artifact_version_id"]].cad_model
                candidate_hash, points = (
                    _load_samples(cad, deadline, detailed=True)
                    if detailed
                    else _load_samples(cad, deadline)
                )
                query_hash, query_points = query_data
                structure = (
                    compare_structure(query_feature.cad_model.brep_structure, cad.brep_structure)
                    if detailed
                    else {}
                )
                context = {
                    "mode": mode,
                    "tolerance_mm": tolerance_mm,
                    "query_unit": query_feature.cad_model.unit_system if detailed else "unknown",
                    "candidate_unit": cad.unit_system if detailed else "unknown",
                    "structure": structure,
                }
                cache_key = (
                    policy,
                    query_hash,
                    candidate_hash,
                    json.dumps(context, sort_keys=True),
                )
                cached = _comparisons.get(cache_key)
                if cached is None:
                    cached = (
                        verify_payloads(
                            query_points,
                            points,
                            mode=mode,
                            query_unit=context["query_unit"],
                            candidate_unit=context["candidate_unit"],
                            tolerance_mm=tolerance_mm,
                            deadline=deadline,
                        )
                        if detailed
                        else verify_samples(query_points, points, deadline=deadline)
                    )
                    if detailed:
                        cached["brep_structure"] = structure
                        if structure.get("status") == "computed":
                            cached["score_factor"] *= math.sqrt(structure["agreement"])
                    _remember(_comparisons, cache_key, deepcopy(cached))
                result = deepcopy(cached)
                result["query_preview_sha256"] = query_hash
                result["candidate_preview_sha256"] = candidate_hash
            except SurfaceVerificationError as exc:
                result["status"] = (
                    "budget_exceeded" if exc.code == "SURFACE_BUDGET_EXCEEDED" else "unavailable"
                )
                result["error_code"] = exc.code
        result["candidate_limit"] = MAX_CANDIDATES
        result["cooperative_budget_seconds"] = BUDGET_SECONDS
        match["geometric_verification"] = result
        match["ranking_basis"] = (
            "surface_adjusted" if result["status"] == "computed" else "reference_only"
        )
        if result["status"] == "computed":
            match["overall_score"] = round(
                match["baseline_overall_score"] * result["score_factor"], 6
            )
            match["score_policy"] = policy
            if result["score_factor"] < 0.75:
                match["differences"] = [
                    {
                        "type": "surface_verification",
                        "message": (
                            "Bidirectional surface evidence reduced the baseline ranking score."
                        ),
                        "evidence_ref": f"surface:{query_hash}:{candidate_hash}:{ALGORITHM}",
                    },
                    *match.get("differences", []),
                ]
        else:
            # Legacy numeric contract is BASELINE ONLY; UI must not label it verified.
            match["score_policy"] = "reference-only-unverified"
    return sorted(
        ordered,
        key=lambda m: (
            m["ranking_basis"] != "surface_adjusted",
            -float(m["overall_score"]),
            m["artifact_version_id"],
        ),
    )
