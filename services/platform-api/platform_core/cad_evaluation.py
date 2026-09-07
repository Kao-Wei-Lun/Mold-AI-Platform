"""Offline, provenance-checked geometry evaluation; never writes business data."""

from __future__ import annotations

import hashlib
import json
import math
import time
from pathlib import Path, PureWindowsPath
from tempfile import TemporaryDirectory

import numpy as np
import trimesh

from .cad_processing import parse_cad_file
from .cad_shape_scoring import compare_shape
from .cad_similarity_v2 import EXTRACTOR_VERSION, RANDOM_SEED, extract_shape_descriptor

SPLITS = {"development", "holdout"}
KINDS = {"controlled_identity", "human_geometry"}
MAX_MODELS = 500
MAX_FILE_BYTES = 200 * 1024 * 1024


def file_checksum(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def model_path(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or PureWindowsPath(relative).drive:
        raise ValueError("Model path must be relative")
    normalized = relative.replace("\\", "/")
    if normalized.startswith("/") or ".." in normalized.split("/"):
        raise ValueError("Model path must remain inside corpus root")
    path = (root / normalized).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError("Model path is missing or escapes corpus root")
    if path.suffix.lower() not in {".stl", ".step", ".stp"}:
        raise ValueError("Only STEP/STL are supported")
    if not 0 < path.stat().st_size <= MAX_FILE_BYTES:
        raise ValueError("Model must be nonempty and at most 200 MiB")
    return path


def validate_manifest(manifest: dict, root: Path) -> dict[str, Path]:
    if not isinstance(manifest, dict):
        raise ValueError("Corpus manifest must be a JSON object")
    if manifest.get("schema_version") != "1.0":
        raise ValueError("Unsupported corpus schema")
    for key in ("corpus_id", "source", "revision", "license"):
        if not isinstance(manifest.get(key), str) or not manifest[key].strip():
            raise ValueError(f"Missing corpus provenance: {key}")
    models, queries = manifest.get("models"), manifest.get("queries")
    if not isinstance(models, list) or not 1 <= len(models) <= MAX_MODELS:
        raise ValueError("Corpus requires 1 to 500 models")
    if not isinstance(queries, list) or not 1 <= len(queries) <= MAX_MODELS:
        raise ValueError("Corpus requires 1 to 500 queries")
    paths, by_id, family_splits, hash_splits = {}, {}, {}, {}
    for model in models:
        if not isinstance(model, dict):
            raise ValueError("Each model must be an object")
        for key in ("id", "path", "sha256", "source_url", "family_id", "split", "unit"):
            if not isinstance(model.get(key), str) or not model[key].strip():
                raise ValueError(f"Missing model field: {key}")
        identifier, split = model["id"], model["split"]
        if identifier in by_id or split not in SPLITS:
            raise ValueError("Duplicate model id or invalid split")
        if not model["source_url"].startswith("https://"):
            raise ValueError("Model source URL must use HTTPS")
        path = model_path(root, model["path"])
        checksum = file_checksum(path)
        if checksum != model["sha256"]:
            raise ValueError(f"Checksum mismatch: {identifier}")
        for key, mapping in ((model["family_id"], family_splits), (checksum, hash_splits)):
            if key in mapping and mapping[key] != split:
                raise ValueError("Family or duplicate-content leakage between splits")
            mapping[key] = split
        by_id[identifier], paths[identifier] = model, path
    query_ids = set()
    for query in queries:
        if not isinstance(query, dict):
            raise ValueError("Each query must be an object")
        identifier = query.get("id")
        if not isinstance(identifier, str) or not identifier or identifier in query_ids:
            raise ValueError("Query id is required and unique")
        query_ids.add(identifier)
        model = by_id.get(query.get("model_id"))
        if not model or query.get("split") != model["split"] or query.get("kind") not in KINDS:
            raise ValueError("Invalid query model, split or kind")
        judgments = query.get("judgments")
        if not isinstance(judgments, dict) or not judgments:
            raise ValueError("Explicit judgments are required; unjudged is not negative")
        candidates = {key for key, item in by_id.items() if item["split"] == query["split"]}
        if query["kind"] == "human_geometry":
            candidates.discard(query["model_id"])
            if not query.get("reviewer") or not query.get("reason"):
                raise ValueError("Human judgments need reviewer and reason")
        for key, grade in judgments.items():
            if key not in candidates or type(grade) is not int or grade not in range(4):
                raise ValueError("Invalid judgment reference or grade (0..3)")
        if query["kind"] == "controlled_identity":
            if judgments != {query["model_id"]: 3} or query.get("expected_no_match"):
                raise ValueError("Controlled identity only labels its transformed source")
        elif query.get("expected_no_match"):
            if set(judgments) != candidates or any(judgments.values()):
                raise ValueError("No-match requires all candidates explicitly judged irrelevant")
        elif not any(judgments.values()):
            raise ValueError("A query needs a positive or explicit expected_no_match")
    return paths


def ranking_metrics(ranked: list[str], judgments: dict[str, int], k: int) -> dict:
    if k < 1 or len(set(ranked)) != len(ranked):
        raise ValueError("Invalid K or duplicate ranking ids")
    positives = {key for key, grade in judgments.items() if grade > 0}
    top = ranked[:k]
    first = next((i for i, key in enumerate(ranked, 1) if key in positives), None)

    def dcg(grades: list[int]) -> float:
        return sum((2**grade - 1) / math.log2(i + 2) for i, grade in enumerate(grades))

    ideal = dcg(sorted(judgments.values(), reverse=True)[:k])
    return {
        "recall_at_k": len(positives.intersection(top)) / len(positives) if positives else None,
        "reciprocal_rank": (1 / first if first else 0.0) if positives else None,
        "ndcg_at_k_provisional": dcg([judgments.get(key, 0) for key in top]) / ideal
        if ideal
        else None,
        "judged_coverage_at_k": sum(key in judgments for key in top) / len(top) if top else 0.0,
        "unjudged_at_k": [key for key in top if key not in judgments],
    }


def geometry_comparison(left, right, policy: str) -> float:
    return compare_shape(left.features, right.features, left.vector, right.vector, policy=policy)[
        "score"
    ]


def evaluate_corpus(
    manifest: dict,
    root: Path,
    *,
    split: str = "holdout",
    k: int = 5,
    sample_count: int = 1024,
    policy: str = "cosine-v2",
    threshold: float | None = None,
) -> dict:
    if split not in SPLITS or not 1 <= k <= 50 or not 128 <= sample_count <= 4096:
        raise ValueError("Invalid split, K or sample count")
    if threshold is not None and (not math.isfinite(threshold) or not 0 <= threshold <= 1):
        raise ValueError("Threshold must be finite and within [0, 1]")
    paths = validate_manifest(manifest, root)
    models = [item for item in manifest["models"] if item["split"] == split]
    queries = [item for item in manifest["queries"] if item["split"] == split]
    if not queries:
        raise ValueError("Selected split contains no queries")
    features, transformed_features, failures, parsed = {}, {}, [], []
    with TemporaryDirectory(prefix="mold-cad-eval-") as directory:
        for index, model in enumerate(models):
            started = time.perf_counter()
            try:
                source = paths[model["id"]]
                preview = Path(directory) / f"{index}.stl"
                result = parse_cad_file(source, source.suffix.lower()[1:], preview)
                mesh = trimesh.load(preview, file_type="stl", force="mesh")
                if len(mesh.faces) > 1_000_000:
                    raise ValueError("Preview exceeds evaluation face budget")
                features[model["id"]] = extract_shape_descriptor(mesh, sample_count=sample_count)
                # A fresh extraction from a rigidly transformed mesh; never reuse its vector.
                mesh.apply_transform(trimesh.transformations.rotation_matrix(0.73, [1, 2, 3]))
                mesh.apply_translation([23, -17, 9])
                transformed_features[model["id"]] = extract_shape_descriptor(
                    mesh, sample_count=sample_count
                )
                parsed.append(
                    {
                        "model_id": model["id"],
                        "parser": result.parser_name,
                        "parser_version": result.parser_version,
                        "unit": result.unit_system,
                        "quality_flags": result.quality_flags,
                        "parse_and_descriptor_seconds": time.perf_counter() - started,
                    }
                )
            except Exception as exc:
                features.pop(model["id"], None)
                failures.append(
                    {"model_id": model["id"], "code": getattr(exc, "code", type(exc).__name__)}
                )
    rows, timings = [], []
    for query in queries:
        if query["model_id"] not in features:
            rows.append({"query_id": query["id"], "kind": query["kind"], "status": "parse_failed"})
            continue
        started = time.perf_counter()
        controlled = query["kind"] == "controlled_identity"
        left = (transformed_features if controlled else features)[query["model_id"]]
        ranked = sorted(
            [
                (key, geometry_comparison(left, value, policy))
                for key, value in features.items()
                if controlled or key != query["model_id"]
            ],
            key=lambda item: (-item[1], item[0]),
        )
        timings.append(time.perf_counter() - started)
        metrics = ranking_metrics([key for key, _ in ranked], query["judgments"], k)
        rows.append(
            {
                "query_id": query["id"],
                "kind": query["kind"],
                "status": "incomplete" if failures else "evaluated",
                **metrics,
                "top_k": [{"model_id": key, "score": score} for key, score in ranked[:k]],
                "no_match_false_acceptance": bool(ranked and ranked[0][1] >= threshold)
                if query.get("expected_no_match") and threshold is not None and not failures
                else None,
            }
        )
    groups = {}
    for kind in sorted(KINDS):
        group = [row for row in rows if row["kind"] == kind and row["status"] == "evaluated"]
        metrics = {}
        for metric in (
            "recall_at_k",
            "reciprocal_rank",
            "ndcg_at_k_provisional",
            "judged_coverage_at_k",
            "no_match_false_acceptance",
        ):
            values = [row[metric] for row in group if row.get(metric) is not None]
            metrics[metric] = sum(values) / len(values) if values else None
        groups[kind] = {"evaluated_queries": len(group), **metrics}
    return {
        "schema_version": "1.0",
        "corpus_id": manifest["corpus_id"],
        "manifest_sha256": hashlib.sha256(
            json.dumps(manifest, sort_keys=True).encode()
        ).hexdigest(),
        "policy": policy,
        "extractor_version": EXTRACTOR_VERSION,
        "seed": RANDOM_SEED,
        "sample_count": sample_count,
        "split": split,
        "k": k,
        "threshold": threshold,
        "model_count": len(models),
        "query_count": len(queries),
        "status": "incomplete" if failures else "evaluated",
        "quality_gate": "not_evaluated",  # A benchmark run is not a release approval.
        "human_holdout_available": split == "holdout"
        and groups["human_geometry"]["evaluated_queries"] > 0,
        "groups": groups,
        "queries": rows,
        "parsed_models": parsed,
        "failures": failures,
        "ranking_seconds": {
            "p50": float(np.percentile(timings, 50)) if timings else None,
            "p95": float(np.percentile(timings, 95)) if timings else None,
        },
        "limitations": [
            "Offline geometry ranking, not Qdrant recall or full engineering ranking.",
            "Controlled identity does not establish relevance between different CAD models.",
            "nDCG is provisional with incomplete judgments; unjudged does not mean negative.",
            "No automatic deployment approval or claim of engineering reusability.",
        ],
    }
