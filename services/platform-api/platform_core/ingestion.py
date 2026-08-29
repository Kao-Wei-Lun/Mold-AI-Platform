import hashlib
import struct
import uuid
from dataclasses import dataclass

from django.conf import settings
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction

from .models import Artifact, ArtifactVersion, CADModel, Job, JobEvent, MoldRevision

SUPPORTED_EXTENSIONS = {".step": "step", ".stp": "step", ".stl": "stl"}
MEDIA_TYPES = {"step": "model/step", "stl": "model/stl"}
EICAR_MARKER = b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE"


class UploadValidationError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.user_message = message


@dataclass(frozen=True)
class UploadRecords:
    artifact: Artifact
    version: ArtifactVersion
    job: Job
    created: bool


def _safe_filename(filename: str) -> str:
    safe_name = filename.replace("\\", "/").rsplit("/", maxsplit=1)[-1].strip()
    if not safe_name or safe_name in {".", ".."}:
        raise UploadValidationError("VALIDATION_FILENAME", "A valid filename is required.")
    return safe_name[:255]


def _format_from_filename(filename: str) -> str:
    suffix = "." + filename.lower().rsplit(".", maxsplit=1)[-1] if "." in filename else ""
    try:
        return SUPPORTED_EXTENSIONS[suffix]
    except KeyError as exc:
        raise UploadValidationError(
            "VALIDATION_UNSUPPORTED_FORMAT", "Only STEP, STP, and STL files are supported."
        ) from exc


def _validate_signature(upload: UploadedFile, cad_format: str) -> None:
    upload.seek(0)
    header = upload.read(4096)
    upload.seek(0)

    if cad_format == "step" and b"ISO-10303-21" not in header.upper():
        raise UploadValidationError(
            "VALIDATION_FILE_SIGNATURE", "The file content is not a valid STEP signature."
        )

    if cad_format == "stl":
        ascii_stl = header.lstrip().lower().startswith(b"solid") and b"facet" in header.lower()
        binary_stl = False
        if upload.size >= 84 and len(header) >= 84:
            triangle_count = struct.unpack("<I", header[80:84])[0]
            binary_stl = upload.size == 84 + (triangle_count * 50)
        if not ascii_stl and not binary_stl:
            raise UploadValidationError(
                "VALIDATION_FILE_SIGNATURE", "The file content is not a valid STL signature."
            )


def _hash_and_screen(upload: UploadedFile) -> str:
    digest = hashlib.sha256()
    marker_tail = b""
    upload.seek(0)
    for chunk in upload.chunks():
        digest.update(chunk)
        scan_window = marker_tail + chunk
        if EICAR_MARKER in scan_window:
            upload.seek(0)
            raise UploadValidationError(
                "VALIDATION_MALWARE_TEST_SIGNATURE",
                "The upload contains a malware test signature and was rejected.",
            )
        marker_tail = scan_window[-(len(EICAR_MARKER) - 1) :]
    upload.seek(0)
    return digest.hexdigest()


def validate_upload(upload: UploadedFile) -> tuple[str, str, str]:
    if upload.size <= 0:
        raise UploadValidationError("VALIDATION_EMPTY_FILE", "The uploaded file is empty.")
    if upload.size > settings.MAX_CAD_UPLOAD_BYTES:
        max_mb = settings.MAX_CAD_UPLOAD_BYTES // (1024 * 1024)
        raise UploadValidationError(
            "VALIDATION_FILE_TOO_LARGE", f"The CAD file exceeds the {max_mb} MB limit."
        )

    filename = _safe_filename(upload.name)
    cad_format = _format_from_filename(filename)
    _validate_signature(upload, cad_format)
    sha256 = _hash_and_screen(upload)
    return filename, cad_format, sha256


def create_upload_records(
    upload: UploadedFile,
    *,
    artifact_name: str = "",
    dataset_id: str = "public-demo-v1",
    product_type: str = "",
    material_code: str = "",
    idempotency_key: str | None = None,
    source_system: str = "upload",
    source_context: dict[str, object] | None = None,
    mold_revision_id: str | None = None,
) -> UploadRecords:
    normalized_key = idempotency_key.strip() if idempotency_key else None
    if normalized_key:
        existing_job = (
            Job.objects.select_related("input_artifact_version__artifact")
            .filter(idempotency_key=normalized_key)
            .first()
        )
        if existing_job:
            version = existing_job.input_artifact_version
            return UploadRecords(version.artifact, version, existing_job, created=False)

    filename, cad_format, sha256 = validate_upload(upload)
    mold_revision = None
    if mold_revision_id:
        mold_revision = MoldRevision.objects.filter(id=mold_revision_id).first()
        if mold_revision is None:
            raise UploadValidationError(
                "VALIDATION_MOLD_REVISION", "The selected mold revision does not exist."
            )
    artifact_id = uuid.uuid4()
    version_id = uuid.uuid4()
    storage_key = f"source/{artifact_id}/{version_id}/source.{cad_format}"
    stored = False

    try:
        with transaction.atomic():
            artifact = Artifact.objects.create(
                id=artifact_id,
                name=(artifact_name.strip() or filename)[:255],
                kind=Artifact.Kind.CAD_SOURCE,
                classification="public_demo",
                dataset_id=(dataset_id.strip() or "public-demo-v1")[:128],
                product_type=product_type.strip()[:128],
                material_code=material_code.strip()[:128],
                mold_revision=mold_revision,
                quality_status="validated",
            )
            version = ArtifactVersion.objects.create(
                id=version_id,
                artifact=artifact,
                version_number=1,
                original_filename=filename,
                media_type=MEDIA_TYPES[cad_format],
                format=cad_format,
                size_bytes=upload.size,
                sha256=sha256,
                storage_key=storage_key,
                source_system=(source_system.strip() or "upload")[:128],
                classification=artifact.classification,
                malware_status=ArtifactVersion.MalwareStatus.BASIC_SCREENED,
            )
            CADModel.objects.create(artifact_version=version, cad_format=cad_format)
            job = Job.objects.create(
                capability_id="cad.parse",
                capability_version="1.0.0",
                state=Job.State.QUEUED,
                queue="cad",
                resource_class="cad",
                input_artifact_version=version,
                input_snapshot={
                    "schema_version": "1.0",
                    "artifact_version_id": str(version.id),
                    "sha256": version.sha256,
                    "format": version.format,
                    "source": source_context or {"type": "manual_upload"},
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
            saved_key = default_storage.save(storage_key, upload)
            stored = True
            if saved_key != storage_key:
                raise RuntimeError("The deterministic artifact storage key already exists.")
    except Exception:
        if stored:
            default_storage.delete(storage_key)
        raise

    return UploadRecords(artifact, version, job, created=True)
