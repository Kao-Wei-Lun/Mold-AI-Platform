"""Operator diagnostic: public dataset only; business records and vector index stay untouched."""

import json
import platform
import time
import tracemalloc
import uuid
from pathlib import Path

import numpy as np
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from platform_core import cad_surface_reranking as ranking
from platform_core.cad_local_geometry import ALGORITHM
from platform_core.models import FeatureSet
from platform_core.vector_store import query_named_vectors


def percentiles(values):
    return {
        "count": len(values),
        "p50": float(np.percentile(values, 50)) if values else None,
        "p95": float(np.percentile(values, 95)) if values else None,
    }


class Command(BaseCommand):
    help = "Measure public exact/ANN overlap and cold/shared-cache latency; no search jobs created."

    def add_arguments(self, parser):
        parser.add_argument("--dataset", required=True)
        parser.add_argument("--queries", type=int, default=5)
        parser.add_argument("--top-k", type=int, default=20)
        parser.add_argument("--repeats", type=int, default=3)
        parser.add_argument("--output", type=Path, required=True)

    def handle(self, *args, **options):
        if options["output"].exists():
            raise CommandError("Output already exists; choose a new report path")
        if (
            not 1 <= options["queries"] <= 20
            or not 1 <= options["top_k"] <= 200
            or not 2 <= options["repeats"] <= 5
        ):
            raise CommandError("Queries 1..20, top-k 1..200, repeats 2..5 required")
        dataset = options["dataset"]
        if dataset in settings.SIMILARITY_EXCLUDED_DATASETS:
            raise CommandError("Dataset is excluded from similarity")
        features = list(
            FeatureSet.objects.filter(
                schema_version="2.0",
                extractor_version="2.1.0",
                index_status="indexed",
                feature_type="cad_similarity",
                index_version="cad-cpu-v2",
                cad_model__artifact_version__artifact__dataset_id=dataset,
                cad_model__artifact_version__artifact__classification="public_demo",
            )
            .select_related("cad_model__preview_artifact_version")
            .order_by("id")[:1001]
        )
        if not 2 <= len(features) <= 1000:
            raise CommandError(
                "Require 2..1000 indexed public v2 CAD records in the selected dataset"
            )
        namespace = "benchmark-" + str(uuid.uuid4())
        vectors = np.asarray([f.vector for f in features], dtype=float)
        vectors /= np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12)
        cold, warm, rows = [], [], []
        cache_hits, failures = 0, 0
        tracemalloc.start()
        try:
            for index, query in enumerate(features[: options["queries"]]):
                scores = vectors @ vectors[index]
                k = min(options["top_k"], len(features))
                cutoff = sorted(scores, reverse=True)[k - 1]
                equivalent = {
                    str(f.id)
                    for f, score in zip(features, scores, strict=True)
                    if score >= cutoff - 1e-6
                }
                started = time.perf_counter()
                found = query_named_vectors(
                    collection_name=settings.QDRANT_CAD_COLLECTION_V2,
                    vector=list(query.vector),
                    limit=k,
                    filters={
                        "classification": "public_demo",
                        "dataset_id": dataset,
                        "index_version": "cad-cpu-v2",
                    },
                )
                ann_seconds = time.perf_counter() - started
                overlap = len({c.feature_set_id for c in found} & equivalent) / k
                candidate = features[(index + 1) % len(features)]
                observations = []
                for repeat in range(options["repeats"]):
                    ranking._samples.clear()
                    ranking._comparisons.clear()
                    started = time.perf_counter()
                    result = ranking.rerank_surfaces(
                        [
                            {
                                "artifact_version_id": str(candidate.cad_model.artifact_version_id),
                                "overall_score": 1.0,
                            }
                        ],
                        query,
                        {str(candidate.cad_model.artifact_version_id): candidate},
                        policy=ALGORITHM,
                        candidate_limit=1,
                        budget_seconds=30,
                        cache_namespace=namespace,
                    )[0]["geometric_verification"]
                    seconds = time.perf_counter() - started
                    observations.append(
                        {
                            "seconds": seconds,
                            "status": result["status"],
                            "cache_source": result.get("cache_source"),
                            "score_factor": result.get("score_factor"),
                        }
                    )
                    if result["status"] != "computed":
                        failures += 1
                    elif repeat == 0:
                        cold.append(seconds)
                    elif result.get("cache_source") == "shared":
                        warm.append(seconds)
                        cache_hits += 1
                rows.append(
                    {
                        "query_feature_id": str(query.id),
                        "ann_tie_aware_exact_overlap": overlap,
                        "ann_seconds": ann_seconds,
                        "surface_runs": observations,
                    }
                )
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
            ranking._samples.clear()
            ranking._comparisons.clear()
        report = {
            "algorithm": ALGORITHM,
            "dataset_id": dataset,
            "model_count": len(features),
            "platform": platform.platform(),
            "processor": platform.processor(),
            "cold_seconds": percentiles(cold),
            "shared_warm_seconds": percentiles(warm),
            "shared_cache_hits": cache_hits,
            "failed_runs": failures,
            "python_traced_peak_bytes": peak,
            "queries": rows,
            "status": "complete"
            if failures == 0 and len(warm) == len(rows) * (options["repeats"] - 1)
            else "incomplete",
            "limitations": [
                "ANN overlap against exact cosine is not human relevance recall.",
                "Includes identity; no engineering filters. Dataset/classification scope is fixed.",
                "Fresh namespace; warm passes clear process caches and verify source checksums.",
                "Python traced peak excludes native allocations; not total RSS or queue latency.",
                "Small adjacent pairs, not a large-corpus SLA. Writes derived cache only.",
            ],
        }
        with options["output"].open("x", encoding="utf-8") as target:
            json.dump(report, target, indent=2, allow_nan=False)
        self.stdout.write(
            json.dumps(
                {
                    k: report[k]
                    for k in (
                        "status",
                        "cold_seconds",
                        "shared_warm_seconds",
                        "shared_cache_hits",
                        "failed_runs",
                    )
                }
            )
        )
        if report["status"] != "complete":
            raise CommandError("Benchmark incomplete; inspect report")
