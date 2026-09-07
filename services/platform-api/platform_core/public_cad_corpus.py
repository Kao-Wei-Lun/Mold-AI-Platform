"""Explicit opt-in download of pinned, small public CAD fixtures; no ingestion."""

import hashlib
import json
import re
from pathlib import Path

import httpx

from .cad_evaluation import file_checksum, validate_manifest

LOCK_PATH = Path(__file__).parent / "fixtures/cad/public-evaluation/mfcad-smoke-lock.json"
DOWNLOAD_LIMIT = 2 * 1024 * 1024


def _store_verified(root: Path, name: str, expected: str, url: str, client: httpx.Client) -> None:
    path = root / name
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Corpus target cannot be a symlink or escape the root")
    if path.exists():
        if not path.is_file() or file_checksum(path) != expected:
            raise ValueError(f"Existing file differs; refusing overwrite: {name}")
        return
    payload = bytearray()
    with client.stream("GET", url) as response:
        response.raise_for_status()
        for chunk in response.iter_bytes():
            payload.extend(chunk)
            if len(payload) > DOWNLOAD_LIMIT:
                raise ValueError("Public CAD download exceeded its 2 MiB limit")
    if hashlib.sha256(payload).hexdigest() != expected:
        raise ValueError(f"Upstream checksum mismatch: {name}")
    with path.open("xb") as target:
        target.write(payload)


def prepare_mfcad_corpus(root: Path, *, transport=None, extended=False) -> dict:
    path = LOCK_PATH.with_name("mfcad-extended-lock.json") if extended else LOCK_PATH
    lock = json.loads(path.read_text(encoding="utf-8"))
    revision = lock["revision"]
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Source must pin a full commit")
    for item in lock["files"]:
        if not re.fullmatch(r"[0-9-]+\.step", item["name"]):
            raise ValueError("Invalid locked source path")
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    base = f"https://raw.githubusercontent.com/hducg/MFCAD/{revision}"
    with httpx.Client(timeout=30, follow_redirects=False, transport=transport) as client:
        _store_verified(
            root, "LICENSE.MFCAD.txt", lock["license_sha256"], base + "/LICENSE", client
        )
        for item in lock["files"]:
            _store_verified(
                root, item["name"], item["sha256"], base + "/dataset/step/" + item["name"], client
            )
    manifest = {
        key: lock[key] for key in ("schema_version", "corpus_id", "source", "revision", "license")
    }
    manifest["purpose"] = "public controlled-identity smoke only; no human relevance labels"
    manifest["models"] = [
        {
            "id": item["name"][:-5],
            "path": item["name"],
            "sha256": item["sha256"],
            "source_url": base + "/dataset/step/" + item["name"],
            # Conservatively keep the generated block family in one development split.
            "family_id": "mfcad-generated-block",
            "split": "development",
            "unit": "unknown",
        }
        for item in lock["files"]
    ]
    manifest["queries"] = [
        {
            "id": "rigid-" + model["id"],
            "model_id": model["id"],
            "split": "development",
            "kind": "controlled_identity",
            "judgments": {model["id"]: 3},
        }
        for model in manifest["models"]
    ]
    validate_manifest(manifest, root)
    path = root / "manifest.json"
    if path.is_symlink():
        raise ValueError("Manifest must not be a symlink")
    if path.exists():
        if json.loads(path.read_text(encoding="utf-8")) != manifest:
            raise ValueError("Existing manifest differs; preserve annotations in a separate corpus")
    else:
        with path.open("x", encoding="utf-8") as target:
            json.dump(manifest, target, indent=2)
    return manifest
