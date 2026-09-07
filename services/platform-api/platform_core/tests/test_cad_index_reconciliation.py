import uuid
from unittest.mock import patch

import pytest
from django.core.management import call_command

from platform_core import cad_index_reconciliation as reconcile
from platform_core.models import ArtifactVersion, FeatureSet

pytestmark = pytest.mark.django_db


def point():
    return {
        "id": str(uuid.uuid4()),
        "vector": [1.0] + [0.0] * 31,
        "payload": {
            "artifact_version_id": str(uuid.uuid4()),
            "dataset_id": "test-public",
            "classification": "public_demo",
            "index_version": "cad-cpu-v2",
        },
    }


def test_dry_run_then_backed_up_exact_orphan_delete(tmp_path):
    orphan = point()
    response = {"result": {"points": [orphan], "next_page_offset": None}}
    backup = tmp_path / "backup.json"

    def request(method, path, payload):
        if "/delete" in path:
            assert backup.is_file()
            assert payload == {"points": [orphan["id"]]}
            return {"status": "ok"}
        return response

    with patch.object(reconcile, "_request", side_effect=request) as remote:
        call_command("reconcile_cad_index", dataset="test-public", output=tmp_path / "dry.json")
        assert remote.call_count == 1
        call_command(
            "reconcile_cad_index",
            dataset="test-public",
            output=backup,
            apply=True,
            expected_orphan_count=1,
        )
        assert remote.call_count == 3
    assert FeatureSet.objects.count() == 0
    assert ArtifactVersion.objects.count() == 0


def test_live_artifact_or_feature_is_retained_and_rechecked():
    response = {"result": {"points": [point()], "next_page_offset": None}}
    with (
        patch.object(reconcile, "_request", return_value=response),
        patch.object(ArtifactVersion.objects, "filter") as artifacts,
    ):
        artifacts.return_value.exists.return_value = True
        report = reconcile.inspect_orphans("test-public")
        assert report["orphan_count"] == 0
        artifacts.return_value.exists.return_value = False
        report = reconcile.inspect_orphans("test-public")
        artifacts.return_value.exists.return_value = True
        with pytest.raises(ValueError, match="changed"):
            reconcile.remove_confirmed_orphans(report, 1)


def test_out_of_scope_or_changed_count_rejects_delete():
    bad = point()
    bad["payload"]["classification"] = "company_internal"
    with patch.object(reconcile, "_request", return_value={"result": {"points": [bad]}}):
        with pytest.raises(ValueError, match="out-of-scope"):
            reconcile.inspect_orphans("test-public")
    bad["payload"]["classification"] = "public_demo"
    with patch.object(reconcile, "_request", return_value={"result": {"points": [bad]}}) as remote:
        report = reconcile.inspect_orphans("test-public")
        with pytest.raises(ValueError, match="count changed"):
            reconcile.remove_confirmed_orphans(report, 2)
        assert remote.call_count == 1
