"""Bounded shared DB cache. Call only after candidate authorization and source hash checks."""

import hashlib
import json
import math
from datetime import timedelta

from django.db import DatabaseError, transaction
from django.utils import timezone

from .cad_local_geometry import ALGORITHM
from .models import SurfaceVerificationCache

SLOTS = 1024
TTL_DAYS = 7
MAX_PAYLOAD_BYTES = 32 * 1024


def fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def valid_payload(payload: dict) -> bool:
    try:
        if len(json.dumps(payload, allow_nan=False).encode()) > MAX_PAYLOAD_BYTES:
            return False
        if (
            payload.get("status") != "computed"
            or payload.get("algorithm") != ALGORITHM
            or payload.get("sample_count") != 1536
            or payload.get("candidate_sample_count") != 1536
            or payload.get("mode") not in {"normalized_shape", "engineering_size"}
        ):
            return False
        for field in ("score_factor", "query_coverage", "candidate_coverage", "f_score"):
            if not isinstance(payload[field], (int, float)) or not 0 <= payload[field] <= 1:
                return False
        for field in ("mean_distance", "p95_distance", "tolerance"):
            if not math.isfinite(payload[field]) or payload[field] < 0:
                return False
        # Only scalar metadata/constants and numeric evidence: no URLs, paths or caller identity.
        allowed_strings = {
            "query",
            "candidate",
            "computed",
            "unavailable",
            ALGORITHM,
            "normalized_shape",
            "engineering_size",
            "mm",
            "normalized_rms_radius",
            "not_calibrated",
            "spatial-patches@1.0",
            "brep-adjacency@1.0",
            "BREP_REPROCESS_OR_STEP_REQUIRED",
        }

        def safe(value):
            if isinstance(value, dict):
                return all(isinstance(k, str) and len(k) < 80 and safe(v) for k, v in value.items())
            if isinstance(value, list):
                return len(value) <= 128 and all(safe(v) for v in value)
            if isinstance(value, str):
                return value in allowed_strings
            return value is None or isinstance(value, (int, float)) and math.isfinite(value)

        return safe(payload)
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
        return False


def read_shared(key: str) -> dict | None:
    try:
        # A failed cache query must not poison a surrounding caller transaction.
        with transaction.atomic():
            row = SurfaceVerificationCache.objects.filter(
                slot=int(key[:8], 16) % SLOTS, cache_key=key, expires_at__gt=timezone.now()
            ).first()
        if row and valid_payload(row.payload) and fingerprint(row.payload) == row.payload_sha256:
            return row.payload
    except (DatabaseError, ValueError, TypeError):
        pass
    return None


def write_shared(key: str, payload: dict) -> bool:
    if not valid_payload(payload):
        return False
    try:
        with transaction.atomic():
            SurfaceVerificationCache.objects.update_or_create(
                slot=int(key[:8], 16) % SLOTS,
                defaults={
                    "cache_key": key,
                    "payload": payload,
                    "payload_sha256": fingerprint(payload),
                    "expires_at": timezone.now() + timedelta(days=TTL_DAYS),
                },
            )
        return True
    except (DatabaseError, ValueError, TypeError):
        return False
