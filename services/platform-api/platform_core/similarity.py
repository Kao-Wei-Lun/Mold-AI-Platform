import hashlib
import json
import math
from dataclasses import dataclass

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import (
    ArtifactVersion,
    CADModel,
    FeatureSet,
    Job,
    JobEvent,
    SimilarityProfile,
    SimilaritySearch,
)
from .vector_store import VECTOR_DIMENSION, query_similar_points, upsert_feature

PROFILE_KEY = "demo-general@1.0"
FEATURE_SCHEMA_VERSION = "1.0"
EXTRACTOR_VERSION = "1.0.0"
DEFAULT_WEIGHTS = {
    "geometry": 0.35,
    "dimension": 0.25,
    "topology": 0.30,
    "metadata": 0.10,
}


class SimilarityValidationError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.user_message = message


@dataclass(frozen=True)
class SimilarityRecords:
    search: SimilaritySearch
    job: Job
    created: bool


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def _normalize(vector: list[float]) -> list[float]:
    magnitude = math.sqrt(sum(value * value for value in vector))
    if magnitude == 0:
        return vector
    return [round(value / magnitude, 10) for value in vector]


def _surface_shares(histogram: dict[str, int], face_count: int) -> tuple[float, float, float]:
    denominator = max(face_count, 1)
    plane = histogram.get("plane", 0) / denominator
    triangle = histogram.get("triangle", 0) / denominator
    curved = (
        sum(histogram.get(name, 0) for name in ("cylinder", "cone", "sphere", "torus"))
        / denominator
    )
    return plane, curved, triangle


def extract_feature_set(cad_model: CADModel) -> FeatureSet:
    if cad_model.geometry_status != CADModel.GeometryStatus.SUCCEEDED:
        raise SimilarityValidationError(
            "SIMILARITY_GEOMETRY_NOT_READY", "CAD geometry must finish before feature extraction."
        )

    artifact = cad_model.artifact_version.artifact
    size = cad_model.bounding_box.get("size", {})
    dimensions = sorted([float(size.get(axis, 0.0)) for axis in ("x", "y", "z")], reverse=True)
    largest = max(dimensions[0], 1e-12)
    proportions = [dimension / largest for dimension in dimensions]
    bbox_volume = math.prod(dimensions)
    bbox_area = 2 * (
        dimensions[0] * dimensions[1]
        + dimensions[1] * dimensions[2]
        + dimensions[0] * dimensions[2]
    )
    fill_ratio = (
        _clamp(abs(cad_model.volume) / bbox_volume)
        if cad_model.volume is not None and bbox_volume > 0
        else 0.0
    )
    surface_area = float(cad_model.surface_area or 0.0)
    surface_ratio = _clamp(surface_area / bbox_area, maximum=4.0) / 4.0 if bbox_area > 0 else 0.0
    face_count = int(cad_model.face_count or 0)
    edge_count = int(cad_model.edge_count or 0)
    edge_face_ratio = _clamp(edge_count / max(face_count, 1), maximum=4.0) / 4.0
    histogram = {str(key): int(value) for key, value in cad_model.surface_type_histogram.items()}
    plane_share, curved_share, triangle_share = _surface_shares(histogram, face_count)
    vector = _normalize(
        [
            *proportions,
            _clamp(math.log1p(largest) / 12.0),
            fill_ratio,
            surface_ratio,
            _clamp(math.log1p(face_count) / 12.0),
            _clamp(math.log1p(edge_count) / 12.0),
            edge_face_ratio,
            plane_share,
            curved_share,
            triangle_share,
        ]
    )
    if len(vector) != VECTOR_DIMENSION:
        raise RuntimeError("CAD similarity vector dimension does not match the index contract.")

    features = {
        "dimension": {"sorted": dimensions, "unit_system": cad_model.unit_system},
        "geometry": {
            "volume": cad_model.volume,
            "surface_area": surface_area,
            "bbox_volume": bbox_volume,
            "bbox_area": bbox_area,
            "fill_ratio": fill_ratio,
            "surface_ratio": surface_ratio,
            "proportions": proportions,
        },
        "topology": {
            "face_count": face_count,
            "edge_count": edge_count,
            "surface_type_histogram": histogram,
        },
        "metadata": {
            "dataset_id": artifact.dataset_id,
            "product_type": artifact.product_type,
            "material_code": artifact.material_code,
            "classification": artifact.classification,
        },
        "quality_flags": list(cad_model.quality_flags),
    }
    vector_checksum = hashlib.sha256(
        json.dumps(vector, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    feature_set, _ = FeatureSet.objects.get_or_create(
        cad_model=cad_model,
        feature_type="cad_similarity",
        schema_version=FEATURE_SCHEMA_VERSION,
        extractor_version=EXTRACTOR_VERSION,
        defaults={
            "features": features,
            "vector": vector,
            "vector_dimension": len(vector),
            "vector_checksum": vector_checksum,
            "index_collection": settings.QDRANT_CAD_COLLECTION,
            "index_version": settings.SIMILARITY_INDEX_VERSION,
        },
    )
    return feature_set


def index_feature_set(feature_set: FeatureSet) -> FeatureSet:
    artifact = feature_set.cad_model.artifact_version.artifact
    try:
        upsert_feature(
            feature_set_id=str(feature_set.id),
            vector=[float(value) for value in feature_set.vector],
            payload={
                "artifact_version_id": str(feature_set.cad_model.artifact_version_id),
                "classification": artifact.classification,
                "dataset_id": artifact.dataset_id,
                "product_type": artifact.product_type,
                "material_code": artifact.material_code,
                "index_version": feature_set.index_version,
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


def extract_and_index_cad_model(cad_model: CADModel) -> FeatureSet:
    return index_feature_set(extract_feature_set(cad_model))


def get_demo_profile() -> SimilarityProfile:
    profile, _ = SimilarityProfile.objects.get_or_create(
        profile_key=PROFILE_KEY,
        defaults={
            "weights": DEFAULT_WEIGHTS,
            "candidate_collection": settings.QDRANT_CAD_COLLECTION,
            "index_version": settings.SIMILARITY_INDEX_VERSION,
        },
    )
    return profile


def create_similarity_records(
    query_version: ArtifactVersion,
    *,
    top_k: int = 10,
    filters: dict[str, object] | None = None,
    idempotency_key: str | None = None,
) -> SimilarityRecords:
    if not 1 <= top_k <= 50:
        raise SimilarityValidationError("VALIDATION_TOP_K", "top_k must be between 1 and 50.")
    try:
        cad_model = query_version.cad_model
    except CADModel.DoesNotExist as exc:
        raise SimilarityValidationError(
            "SIMILARITY_GEOMETRY_NOT_READY", "The selected artifact has no parsed CAD geometry."
        ) from exc
    feature_set = (
        cad_model.feature_sets.filter(
            feature_type="cad_similarity",
            schema_version=FEATURE_SCHEMA_VERSION,
            extractor_version=EXTRACTOR_VERSION,
        )
        .order_by("-created_at")
        .first()
    )
    if feature_set is None or feature_set.index_status != FeatureSet.IndexStatus.INDEXED:
        raise SimilarityValidationError(
            "SIMILARITY_FEATURE_NOT_INDEXED",
            "The selected CAD feature set is not indexed. Reprocess it after Qdrant recovers.",
        )

    normalized_key = idempotency_key.strip() if idempotency_key else None
    if normalized_key:
        existing_job = Job.objects.filter(idempotency_key=normalized_key).first()
        if existing_job:
            if existing_job.capability_id != "mold.similarity_search":
                raise SimilarityValidationError(
                    "CONFLICT_IDEMPOTENCY_KEY",
                    "The idempotency key is already used by another capability.",
                )
            return SimilarityRecords(existing_job.similarity_search, existing_job, created=False)

    allowed_filter_keys = {"dataset_ids", "product_types", "material_codes"}
    raw_filters = filters or {}
    normalized_filters: dict[str, list[str]] = {}
    for key in allowed_filter_keys:
        values = raw_filters.get(key, [])
        if values is None:
            continue
        if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
            raise SimilarityValidationError(
                "VALIDATION_FILTER", f"{key} must be an array of strings."
            )
        normalized_filters[key] = [value.strip()[:128] for value in values if value.strip()][:25]

    profile = get_demo_profile()
    with transaction.atomic():
        job = Job.objects.create(
            capability_id="mold.similarity_search",
            capability_version="1.0.0",
            state=Job.State.QUEUED,
            queue="cad",
            resource_class="vector",
            input_artifact_version=query_version,
            input_snapshot={
                "schema_version": "1.0",
                "cad_artifact_version_id": str(query_version.id),
                "profile": profile.profile_key,
                "filters": normalized_filters,
                "top_k": top_k,
            },
            idempotency_key=normalized_key,
        )
        JobEvent.objects.create(
            job=job,
            from_state="",
            to_state=Job.State.QUEUED,
            stage="queued",
            progress=0,
        )
        search = SimilaritySearch.objects.create(
            job=job,
            query_feature_set=feature_set,
            profile=profile,
            top_k=top_k,
            filters=normalized_filters,
        )
    return SimilarityRecords(search, job, created=True)


def _ratio_score(first: float | int | None, second: float | int | None) -> float | None:
    if first is None or second is None:
        return None
    first_value = abs(float(first))
    second_value = abs(float(second))
    if first_value == 0 and second_value == 0:
        return 1.0
    if first_value <= 0 or second_value <= 0:
        return 0.0
    return math.exp(-abs(math.log(first_value / second_value)))


def _average(values: list[float | None]) -> float | None:
    available = [value for value in values if value is not None]
    return sum(available) / len(available) if available else None


def _histogram_score(first: dict[str, int], second: dict[str, int]) -> float:
    keys = set(first) | set(second)
    first_total = sum(first.values()) or 1
    second_total = sum(second.values()) or 1
    return sum(
        min(first.get(key, 0) / first_total, second.get(key, 0) / second_total) for key in keys
    )


def compare_feature_sets(
    query: FeatureSet, candidate: FeatureSet, profile: SimilarityProfile
) -> dict[str, object]:
    query_features = query.features
    candidate_features = candidate.features
    query_dimensions = query_features["dimension"]
    candidate_dimensions = candidate_features["dimension"]
    units_comparable = query_dimensions["unit_system"] == candidate_dimensions["unit_system"]
    dimension_score = (
        _average(
            [
                _ratio_score(first, second)
                for first, second in zip(
                    query_dimensions["sorted"], candidate_dimensions["sorted"], strict=True
                )
            ]
        )
        if units_comparable
        else None
    )

    query_geometry = query_features["geometry"]
    candidate_geometry = candidate_features["geometry"]
    geometry_score = _average(
        [
            _average(
                [
                    _ratio_score(first, second)
                    for first, second in zip(
                        query_geometry["proportions"],
                        candidate_geometry["proportions"],
                        strict=True,
                    )
                ]
            ),
            _ratio_score(query_geometry["fill_ratio"], candidate_geometry["fill_ratio"]),
            _ratio_score(query_geometry["surface_ratio"], candidate_geometry["surface_ratio"]),
        ]
    )

    query_topology = query_features["topology"]
    candidate_topology = candidate_features["topology"]
    topology_score = _average(
        [
            _ratio_score(query_topology["face_count"], candidate_topology["face_count"]),
            _ratio_score(query_topology["edge_count"], candidate_topology["edge_count"]),
            _histogram_score(
                query_topology["surface_type_histogram"],
                candidate_topology["surface_type_histogram"],
            ),
        ]
    )

    query_metadata = query_features["metadata"]
    candidate_metadata = candidate_features["metadata"]
    metadata_comparisons = [
        1.0 if query_metadata[key] == candidate_metadata[key] else 0.0
        for key in ("product_type", "material_code")
        if query_metadata.get(key) and candidate_metadata.get(key)
    ]
    metadata_score = _average(metadata_comparisons)
    lane_scores = {
        "geometry": geometry_score,
        "dimension": dimension_score,
        "topology": topology_score,
        "metadata": metadata_score,
    }
    available_weights = {
        lane: float(profile.weights[lane])
        for lane, score in lane_scores.items()
        if score is not None
    }
    weight_total = sum(available_weights.values())
    overall = (
        sum(float(lane_scores[lane]) * weight for lane, weight in available_weights.items())
        / weight_total
    )

    similarities: list[dict[str, object]] = []
    differences: list[dict[str, object]] = []
    if geometry_score is not None and geometry_score >= 0.85:
        similarities.append(
            {
                "type": "shape_proportions",
                "message": "Overall bounding-box proportions and occupied volume are close.",
                "evidence_ref": f"feature-set:{candidate.id}:geometry",
            }
        )
    elif geometry_score is not None:
        differences.append(
            {
                "type": "shape_proportions",
                "message": "Shape proportions or occupied volume differ materially.",
                "evidence_ref": f"feature-set:{candidate.id}:geometry",
            }
        )
    if dimension_score is None:
        differences.append(
            {
                "type": "unit_mismatch",
                "message": "Absolute dimensions were not scored because unit systems differ.",
                "evidence_ref": f"feature-set:{candidate.id}:dimension",
            }
        )
    elif dimension_score >= 0.85:
        similarities.append(
            {
                "type": "overall_dimensions",
                "message": "Overall dimensions are within a similar range.",
                "evidence_ref": f"feature-set:{candidate.id}:dimension",
            }
        )
    else:
        differences.append(
            {
                "type": "overall_dimensions",
                "message": "One or more overall dimensions differ materially.",
                "evidence_ref": f"feature-set:{candidate.id}:dimension",
            }
        )
    if topology_score is not None and topology_score >= 0.85:
        similarities.append(
            {
                "type": "topology_complexity",
                "message": "Face, edge, and surface-type distributions are similar.",
                "evidence_ref": f"feature-set:{candidate.id}:topology",
            }
        )
    elif topology_score is not None:
        differences.append(
            {
                "type": "topology_complexity",
                "message": "Face, edge, or surface-type distributions differ.",
                "evidence_ref": f"feature-set:{candidate.id}:topology",
            }
        )

    return {
        "overall_score": round(overall, 6),
        "sub_scores": {
            lane: round(score, 6) if score is not None else None
            for lane, score in lane_scores.items()
        },
        "effective_weights": {
            lane: round(weight / weight_total, 6) for lane, weight in available_weights.items()
        },
        "feature_availability": {lane: score is not None for lane, score in lane_scores.items()},
        "similarities": similarities[:3],
        "differences": differences[:3],
    }


def run_similarity(search: SimilaritySearch) -> dict[str, object]:
    query_feature = search.query_feature_set
    query_artifact = query_feature.cad_model.artifact_version.artifact
    qdrant_filters: dict[str, list[str] | str] = {
        "classification": query_artifact.classification,
        "index_version": search.profile.index_version,
    }
    filter_mapping = {
        "dataset_ids": "dataset_id",
        "product_types": "product_type",
        "material_codes": "material_code",
    }
    for api_name, payload_name in filter_mapping.items():
        values = search.filters.get(api_name, [])
        if values:
            qdrant_filters[payload_name] = values

    coarse_candidates = query_similar_points(
        [float(value) for value in query_feature.vector],
        limit=min(max(search.top_k * 5, 20), 200),
        filters=qdrant_filters,
    )
    coarse_by_id = {
        candidate.feature_set_id: candidate.coarse_score for candidate in coarse_candidates
    }
    candidate_features = FeatureSet.objects.filter(
        id__in=coarse_by_id,
        index_status=FeatureSet.IndexStatus.INDEXED,
        index_version=search.profile.index_version,
    ).select_related(
        "cad_model__artifact_version__artifact",
        "cad_model__preview_artifact_version",
    )

    matches = []
    for candidate in candidate_features:
        if candidate.id == query_feature.id:
            continue
        comparison = compare_feature_sets(query_feature, candidate, search.profile)
        cad_model = candidate.cad_model
        artifact_version = cad_model.artifact_version
        artifact = artifact_version.artifact
        preview = cad_model.preview_artifact_version
        matches.append(
            {
                "rank": 0,
                "artifact_id": str(artifact.id),
                "artifact_version_id": str(artifact_version.id),
                "artifact_name": artifact.name,
                "dataset_id": artifact.dataset_id,
                "product_type": artifact.product_type,
                "material_code": artifact.material_code,
                "coarse_score": round(coarse_by_id[str(candidate.id)], 6),
                **comparison,
                "quality_flags": list(cad_model.quality_flags),
                "preview": {
                    "artifact_version_id": str(preview.id),
                    "download_url": f"/api/v1/artifact-versions/{preview.id}/download",
                }
                if preview
                else None,
            }
        )
    matches.sort(key=lambda match: (-float(match["overall_score"]), match["artifact_version_id"]))
    matches = matches[: search.top_k]
    for rank, match in enumerate(matches, start=1):
        match["rank"] = rank

    query_preview = query_feature.cad_model.preview_artifact_version
    return {
        "schema_version": "1.0",
        "search_id": str(search.id),
        "query_ref": {
            "artifact_id": str(query_artifact.id),
            "cad_artifact_version_id": str(query_feature.cad_model.artifact_version_id),
            "artifact_name": query_artifact.name,
            "preview": {
                "artifact_version_id": str(query_preview.id),
                "download_url": f"/api/v1/artifact-versions/{query_preview.id}/download",
            }
            if query_preview
            else None,
        },
        "profile": search.profile.profile_key,
        "profile_weights": search.profile.weights,
        "feature_schema_version": query_feature.schema_version,
        "extractor_version": query_feature.extractor_version,
        "index_version": search.profile.index_version,
        "filters": search.filters,
        "result_count": len(matches),
        "results": matches,
        "limitations": [
            "Demo ranking uses deterministic geometry, dimension, topology, "
            "and available metadata lanes.",
            "A learned visual embedding lane is not included in Stage 3.",
        ],
        "lineage_ref": f"similarity-search:{search.id}",
    }
