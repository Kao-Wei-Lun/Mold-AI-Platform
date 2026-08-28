import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile

from .design_review import create_design_review_records
from .ingestion import UploadValidationError, create_upload_records
from .models import Artifact, ArtifactVersion, FeatureSet, Job
from .similarity import compare_feature_sets, extract_and_index_cad_model, get_demo_profile
from .tasks import process_cad_job, run_design_review_job

CURATED_CAD_DATASET = "curated-cad-demo-v1"
CURATED_CAD_ERROR_DATASET = "curated-cad-demo-errors-v1"
AUTOMATED_CAD_SMOKE_DATASET = "automated-cad-smoke-v1"
MANUAL_CAD_DATASET = "manual-cad-upload-v1"
MANIFEST_PATH = Path(__file__).parent / "fixtures" / "cad" / "curated-demo-v1" / "manifest.json"


class CADFixtureValidationError(RuntimeError):
    pass


@dataclass(frozen=True)
class CADSeedResult:
    dataset_id: str
    dataset_version: str
    manifest_sha256: str
    created: int
    existing: int
    reconciled: int
    verified: int
    error_controls_verified: int
    golden_similarity_verified: int
    golden_review_verified: int
    artifact_version_ids: tuple[str, ...]


def _number(value: float | int) -> str:
    return f"{float(value):.6f}"


def _triangle(name: str, vertices: list[tuple[float, float, float]]) -> list[str]:
    lines = ["  facet normal 0.000000 0.000000 0.000000", "    outer loop"]
    lines.extend(f"      vertex {_number(x)} {_number(y)} {_number(z)}" for x, y, z in vertices)
    lines.extend(["    endloop", "  endfacet"])
    return lines


def _box_triangles(
    origin: list[float], size: list[float], *, open_top: bool = False
) -> list[list[tuple[float, float, float]]]:
    x, y, z = (float(value) for value in origin)
    dx, dy, dz = (float(value) for value in size)
    p000, p100 = (x, y, z), (x + dx, y, z)
    p010, p110 = (x, y + dy, z), (x + dx, y + dy, z)
    p001, p101 = (x, y, z + dz), (x + dx, y, z + dz)
    p011, p111 = (x, y + dy, z + dz), (x + dx, y + dy, z + dz)
    triangles = [
        [p000, p110, p100],
        [p000, p010, p110],
        [p001, p101, p111],
        [p001, p111, p011],
        [p000, p100, p101],
        [p000, p101, p001],
        [p010, p011, p111],
        [p010, p111, p110],
        [p000, p001, p011],
        [p000, p011, p010],
        [p100, p110, p111],
        [p100, p111, p101],
    ]
    return triangles[:2] + triangles[4:] if open_top else triangles


def render_fixture_bytes(fixture: dict[str, object]) -> bytes:
    generator = fixture.get("generator", "boxes")
    if generator == "invalid_signature":
        return b"This is an intentional invalid STL signature control.\n"
    if generator == "open_box":
        boxes = [{"origin": [0, 0, 0], "size": fixture["size"]}]
        open_top = True
    else:
        boxes = fixture.get("boxes", [])
        open_top = False
    lines = [f"solid {fixture['id']}"]
    for box in boxes:
        for vertices in _box_triangles(box["origin"], box["size"], open_top=open_top):
            lines.extend(_triangle(str(fixture["id"]), vertices))
    lines.append(f"endsolid {fixture['id']}")
    return ("\n".join(lines) + "\n").encode("ascii")


def load_cad_manifest(*, require_checksums: bool = True) -> tuple[dict[str, object], str]:
    raw = MANIFEST_PATH.read_bytes()
    try:
        manifest = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CADFixtureValidationError("The curated CAD manifest is not valid JSON.") from exc
    if manifest.get("schema_version") != "1.0":
        raise CADFixtureValidationError("Unsupported curated CAD manifest schema version.")
    if manifest.get("dataset_id") != CURATED_CAD_DATASET:
        raise CADFixtureValidationError("The curated CAD manifest dataset ID is incorrect.")
    fixtures = [*manifest.get("fixtures", []), *manifest.get("error_controls", [])]
    ids = [item.get("id") for item in fixtures]
    filenames = [item.get("filename") for item in fixtures]
    if len(ids) != len(set(ids)) or len(filenames) != len(set(filenames)):
        raise CADFixtureValidationError("Fixture IDs and filenames must be unique.")
    if any(Path(str(name)).name != name or not str(name).endswith(".stl") for name in filenames):
        raise CADFixtureValidationError("Fixture filenames must be safe STL basenames.")
    if not 14 <= len(manifest.get("fixtures", [])) <= 22:
        raise CADFixtureValidationError("The normal curated corpus must contain 14 to 22 fixtures.")
    for fixture in fixtures:
        actual = hashlib.sha256(render_fixture_bytes(fixture)).hexdigest()
        expected = fixture.get("sha256")
        if require_checksums and actual != expected:
            raise CADFixtureValidationError(
                f"Fixture checksum mismatch for {fixture.get('id')}: "
                f"expected {expected}, got {actual}."
            )
    return manifest, hashlib.sha256(raw).hexdigest()


def _source_context(
    fixture: dict[str, object], manifest: dict[str, object], manifest_sha256: str
) -> dict[str, object]:
    return {
        "type": "curated_fixture",
        "fixture_id": fixture["id"],
        "role": fixture.get("role", "error_control"),
        "scenario": fixture.get("scenario"),
        "rank_group": fixture.get("rank_group"),
        "dataset_version": manifest["dataset_version"],
        "manifest_sha256": manifest_sha256,
        "generator": manifest["generator"],
        "provenance": manifest["provenance"],
    }


def _artifact_version(
    fixture_id: str, dataset_id: str = CURATED_CAD_DATASET
) -> ArtifactVersion | None:
    return (
        ArtifactVersion.objects.select_related("artifact", "cad_model")
        .filter(
            artifact__dataset_id=dataset_id,
            source_system="curated-cad-generator",
            input_jobs__capability_id="cad.parse",
            input_jobs__input_snapshot__source__fixture_id=fixture_id,
        )
        .order_by("created_at")
        .first()
    )


def _verify_geometry(version: ArtifactVersion, fixture: dict[str, object]) -> None:
    cad = version.cad_model
    if cad.geometry_status != cad.GeometryStatus.SUCCEEDED:
        raise CADFixtureValidationError(f"Fixture {fixture['id']} geometry is not ready.")
    expected_size = fixture.get("expected", {}).get("bbox_size")
    actual_size = cad.bounding_box.get("size", {})
    for axis, expected in zip(("x", "y", "z"), expected_size, strict=True):
        if abs(float(actual_size.get(axis, -1)) - float(expected)) > 1e-5:
            raise CADFixtureValidationError(
                f"Fixture {fixture['id']} bounding box {axis} failed verification."
            )
    for flag in fixture.get("expected", {}).get("required_flags", []):
        if flag not in cad.quality_flags:
            raise CADFixtureValidationError(f"Fixture {fixture['id']} is missing {flag}.")


def _ensure_indexed(
    version: ArtifactVersion, *, verify_only: bool, force_reindex: bool = False
) -> bool:
    feature = version.cad_model.feature_sets.filter(feature_type="cad_similarity").first()
    if feature and feature.index_status == FeatureSet.IndexStatus.INDEXED and not force_reindex:
        return False
    if verify_only:
        raise CADFixtureValidationError(f"Fixture {version.id} is not indexed.")
    extract_and_index_cad_model(version.cad_model)
    return True


def _verify_similarity(manifest: dict[str, object]) -> int:
    profile = get_demo_profile()
    fixtures = {item["id"]: item for item in manifest["fixtures"]}
    verified = 0
    for golden in manifest["golden_similarity"]:
        query_version = _artifact_version(golden["query_id"])
        if query_version is None:
            raise CADFixtureValidationError(f"Missing golden query {golden['query_id']}.")
        query = query_version.cad_model.feature_sets.get(feature_type="cad_similarity")
        grouped: dict[str, list[float]] = {}
        candidate_ids: list[str] = []
        for fixture in fixtures.values():
            if fixture.get("scenario") != golden["scenario"] or fixture["id"] == golden["query_id"]:
                continue
            version = _artifact_version(fixture["id"])
            if version is None:
                raise CADFixtureValidationError(f"Missing golden candidate {fixture['id']}.")
            candidate_ids.append(str(version.id))
            candidate = version.cad_model.feature_sets.get(feature_type="cad_similarity")
            score = float(compare_feature_sets(query, candidate, profile)["overall_score"])
            grouped.setdefault(str(fixture["rank_group"]), []).append(score)
        if str(query_version.id) in candidate_ids:
            raise CADFixtureValidationError("A golden similarity query included itself.")
        order = golden["required_group_order"]
        for better, worse in zip(order, order[1:], strict=False):
            if min(grouped[better]) <= max(grouped[worse]):
                raise CADFixtureValidationError(
                    f"Golden {golden['scenario']} rank invariant failed: {better} <= {worse}."
                )
        verified += 1
    return verified


def _verify_design_reviews(manifest: dict[str, object], *, verify_only: bool) -> int:
    verified = 0
    for golden in manifest["golden_design_review"]:
        version = _artifact_version(golden["fixture_id"])
        if version is None:
            raise CADFixtureValidationError(f"Missing review fixture {golden['fixture_id']}.")
        key = f"curated-cad:{manifest['dataset_version']}:review:{golden['scenario']}"
        existing = Job.objects.filter(idempotency_key=key).first()
        if verify_only and existing is None:
            raise CADFixtureValidationError(f"Missing golden review {golden['scenario']}.")
        records = create_design_review_records(
            version, context=golden["context"], idempotency_key=key
        )
        if records.created:
            run_design_review_job.run(str(records.job.id))
        findings = {
            finding.rule_version.rule_id: finding.result
            for finding in records.review.findings.select_related("rule_version")
        }
        for rule_id, expected in golden["expected"].items():
            if findings.get(rule_id) != expected:
                raise CADFixtureValidationError(
                    f"Golden review {golden['scenario']} expected {rule_id}={expected}."
                )
        verified += 1
    return verified


def seed_curated_cad_demo(
    *, verify_only: bool = False, force_reindex: bool = False
) -> CADSeedResult:
    if verify_only and force_reindex:
        raise CADFixtureValidationError("--verify-only and forced reindex are mutually exclusive.")
    manifest, manifest_sha256 = load_cad_manifest()
    created = existing = reconciled = verified = error_verified = 0
    version_ids: list[str] = []
    for fixture in manifest["fixtures"]:
        version = _artifact_version(fixture["id"])
        if version is None:
            if verify_only:
                raise CADFixtureValidationError(f"Missing curated CAD fixture {fixture['id']}.")
            upload = SimpleUploadedFile(
                fixture["filename"], render_fixture_bytes(fixture), content_type="model/stl"
            )
            records = create_upload_records(
                upload,
                artifact_name=fixture["name"],
                dataset_id=CURATED_CAD_DATASET,
                product_type=fixture["product_type"],
                material_code=fixture["material_code"],
                idempotency_key=f"curated-cad:{manifest['dataset_version']}:{fixture['id']}:parse",
                source_system="curated-cad-generator",
                source_context=_source_context(fixture, manifest, manifest_sha256),
            )
            process_cad_job.run(str(records.job.id))
            version = records.version
            created += 1
        else:
            existing += 1
        version.refresh_from_db()
        if version.sha256 != fixture["sha256"]:
            raise CADFixtureValidationError(f"Stored checksum mismatch for {fixture['id']}.")
        _verify_geometry(version, fixture)
        reconciled += int(
            _ensure_indexed(version, verify_only=verify_only, force_reindex=force_reindex)
        )
        verified += 1
        version_ids.append(str(version.id))

    for fixture in manifest["error_controls"]:
        content = render_fixture_bytes(fixture)
        if fixture["expected_error"] == "VALIDATION_FILE_SIGNATURE":
            try:
                create_upload_records(
                    SimpleUploadedFile(fixture["filename"], content, content_type="model/stl"),
                    dataset_id=CURATED_CAD_ERROR_DATASET,
                )
            except UploadValidationError as exc:
                if exc.code != fixture["expected_error"]:
                    raise CADFixtureValidationError(
                        f"Error control {fixture['id']} returned {exc.code}."
                    ) from exc
            else:
                raise CADFixtureValidationError(f"Error control {fixture['id']} was accepted.")
        else:
            version = _artifact_version(fixture["id"], CURATED_CAD_ERROR_DATASET)
            if version is None:
                if verify_only:
                    raise CADFixtureValidationError(f"Missing error control {fixture['id']}.")
                records = create_upload_records(
                    SimpleUploadedFile(fixture["filename"], content, content_type="model/stl"),
                    artifact_name=fixture["name"],
                    dataset_id=CURATED_CAD_ERROR_DATASET,
                    idempotency_key=(
                        f"curated-cad:{manifest['dataset_version']}:{fixture['id']}:parse"
                    ),
                    source_system="curated-cad-generator",
                    source_context=_source_context(fixture, manifest, manifest_sha256),
                )
                process_cad_job.run(str(records.job.id))
                version = records.version
            version.refresh_from_db()
            if fixture["expected_error"] not in version.cad_model.quality_flags:
                raise CADFixtureValidationError(f"Error control {fixture['id']} did not reproduce.")
        error_verified += 1

    similarity_verified = _verify_similarity(manifest)
    review_verified = _verify_design_reviews(manifest, verify_only=verify_only)
    return CADSeedResult(
        dataset_id=CURATED_CAD_DATASET,
        dataset_version=str(manifest["dataset_version"]),
        manifest_sha256=manifest_sha256,
        created=created,
        existing=existing,
        reconciled=reconciled,
        verified=verified,
        error_controls_verified=error_verified,
        golden_similarity_verified=similarity_verified,
        golden_review_verified=review_verified,
        artifact_version_ids=tuple(version_ids),
    )


def curated_cad_status() -> dict[str, object]:
    manifest, manifest_sha256 = load_cad_manifest()
    expected = len(manifest["fixtures"])
    artifacts = Artifact.objects.filter(
        kind=Artifact.Kind.CAD_SOURCE,
        dataset_id=CURATED_CAD_DATASET,
        versions__source_system="curated-cad-generator",
    ).distinct()
    ready = artifacts.filter(versions__cad_model__geometry_status="succeeded").distinct().count()
    indexed = (
        artifacts.filter(
            versions__cad_model__feature_sets__index_status=FeatureSet.IndexStatus.INDEXED
        )
        .distinct()
        .count()
    )
    return {
        "dataset_id": CURATED_CAD_DATASET,
        "dataset_version": manifest["dataset_version"],
        "manifest_sha256": manifest_sha256,
        "expected": expected,
        "ready": ready,
        "indexed": indexed,
        "reconciled": ready == expected and indexed == expected,
        "golden_scenarios": {
            "similarity": len(manifest["golden_similarity"]),
            "design_review": len(manifest["golden_design_review"]),
        },
    }
