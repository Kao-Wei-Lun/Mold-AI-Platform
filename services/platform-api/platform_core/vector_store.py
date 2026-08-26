import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from django.conf import settings

VECTOR_DIMENSION = 12


class VectorStoreError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.user_message = message


@dataclass(frozen=True)
class VectorCandidate:
    feature_set_id: str
    coarse_score: float


def _request(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    *,
    timeout: float = 8,
) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(
        f"{settings.QDRANT_URL.rstrip('/')}{path}",
        data=body,
        method=method,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise VectorStoreError(
            "VECTOR_STORE_HTTP_ERROR",
            f"The vector store rejected the request with HTTP {exc.code}: {detail}",
        ) from exc
    except (OSError, URLError, TimeoutError) as exc:
        raise VectorStoreError(
            "VECTOR_STORE_UNAVAILABLE", "The vector store is temporarily unavailable."
        ) from exc


def ensure_collection() -> None:
    ensure_named_collection(settings.QDRANT_CAD_COLLECTION, VECTOR_DIMENSION)


def ensure_named_collection(collection_name: str, dimension: int) -> None:
    collection = quote(collection_name, safe="")
    try:
        _request("GET", f"/collections/{collection}", timeout=3)
        return
    except VectorStoreError as exc:
        if exc.code != "VECTOR_STORE_HTTP_ERROR" or "HTTP 404" not in str(exc):
            raise

    try:
        _request(
            "PUT",
            f"/collections/{collection}",
            {"vectors": {"size": dimension, "distance": "Cosine"}},
        )
    except VectorStoreError as exc:
        if "HTTP 409" not in str(exc):
            raise


def upsert_feature(*, feature_set_id: str, vector: list[float], payload: dict[str, object]) -> None:
    ensure_collection()
    collection = quote(settings.QDRANT_CAD_COLLECTION, safe="")
    _request(
        "PUT",
        f"/collections/{collection}/points?wait=true",
        {"points": [{"id": feature_set_id, "vector": vector, "payload": payload}]},
    )


def query_similar_points(
    vector: list[float], *, limit: int, filters: dict[str, list[str] | str]
) -> list[VectorCandidate]:
    collection = quote(settings.QDRANT_CAD_COLLECTION, safe="")
    must: list[dict[str, object]] = []
    for key, value in filters.items():
        if isinstance(value, list):
            if value:
                must.append({"key": key, "match": {"any": value}})
        elif value:
            must.append({"key": key, "match": {"value": value}})

    payload: dict[str, object] = {"query": vector, "limit": limit, "with_payload": False}
    if must:
        payload["filter"] = {"must": must}
    response = _request(
        "POST",
        f"/collections/{collection}/points/query",
        payload,
    )
    points = response.get("result", {}).get("points", [])
    return [
        VectorCandidate(feature_set_id=str(point["id"]), coarse_score=float(point["score"]))
        for point in points
    ]


def upsert_named_vector(
    *,
    collection_name: str,
    dimension: int,
    point_id: str,
    vector: list[float],
    payload: dict[str, object],
) -> None:
    ensure_named_collection(collection_name, dimension)
    collection = quote(collection_name, safe="")
    _request(
        "PUT",
        f"/collections/{collection}/points?wait=true",
        {"points": [{"id": point_id, "vector": vector, "payload": payload}]},
    )


def query_named_vectors(
    *,
    collection_name: str,
    vector: list[float],
    limit: int,
    filters: dict[str, list[str] | str | bool],
) -> list[VectorCandidate]:
    collection = quote(collection_name, safe="")
    must: list[dict[str, object]] = []
    for key, value in filters.items():
        if isinstance(value, list):
            if value:
                must.append({"key": key, "match": {"any": value}})
        elif value not in (None, ""):
            must.append({"key": key, "match": {"value": value}})
    payload: dict[str, object] = {"query": vector, "limit": limit, "with_payload": False}
    if must:
        payload["filter"] = {"must": must}
    response = _request("POST", f"/collections/{collection}/points/query", payload)
    points = response.get("result", {}).get("points", [])
    return [
        VectorCandidate(feature_set_id=str(point["id"]), coarse_score=float(point["score"]))
        for point in points
    ]
