"""CPU RAG encoders, query expansion, reranking and calibrated abstention."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from django.conf import settings

from .knowledge_structure import CHUNKER_VERSION, PARSER_VERSION

DENSE_MODEL_NAME = "BAAI/bge-small-zh-v1.5"
DENSE_MODEL_REVISION = "fastembed-onnx-cpu@approved-1"
DENSE_DIMENSION = 512
SPARSE_ENCODER = "mold-bm25-token-hash@1.0.0"
RERANKER_MODEL = "ms-marco-MiniLM-L-12-v2"
RERANKER_VERSION = "flashrank-onnx-cpu@approved-1"
RERANKER_MODEL_FILE = "flashrank-MiniLM-L-12-v2_Q.onnx"
FALLBACK_DENSE_MODEL = "feature-hash-fallback@2.0.0"
FALLBACK_RERANKER = "governed-lexical-reranker@1.1.0"

DOMAIN_SYNONYM_GROUPS = (
    ("縮水", "凹痕", "收縮凹陷", "sink mark"),
    ("短射", "欠注", "充填不足", "short shot"),
    ("結合線", "熔接線", "夾水紋", "weld line"),
    ("頂白", "頂針發白", "頂出應力痕", "stress mark"),
)


@dataclass(frozen=True)
class DenseEncoding:
    vector: list[float]
    model: str
    revision: str
    dimension: int
    mode: str
    checksum: str


@dataclass(frozen=True)
class SparseEncoding:
    indices: list[int]
    values: list[float]
    encoder: str = SPARSE_ENCODER


@dataclass(frozen=True)
class RerankResult:
    index: int
    score: float


def _tokens(text: str) -> list[str]:
    # This tokenizer is only the governed sparse/fallback path. The dense model
    # uses its own packaged tokenizer when available.
    import re

    values: list[str] = []
    for raw in re.findall(r"[^\W_]+", text.casefold(), re.UNICODE):
        if len(raw) > 1:
            values.append(raw)
        for run in re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+", raw):
            values.extend(run[index : index + 2] for index in range(len(run) - 1))
    return values


def _fallback_rerank_tokens(text: str) -> set[str]:
    """Return lexical tokens without artificial whole-sentence CJK terms.

    The retrieval tokenizer remains unchanged because it is part of the
    persisted dense/sparse index contract. This view is local to the
    versioned fallback reranker, so improving overlap does not invalidate an
    existing v2 collection.
    """
    import re

    values: list[str] = []
    for raw in re.findall(r"[^\W_]+", text.casefold(), re.UNICODE):
        cjk_runs = re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+", raw)
        if len(raw) > 1 and not cjk_runs:
            values.append(raw)
        for run in cjk_runs:
            values.extend(run[index : index + 2] for index in range(len(run) - 1))
    return set(values)


def expand_domain_query(query: str) -> tuple[str, list[str]]:
    normalized = query.casefold()
    expansions: list[str] = []
    for group in DOMAIN_SYNONYM_GROUPS:
        if any(term.casefold() in normalized for term in group):
            expansions.extend(term for term in group if term.casefold() not in normalized)
    deduplicated = list(dict.fromkeys(expansions))
    return " ".join([query, *deduplicated]).strip(), deduplicated


def sparse_encode(text: str) -> SparseEncoding:
    counts: dict[int, int] = {}
    for token in _tokens(text):
        index = int.from_bytes(hashlib.blake2b(token.encode(), digest_size=4).digest(), "big")
        counts[index] = counts.get(index, 0) + 1
    indices = sorted(counts)
    return SparseEncoding(
        indices=indices,
        values=[round(1.0 + math.log(counts[index]), 8) for index in indices],
    )


def _fallback_dense(text: str) -> DenseEncoding:
    vector = [0.0] * DENSE_DIMENSION
    for token in _tokens(text):
        digest = hashlib.blake2b(token.encode(), digest_size=8).digest()
        index = int.from_bytes(digest[:4], "big") % DENSE_DIMENSION
        vector[index] += 1.0 if digest[4] % 2 == 0 else -1.0
    magnitude = math.sqrt(sum(value * value for value in vector))
    if magnitude:
        vector = [round(value / magnitude, 10) for value in vector]
    checksum = hashlib.sha256(json.dumps(vector, separators=(",", ":")).encode()).hexdigest()
    return DenseEncoding(
        vector=vector,
        model=FALLBACK_DENSE_MODEL,
        revision="deterministic-cpu",
        dimension=DENSE_DIMENSION,
        mode="degraded",
        checksum=checksum,
    )


@lru_cache(maxsize=1)
def _fastembed_model():
    from fastembed import TextEmbedding  # type: ignore[import-not-found]

    return TextEmbedding(
        model_name=DENSE_MODEL_NAME,
        cache_dir=str(settings.EMBEDDING_MODEL_PATH),
        local_files_only=True,
        providers=["CPUExecutionProvider"],
    )


def dense_encode(text: str) -> DenseEncoding:
    model_path = Path(settings.EMBEDDING_MODEL_PATH)
    if model_path.exists():
        try:
            vector = [float(value) for value in next(_fastembed_model().embed([text]))]
            if len(vector) != DENSE_DIMENSION:
                raise ValueError(f"Expected {DENSE_DIMENSION} dimensions, got {len(vector)}.")
            checksum = hashlib.sha256(
                json.dumps(vector, separators=(",", ":")).encode()
            ).hexdigest()
            return DenseEncoding(
                vector=vector,
                model=DENSE_MODEL_NAME,
                revision=DENSE_MODEL_REVISION,
                dimension=DENSE_DIMENSION,
                mode="active",
                checksum=checksum,
            )
        except (ImportError, OSError, RuntimeError, StopIteration, ValueError):
            if settings.RAG_CPU_MODELS_REQUIRED:
                raise
    if settings.RAG_CPU_MODELS_REQUIRED:
        raise RuntimeError(
            "The approved CPU embedding model is unavailable. Run scripts/download_models.py "
            "during the connected build/preparation step."
        )
    return _fallback_dense(text)


def _fallback_rerank_score(query: str, passage: str, fused_score: float) -> float:
    query_tokens = _fallback_rerank_tokens(query)
    passage_tokens = _fallback_rerank_tokens(passage)
    overlap = len(query_tokens & passage_tokens) / max(len(query_tokens), 1)
    phrase = 1.0 if query.casefold() in passage.casefold() else 0.0
    return round(min(1.0, 0.62 * overlap + 0.18 * phrase + 0.20 * min(fused_score, 1.0)), 8)


@lru_cache(maxsize=1)
def _flashrank_model():
    from flashrank import Ranker  # type: ignore[import-not-found]

    return Ranker(
        model_name=RERANKER_MODEL,
        cache_dir=str(settings.RERANKER_MODEL_PATH),
    )


def _flashrank_is_packaged() -> bool:
    """Only allow FlashRank after its complete approved artifact is local.

    FlashRank downloads a model when its model directory is absent.  Checking
    the exact ONNX file before constructing ``Ranker`` keeps runtime network
    egress disabled by contract.
    """
    return (Path(settings.RERANKER_MODEL_PATH) / RERANKER_MODEL / RERANKER_MODEL_FILE).is_file()


def rerank_passages(
    query: str,
    passages: list[str],
    fused_scores: list[float],
    *,
    fallback_queries: list[str] | None = None,
) -> tuple[list[RerankResult], dict[str, str]]:
    if _flashrank_is_packaged():
        try:
            from flashrank import RerankRequest  # type: ignore[import-not-found]

            payload = [
                {"id": index, "text": text, "meta": {}} for index, text in enumerate(passages)
            ]
            ranked = _flashrank_model().rerank(RerankRequest(query=query, passages=payload))
            results = [
                RerankResult(index=int(item["id"]), score=float(item["score"])) for item in ranked
            ]
            return results, {"model": RERANKER_MODEL, "version": RERANKER_VERSION}
        except (ImportError, KeyError, OSError, RuntimeError, TypeError, ValueError):
            if settings.RAG_CPU_MODELS_REQUIRED:
                raise
    if settings.RAG_CPU_MODELS_REQUIRED:
        raise RuntimeError(
            "The approved CPU reranker is unavailable. Run scripts/download_models.py during "
            "the connected build/preparation step."
        )
    governed_queries = list(dict.fromkeys(fallback_queries or [query]))
    results = [
        RerankResult(
            index=index,
            score=max(
                _fallback_rerank_score(candidate_query, text, fused_scores[index])
                for candidate_query in governed_queries
            ),
        )
        for index, text in enumerate(passages)
    ]
    results.sort(key=lambda item: (-item.score, item.index))
    return results, {
        "model": FALLBACK_RERANKER,
        "version": "deterministic-cpu",
        "query_policy": "original-plus-expansion-max@1.0.0",
    }


def load_abstention_calibration() -> dict[str, object]:
    path = Path(settings.RAG_ABSTENTION_CALIBRATION_PATH)
    with path.open(encoding="utf-8") as source:
        config = json.load(source)
    required = {"schema_version", "calibration_id", "threshold", "approved_by", "approved_at"}
    if not required.issubset(config):
        raise RuntimeError("RAG abstention calibration is incomplete.")
    threshold = float(config["threshold"])
    if not 0 <= threshold <= 1:
        raise RuntimeError("RAG abstention threshold must be between 0 and 1.")
    return config


def pipeline_manifest(dense: DenseEncoding, reranker: dict[str, str]) -> dict[str, object]:
    manifest = {
        "schema_version": "2.0",
        "parser_version": PARSER_VERSION,
        "chunker_version": CHUNKER_VERSION,
        "dense_model": dense.model,
        "dense_revision": dense.revision,
        "dense_dimension": dense.dimension,
        "sparse_encoder": SPARSE_ENCODER,
        "reranker": reranker,
    }
    manifest["checksum"] = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return manifest
