"""Explicitly prefetch approved CPU RAG models for an offline runtime.

Run this only in the connected preparation environment. Production code always
loads from the resulting local cache and never initiates a model download.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from fastembed import TextEmbedding
from flashrank import Ranker

from platform_core.knowledge_models import DENSE_MODEL_NAME, DENSE_MODEL_REVISION, RERANKER_MODEL


def _file_manifest(root: Path) -> list[dict[str, object]]:
    records = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        records.append(
            {
                "path": path.relative_to(root).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": digest.hexdigest(),
            }
        )
    return records


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=Path, default=Path("/data/models"))
    args = parser.parse_args()
    fastembed_dir = args.target / "fastembed"
    flashrank_dir = args.target / "flashrank"
    fastembed_dir.mkdir(parents=True, exist_ok=True)
    flashrank_dir.mkdir(parents=True, exist_ok=True)

    embedding = TextEmbedding(
        model_name=DENSE_MODEL_NAME,
        cache_dir=str(fastembed_dir),
        providers=["CPUExecutionProvider"],
    )
    probe = next(embedding.embed(["模具工程 CPU model readiness probe"]))
    if len(probe) != 512:
        raise RuntimeError(f"Unexpected embedding dimension: {len(probe)}")
    Ranker(model_name=RERANKER_MODEL, cache_dir=str(flashrank_dir))

    manifest = {
        "schema_version": "1.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "runtime_network_download": False,
        "models": {
            "embedding": {
                "name": DENSE_MODEL_NAME,
                "revision": DENSE_MODEL_REVISION,
                "dimension": 512,
                "license": "MIT",
            },
            "reranker": {
                "name": RERANKER_MODEL,
                "revision": "flashrank-onnx-cpu@approved-1",
                "license": "Apache-2.0",
            },
        },
        "files": _file_manifest(args.target),
    }
    manifest_bytes = json.dumps(manifest, indent=2, sort_keys=True).encode()
    (args.target / "manifest.json").write_bytes(manifest_bytes)
    print(f"MODEL_MANIFEST {args.target / 'manifest.json'}")
    print(f"MODEL_FILES {len(manifest['files'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
