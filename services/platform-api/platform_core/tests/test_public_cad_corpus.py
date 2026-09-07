import hashlib
import json
from unittest.mock import patch

import httpx
import pytest

from platform_core.public_cad_corpus import DOWNLOAD_LIMIT, _store_verified, prepare_mfcad_corpus


def test_verified_download_is_idempotent_and_will_not_overwrite(tmp_path):
    body = b"fixture"
    checksum = hashlib.sha256(body).hexdigest()
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(200, content=body)

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        _store_verified(tmp_path, "a.step", checksum, "https://example.org/a", client)
        _store_verified(tmp_path, "a.step", checksum, "https://example.org/a", client)
        assert len(calls) == 1
        with pytest.raises(ValueError, match="overwrite"):
            _store_verified(tmp_path, "a.step", "0" * 64, "https://example.org/a", client)
    assert (tmp_path / "a.step").read_bytes() == body


@pytest.mark.parametrize(
    "payload", [b"bad checksum", b"a" * (DOWNLOAD_LIMIT + 1)], ids=["checksum", "oversize"]
)
def test_bad_download_never_creates_cad_file(tmp_path, payload):
    with httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=payload))
    ) as client:
        with pytest.raises(ValueError):
            _store_verified(tmp_path, "a.step", "0" * 64, "https://example.org/a", client)
    assert not (tmp_path / "a.step").exists()


def test_download_rejects_redirects(tmp_path):
    transport = httpx.MockTransport(
        lambda r: httpx.Response(302, headers={"location": "http://127.0.0.1"})
    )
    with httpx.Client(transport=transport, follow_redirects=False) as client:
        with pytest.raises(httpx.HTTPStatusError):
            _store_verified(tmp_path, "a.step", "0" * 64, "https://example.org/a", client)


def test_preparation_creates_only_controlled_development_labels(tmp_path):
    body, license_body = b"test cad bytes", b"test license"
    lock = {
        "schema_version": "1.0",
        "corpus_id": "test",
        "source": "test",
        "license": "test",
        "revision": "a" * 40,
        "license_sha256": hashlib.sha256(license_body).hexdigest(),
        "files": [{"name": "0-1.step", "sha256": hashlib.sha256(body).hexdigest()}],
    }
    lock_path = tmp_path / "lock.json"
    lock_path.write_text(json.dumps(lock), encoding="utf-8")
    transport = httpx.MockTransport(
        lambda r: httpx.Response(
            200, content=license_body if r.url.path.endswith("LICENSE") else body
        )
    )
    with patch("platform_core.public_cad_corpus.LOCK_PATH", lock_path):
        result = prepare_mfcad_corpus(tmp_path / "corpus", transport=transport)
        assert result == prepare_mfcad_corpus(tmp_path / "corpus", transport=transport)
    assert result["queries"][0]["kind"] == "controlled_identity"
    assert result["queries"][0]["judgments"] == {"0-1": 3}
    assert result["models"][0]["split"] == "development"
