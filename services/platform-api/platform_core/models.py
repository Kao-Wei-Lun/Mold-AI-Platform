import uuid

from django.core.exceptions import ValidationError
from django.db import models


class Artifact(models.Model):
    class Kind(models.TextChoices):
        CAD_SOURCE = "cad_source", "CAD source"
        CAD_PREVIEW = "cad_preview", "CAD preview"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    kind = models.CharField(max_length=32, choices=Kind.choices)
    classification = models.CharField(max_length=32, default="public_demo")
    created_by = models.CharField(max_length=128, default="demo-user")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name} ({self.id})"


class ArtifactVersion(models.Model):
    class MalwareStatus(models.TextChoices):
        BASIC_SCREENED = "basic_screened", "Basic screening passed"
        NOT_SCANNED = "not_scanned", "Not scanned"

    IMMUTABLE_FIELDS = (
        "artifact_id",
        "version_number",
        "original_filename",
        "media_type",
        "format",
        "size_bytes",
        "sha256",
        "storage_key",
        "source_system",
        "classification",
        "malware_status",
        "supersedes_id",
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    artifact = models.ForeignKey(Artifact, related_name="versions", on_delete=models.PROTECT)
    version_number = models.PositiveIntegerField(default=1)
    original_filename = models.CharField(max_length=255)
    media_type = models.CharField(max_length=128)
    format = models.CharField(max_length=16)
    size_bytes = models.PositiveBigIntegerField()
    sha256 = models.CharField(max_length=64)
    storage_key = models.CharField(max_length=512, unique=True)
    source_system = models.CharField(max_length=64, default="upload")
    classification = models.CharField(max_length=32, default="public_demo")
    malware_status = models.CharField(
        max_length=32,
        choices=MalwareStatus.choices,
        default=MalwareStatus.NOT_SCANNED,
    )
    supersedes = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        related_name="superseded_by",
        on_delete=models.PROTECT,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["artifact", "version_number"], name="unique_artifact_version_number"
            )
        ]
        indexes = [models.Index(fields=["sha256"], name="artifact_sha256_idx")]

    def __str__(self) -> str:
        return f"{self.artifact_id}@{self.version_number}"

    def save(self, *args, **kwargs) -> None:
        if self.pk and ArtifactVersion.objects.filter(pk=self.pk).exists():
            persisted = ArtifactVersion.objects.only(*self.IMMUTABLE_FIELDS).get(pk=self.pk)
            changed = [
                field
                for field in self.IMMUTABLE_FIELDS
                if getattr(persisted, field) != getattr(self, field)
            ]
            if changed:
                raise ValidationError(
                    {"artifact_version": f"Immutable fields cannot change: {', '.join(changed)}"}
                )
        super().save(*args, **kwargs)


class Job(models.Model):
    class State(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        CANCEL_REQUESTED = "cancel_requested", "Cancel requested"
        CANCELLED = "cancelled", "Cancelled"
        EXPIRED = "expired", "Expired"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    capability_id = models.CharField(max_length=128)
    capability_version = models.CharField(max_length=32, default="1.0.0")
    state = models.CharField(max_length=24, choices=State.choices, default=State.QUEUED)
    priority = models.PositiveSmallIntegerField(default=5)
    resource_class = models.CharField(max_length=32, default="cad")
    queue = models.CharField(max_length=64, default="cad")
    attempt = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=1)
    input_artifact_version = models.ForeignKey(
        ArtifactVersion, related_name="input_jobs", on_delete=models.PROTECT
    )
    input_snapshot = models.JSONField(default=dict)
    result_ref = models.CharField(max_length=255, blank=True)
    progress = models.PositiveSmallIntegerField(default=0)
    stage = models.CharField(max_length=64, default="queued")
    error_code = models.CharField(max_length=128, blank=True)
    error_message = models.CharField(max_length=512, blank=True)
    correlation_id = models.UUIDField(default=uuid.uuid4, editable=False)
    idempotency_key = models.CharField(max_length=255, null=True, blank=True, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    heartbeat_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["state", "created_at"], name="job_state_created_idx")]

    def __str__(self) -> str:
        return f"{self.capability_id}:{self.id} [{self.state}]"


class JobEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job = models.ForeignKey(Job, related_name="events", on_delete=models.CASCADE)
    from_state = models.CharField(max_length=24, blank=True)
    to_state = models.CharField(max_length=24)
    stage = models.CharField(max_length=64)
    progress = models.PositiveSmallIntegerField()
    detail = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.job_id}: {self.from_state or 'created'} -> {self.to_state}"


class CADModel(models.Model):
    class GeometryStatus(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    artifact_version = models.OneToOneField(
        ArtifactVersion, related_name="cad_model", on_delete=models.PROTECT
    )
    cad_format = models.CharField(max_length=16)
    unit_system = models.CharField(max_length=32, default="unknown")
    parser_name = models.CharField(max_length=128, blank=True)
    parser_version = models.CharField(max_length=64, blank=True)
    geometry_status = models.CharField(
        max_length=24, choices=GeometryStatus.choices, default=GeometryStatus.QUEUED
    )
    bounding_box = models.JSONField(default=dict)
    volume = models.FloatField(null=True, blank=True)
    surface_area = models.FloatField(null=True, blank=True)
    face_count = models.PositiveIntegerField(null=True, blank=True)
    edge_count = models.PositiveIntegerField(null=True, blank=True)
    surface_type_histogram = models.JSONField(default=dict)
    quality_flags = models.JSONField(default=list)
    preview_artifact_version = models.ForeignKey(
        ArtifactVersion,
        null=True,
        blank=True,
        related_name="preview_for_cad_models",
        on_delete=models.PROTECT,
    )
    error_code = models.CharField(max_length=128, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"CAD {self.artifact_version_id} [{self.geometry_status}]"


class LineageEdge(models.Model):
    class Relationship(models.TextChoices):
        DERIVED_FROM = "derived_from", "Derived from"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    from_artifact_version = models.ForeignKey(
        ArtifactVersion, related_name="lineage_out", on_delete=models.PROTECT
    )
    to_artifact_version = models.ForeignKey(
        ArtifactVersion, related_name="lineage_in", on_delete=models.PROTECT
    )
    relationship = models.CharField(max_length=32, choices=Relationship.choices)
    job = models.ForeignKey(Job, related_name="lineage_edges", on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["from_artifact_version", "to_artifact_version", "relationship"],
                name="unique_lineage_edge",
            )
        ]

    def __str__(self) -> str:
        return f"{self.from_artifact_version_id} {self.relationship} {self.to_artifact_version_id}"
