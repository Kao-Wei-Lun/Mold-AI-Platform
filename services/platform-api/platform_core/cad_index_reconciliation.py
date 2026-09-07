"""Operator-only orphan index reconciliation; database artifacts are never deleted."""

import uuid
from urllib.parse import quote

from django.conf import settings

from .models import ArtifactVersion, FeatureSet
from .vector_store import _request

MAX_POINTS = 5000


def inspect_orphans(dataset: str) -> dict:
    if not dataset or len(dataset) > 128:
        raise ValueError("Explicit dataset required")
    collection = settings.QDRANT_CAD_COLLECTION_V2
    points, offset = [], None
    seen_offsets = set()
    while True:
        payload = {
            "limit": 100,
            "with_payload": True,
            "with_vector": True,
            "filter": {
                "must": [
                    {"key": "dataset_id", "match": {"value": dataset}},
                    {"key": "classification", "match": {"value": "public_demo"}},
                    {"key": "index_version", "match": {"value": "cad-cpu-v2"}},
                ]
            },
        }
        if offset is not None:
            payload["offset"] = offset
        response = _request(
            "POST", f"/collections/{quote(collection, safe='')}/points/scroll", payload
        )
        result = response["result"]
        points.extend(result["points"])
        if len(points) > MAX_POINTS:
            raise ValueError("Too many points for bounded reconciliation")
        offset = result.get("next_page_offset")
        if offset is None:
            break
        if str(offset) in seen_offsets:
            raise ValueError("Repeated vector store page offset")
        seen_offsets.add(str(offset))
    orphans, retained = [], []
    for point in points:
        data = point.get("payload", {})
        # Validate returned scope again; never trust a broadened/malformed response.
        if (
            data.get("dataset_id") != dataset
            or data.get("classification") != "public_demo"
            or data.get("index_version") != "cad-cpu-v2"
        ):
            raise ValueError("Vector store returned out-of-scope point")
        identifier = str(uuid.UUID(str(point["id"])))
        artifact = str(uuid.UUID(str(data["artifact_version_id"])))
        if (
            FeatureSet.objects.filter(id=identifier).exists()
            or ArtifactVersion.objects.filter(id=artifact).exists()
        ):
            retained.append(identifier)
        else:
            orphans.append(point)  # Includes full vector and payload for recovery.
    return {
        "schema_version": "1.0",
        "collection": collection,
        "dataset_id": dataset,
        "scanned": len(points),
        "retained_count": len(retained),
        "orphan_count": len(orphans),
        "orphan_points": orphans,
        "action": "dry_run",
        "database_records_deleted": 0,
    }


def remove_confirmed_orphans(report: dict, expected_count: int) -> int:
    points = report["orphan_points"]
    if report["collection"] != settings.QDRANT_CAD_COLLECTION_V2 or len(points) != expected_count:
        raise ValueError("Collection or expected orphan count changed")
    for point in points:
        if (
            FeatureSet.objects.filter(id=point["id"]).exists()
            or ArtifactVersion.objects.filter(id=point["payload"]["artifact_version_id"]).exists()
        ):
            raise ValueError("Database changed; rerun inspection before cleaning")
    if not points:
        return 0
    _request(
        "POST",
        f"/collections/{quote(report['collection'], safe='')}/points/delete?wait=true",
        {"points": [str(p["id"]) for p in points]},
    )
    return len(points)
