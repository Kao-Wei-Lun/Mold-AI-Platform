import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Lower


class Project(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        ARCHIVED = "archived", "Archived"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    scope = models.ForeignKey("DataScope", related_name="projects", on_delete=models.PROTECT)
    code = models.CharField(max_length=128)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    classification = models.CharField(max_length=32, default="public_demo")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    row_version = models.PositiveIntegerField(default=1)
    created_by = models.CharField(max_length=128, default="system")
    updated_by = models.CharField(max_length=128, default="system")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["code"]
        constraints = [
            models.UniqueConstraint(fields=["scope", "code"], name="unique_project_scope_code")
        ]

    def __str__(self) -> str:
        return self.code


class ProductPart(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        ARCHIVED = "archived", "Archived"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, related_name="parts", on_delete=models.PROTECT)
    part_number = models.CharField(max_length=128)
    name = models.CharField(max_length=255)
    product_type = models.CharField(max_length=128, blank=True)
    material_code = models.CharField(max_length=128, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    row_version = models.PositiveIntegerField(default=1)
    created_by = models.CharField(max_length=128, default="system")
    updated_by = models.CharField(max_length=128, default="system")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["project__code", "part_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "part_number"], name="unique_project_part_number"
            )
        ]

    def __str__(self) -> str:
        return self.part_number


class Mold(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        RETIRED = "retired", "Retired"
        ARCHIVED = "archived", "Archived"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, related_name="molds", on_delete=models.PROTECT)
    product_part = models.ForeignKey(
        ProductPart, related_name="molds", null=True, blank=True, on_delete=models.PROTECT
    )
    mold_code = models.CharField(max_length=128)
    name = models.CharField(max_length=255)
    mold_type = models.CharField(max_length=64, default="injection")
    cavity_count = models.PositiveSmallIntegerField(default=1)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    row_version = models.PositiveIntegerField(default=1)
    created_by = models.CharField(max_length=128, default="system")
    updated_by = models.CharField(max_length=128, default="system")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["project__code", "mold_code"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "mold_code"], name="unique_project_mold_code"
            )
        ]

    def __str__(self) -> str:
        return self.mold_code


class MoldRevision(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        RELEASED = "released", "Released"
        SUPERSEDED = "superseded", "Superseded"
        ARCHIVED = "archived", "Archived"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    mold = models.ForeignKey(Mold, related_name="revisions", on_delete=models.PROTECT)
    revision_code = models.CharField(max_length=64)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    change_summary = models.TextField(blank=True)
    source_system = models.CharField(max_length=64, default="platform_demo")
    source_revision_id = models.CharField(max_length=128, blank=True)
    row_version = models.PositiveIntegerField(default=1)
    released_at = models.DateTimeField(null=True, blank=True)
    created_by = models.CharField(max_length=128, default="system")
    updated_by = models.CharField(max_length=128, default="system")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["mold__mold_code", "revision_code"]
        constraints = [
            models.UniqueConstraint(
                fields=["mold", "revision_code"], name="unique_mold_revision_code"
            )
        ]

    def __str__(self) -> str:
        return f"{self.mold.mold_code}@{self.revision_code}"


class Artifact(models.Model):
    class Kind(models.TextChoices):
        CAD_SOURCE = "cad_source", "CAD source"
        CAD_PREVIEW = "cad_preview", "CAD preview"
        KNOWLEDGE_SOURCE = "knowledge_source", "Knowledge source"
        HMI_SOURCE = "hmi_source", "HMI source image"
        HMI_EXPORT = "hmi_export", "HMI spreadsheet export"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    kind = models.CharField(max_length=32, choices=Kind.choices)
    classification = models.CharField(max_length=32, default="public_demo")
    dataset_id = models.CharField(max_length=128, default="public-demo-v1")
    product_type = models.CharField(max_length=128, blank=True)
    material_code = models.CharField(max_length=128, blank=True)
    mold_revision = models.ForeignKey(
        MoldRevision,
        related_name="artifacts",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
    )
    lifecycle_status = models.CharField(max_length=24, default="active")
    quality_status = models.CharField(max_length=24, default="pending")
    archive_reason = models.CharField(max_length=512, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    row_version = models.PositiveIntegerField(default=1)
    created_by = models.CharField(max_length=128, default="demo-user")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

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


class SimilarityProfile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    profile_key = models.CharField(max_length=128, unique=True)
    schema_version = models.CharField(max_length=32, default="1.0")
    weights = models.JSONField(default=dict)
    candidate_collection = models.CharField(max_length=128)
    index_version = models.CharField(max_length=128)
    status = models.CharField(max_length=32, default="approved_demo")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.profile_key


class FeatureSet(models.Model):
    class IndexStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        INDEXED = "indexed", "Indexed"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cad_model = models.ForeignKey(CADModel, related_name="feature_sets", on_delete=models.PROTECT)
    feature_type = models.CharField(max_length=64, default="cad_similarity")
    schema_version = models.CharField(max_length=32, default="1.0")
    extractor_name = models.CharField(max_length=128, default="deterministic-cad-features")
    extractor_version = models.CharField(max_length=32, default="1.0.0")
    features = models.JSONField(default=dict)
    vector = models.JSONField(default=list)
    vector_dimension = models.PositiveSmallIntegerField()
    metric = models.CharField(max_length=32, default="cosine")
    normalized = models.BooleanField(default=True)
    vector_checksum = models.CharField(max_length=64)
    index_collection = models.CharField(max_length=128)
    index_version = models.CharField(max_length=128)
    index_status = models.CharField(
        max_length=24, choices=IndexStatus.choices, default=IndexStatus.PENDING
    )
    index_error_code = models.CharField(max_length=128, blank=True)
    indexed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["cad_model", "feature_type", "schema_version", "extractor_version"],
                name="unique_cad_feature_set_version",
            )
        ]
        indexes = [
            models.Index(fields=["index_status", "created_at"], name="feature_index_status_idx")
        ]

    def __str__(self) -> str:
        return f"{self.cad_model_id}:{self.feature_type}@{self.schema_version}"


class SimilaritySearch(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job = models.OneToOneField(Job, related_name="similarity_search", on_delete=models.PROTECT)
    query_feature_set = models.ForeignKey(
        FeatureSet, related_name="query_searches", on_delete=models.PROTECT
    )
    profile = models.ForeignKey(
        SimilarityProfile, related_name="searches", on_delete=models.PROTECT
    )
    top_k = models.PositiveSmallIntegerField(default=10)
    filters = models.JSONField(default=dict)
    result = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Similarity search {self.id} [{self.job.state}]"


class RuleProfile(models.Model):
    class WorkflowStatus(models.TextChoices):
        DRAFT = "draft", "Draft"
        VALIDATED = "validated", "Validated"
        IN_REVIEW = "in_review", "In review"
        APPROVED = "approved", "Approved"
        PUBLISHED = "published", "Published"
        RETIRED = "retired", "Retired"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    profile_key = models.CharField(max_length=128)
    version = models.CharField(max_length=32)
    status = models.CharField(max_length=32, default="approved_demo")
    product_scope = models.JSONField(default=list)
    material_scope = models.JSONField(default=list)
    owner = models.CharField(max_length=128)
    approved_by = models.CharField(max_length=128)
    ruleset_checksum = models.CharField(max_length=64)
    workflow_status = models.CharField(
        max_length=16, choices=WorkflowStatus.choices, default=WorkflowStatus.PUBLISHED
    )
    change_summary = models.TextField(blank=True)
    row_version = models.PositiveIntegerField(default=1)
    submitted_by = models.CharField(max_length=128, blank=True)
    reviewed_by = models.CharField(max_length=128, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    retired_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["profile_key", "version"], name="unique_rule_profile_key_version"
            )
        ]

    def __str__(self) -> str:
        return self.profile_key


class RuleVersion(models.Model):
    IMMUTABLE_FIELDS = (
        "profile_id",
        "rule_id",
        "rule_version",
        "title",
        "description",
        "evaluator",
        "applicability",
        "parameters",
        "operator",
        "limit_value",
        "unit",
        "tolerance",
        "severity",
        "risk_type",
        "recommendation",
        "reference",
    )
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    profile = models.ForeignKey(RuleProfile, related_name="rules", on_delete=models.PROTECT)
    rule_id = models.CharField(max_length=64)
    rule_version = models.CharField(max_length=32)
    title = models.CharField(max_length=255)
    description = models.TextField()
    evaluator = models.CharField(max_length=64)
    applicability = models.JSONField(default=dict)
    parameters = models.JSONField(default=dict)
    operator = models.CharField(max_length=16)
    limit_value = models.FloatField(null=True, blank=True)
    unit = models.CharField(max_length=32)
    tolerance = models.FloatField(default=0)
    severity = models.CharField(max_length=16)
    risk_type = models.CharField(max_length=64)
    recommendation = models.TextField()
    reference = models.JSONField(default=dict)
    sort_order = models.PositiveSmallIntegerField(default=0)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "rule_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["profile", "rule_id", "rule_version"],
                name="unique_rule_profile_version",
            )
        ]

    def __str__(self) -> str:
        return f"{self.rule_id}@{self.rule_version}"

    def save(self, *args, **kwargs) -> None:
        if self.pk and RuleVersion.objects.filter(pk=self.pk).exists():
            persisted = RuleVersion.objects.select_related("profile").only(
                *self.IMMUTABLE_FIELDS, "profile__workflow_status"
            ).get(pk=self.pk)
            changed = [
                field
                for field in self.IMMUTABLE_FIELDS
                if getattr(persisted, field) != getattr(self, field)
            ]
            if changed and persisted.profile.workflow_status != RuleProfile.WorkflowStatus.DRAFT:
                raise ValidationError(
                    {"rule_version": f"Immutable fields cannot change: {', '.join(changed)}"}
                )
        super().save(*args, **kwargs)


class ReviewRun(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job = models.OneToOneField(Job, related_name="design_review", on_delete=models.PROTECT)
    cad_model = models.ForeignKey(CADModel, related_name="review_runs", on_delete=models.PROTECT)
    profile = models.ForeignKey(RuleProfile, related_name="review_runs", on_delete=models.PROTECT)
    context = models.JSONField(default=dict)
    input_snapshot = models.JSONField(default=dict)
    geometry_engine_version = models.CharField(max_length=128)
    review_status = models.CharField(max_length=24, choices=Status.choices, default=Status.QUEUED)
    result_summary = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Design review {self.id} [{self.review_status}]"


class ReviewFinding(models.Model):
    class Result(models.TextChoices):
        PASS = "PASS", "Pass"
        FAIL = "FAIL", "Fail"
        NOT_APPLICABLE = "NOT_APPLICABLE", "Not applicable"
        NOT_EVALUATED = "NOT_EVALUATED", "Not evaluated"
        ERROR = "ERROR", "Error"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    review_run = models.ForeignKey(ReviewRun, related_name="findings", on_delete=models.PROTECT)
    rule_version = models.ForeignKey(RuleVersion, related_name="findings", on_delete=models.PROTECT)
    result = models.CharField(max_length=24, choices=Result.choices)
    actual_value = models.FloatField(null=True, blank=True)
    limit_value = models.FloatField(null=True, blank=True)
    unit = models.CharField(max_length=32)
    severity = models.CharField(max_length=16)
    risk_type = models.CharField(max_length=64)
    geometry_location = models.JSONField(default=dict)
    evidence_refs = models.JSONField(default=list)
    quality_flags = models.JSONField(default=list)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["rule_version__sort_order", "rule_version__rule_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["review_run", "rule_version"], name="unique_review_finding"
            )
        ]

    def __str__(self) -> str:
        return f"{self.review_run_id}:{self.rule_version.rule_id}={self.result}"


class ReviewDecision(models.Model):
    class Decision(models.TextChoices):
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"
        WAIVED = "waived", "Waived"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    finding = models.ForeignKey(ReviewFinding, related_name="decisions", on_delete=models.PROTECT)
    decision = models.CharField(max_length=16, choices=Decision.choices)
    reason = models.TextField(blank=True)
    decided_by = models.CharField(max_length=128)
    approved_by = models.CharField(max_length=128, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.finding_id}:{self.decision}"


class AuditEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_type = models.CharField(max_length=128)
    actor_id = models.CharField(max_length=128)
    target_refs = models.JSONField(default=list)
    detail = models.JSONField(default=dict)
    payload_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.event_type}:{self.id}"


class AccountProfile(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"
        DISABLED = "disabled", "Disabled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        related_name="mold_ai_profile",
        on_delete=models.PROTECT,
    )
    display_name = models.CharField(max_length=150, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    locale = models.CharField(max_length=16, default="zh-TW")
    timezone = models.CharField(max_length=64, default="Asia/Taipei")
    row_version = models.PositiveIntegerField(default=1)
    disabled_at = models.DateTimeField(null=True, blank=True)
    disabled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="disabled_mold_ai_accounts",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
    )
    disable_reason = models.CharField(max_length=512, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user__username"]

    def __str__(self) -> str:
        return f"{self.user.username} ({self.id})"


class DataScope(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=128, unique=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    classification = models.CharField(max_length=32, default="public_demo")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["code"]

    def __str__(self) -> str:
        return self.code


class AccessRole(models.Model):
    code = models.CharField(max_length=64, primary_key=True)
    name = models.CharField(max_length=128)
    description = models.TextField(blank=True)
    permissions = models.JSONField(default=list)
    is_system = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["code"]

    def __str__(self) -> str:
        return self.code


class RoleAssignment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="mold_ai_role_assignments",
        on_delete=models.PROTECT,
    )
    role = models.ForeignKey(AccessRole, related_name="assignments", on_delete=models.PROTECT)
    data_scope = models.ForeignKey(DataScope, related_name="assignments", on_delete=models.PROTECT)
    valid_from = models.DateTimeField(null=True, blank=True)
    valid_to = models.DateTimeField(null=True, blank=True)
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="granted_mold_ai_roles",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
    )
    reason = models.CharField(max_length=512)
    created_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="revoked_mold_ai_roles",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
    )
    revoke_reason = models.CharField(max_length=512, blank=True)

    class Meta:
        ordering = ["user__username", "role_id", "data_scope__code"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "role", "data_scope"],
                condition=models.Q(revoked_at__isnull=True),
                name="unique_active_role_assignment",
            )
        ]

    def __str__(self) -> str:
        return f"{self.user.username}:{self.role_id}@{self.data_scope.code}"


class MasterDataItem(models.Model):
    class Kind(models.TextChoices):
        DATASET = "dataset", "Dataset"
        PRODUCT_TYPE = "product_type", "Product type"
        MATERIAL = "material", "Material"
        MACHINE = "machine", "Machine"
        DEFECT = "defect", "Defect"
        LOCATION = "location", "Location"
        UNIT = "unit", "Unit"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"
        ARCHIVED = "archived", "Archived"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=32, choices=Kind.choices)
    code = models.CharField(max_length=128)
    name_en = models.CharField(max_length=255)
    name_zh_tw = models.CharField(max_length=255)
    description_en = models.TextField(blank=True)
    description_zh_tw = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    sort_order = models.PositiveIntegerField(default=100)
    attributes = models.JSONField(default=dict, blank=True)
    aliases = models.JSONField(default=list, blank=True)
    source_system = models.CharField(max_length=64, default="platform_demo")
    source_refs = models.JSONField(default=list, blank=True)
    scope = models.ForeignKey(DataScope, related_name="master_data_items", on_delete=models.PROTECT)
    classification = models.CharField(max_length=32, default="public_demo")
    effective_from = models.DateField(null=True, blank=True)
    effective_to = models.DateField(null=True, blank=True)
    row_version = models.PositiveIntegerField(default=1)
    created_by = models.CharField(max_length=128)
    updated_by = models.CharField(max_length=128)
    archive_reason = models.CharField(max_length=512, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["kind", "sort_order", "code"]
        constraints = [
            models.UniqueConstraint(
                Lower("code"), "scope", "kind", name="unique_master_data_scope_kind_code"
            )
        ]
        indexes = [
            models.Index(fields=["scope", "kind", "status"], name="master_scope_kind_status_idx")
        ]

    def __str__(self) -> str:
        return f"{self.kind}:{self.code}"


class MasterDataMappingBacklog(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        MAPPED = "mapped", "Mapped"
        IGNORED = "ignored", "Ignored"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_domain = models.CharField(max_length=64)
    source_record_ref = models.CharField(max_length=128)
    field_name = models.CharField(max_length=64)
    raw_value = models.CharField(max_length=255)
    target_kind = models.CharField(max_length=32, choices=MasterDataItem.Kind.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    occurrence_count = models.PositiveIntegerField(default=1)
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-last_seen_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["source_domain", "field_name", "raw_value", "target_kind"],
                name="unique_pending_mapping_value",
            )
        ]

    def __str__(self) -> str:
        return f"{self.source_domain}:{self.field_name}={self.raw_value}"


class KnowledgeDocument(models.Model):
    class IngestionStatus(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        INDEXED = "indexed", "Indexed"
        QUARANTINED = "quarantined", "Quarantined"
        FAILED = "failed", "Failed"
        OBSOLETE = "obsolete", "Obsolete"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document_key = models.CharField(max_length=128, default=uuid.uuid4)
    version_number = models.PositiveIntegerField(default=1)
    supersedes = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        related_name="superseded_by",
        on_delete=models.PROTECT,
    )
    artifact_version = models.OneToOneField(
        ArtifactVersion, related_name="knowledge_document", on_delete=models.PROTECT
    )
    document_type = models.CharField(max_length=64)
    authority_level = models.CharField(max_length=32, default="demo")
    effective_from = models.DateField(null=True, blank=True)
    effective_to = models.DateField(null=True, blank=True)
    owner = models.CharField(max_length=128)
    classification = models.CharField(max_length=32, default="public_demo")
    acl_scopes = models.JSONField(default=list)
    language = models.CharField(max_length=16, default="en")
    parser_version = models.CharField(max_length=64, default="plain-text@1.0.0")
    chunker_version = models.CharField(max_length=64, default="section-paragraph@1.0.0")
    ingestion_status = models.CharField(
        max_length=24,
        choices=IngestionStatus.choices,
        default=IngestionStatus.QUEUED,
    )
    injection_scan_status = models.CharField(max_length=24, default="pending")
    injection_findings = models.JSONField(default=list)
    chunk_count = models.PositiveIntegerField(default=0)
    indexed_at = models.DateTimeField(null=True, blank=True)
    error_code = models.CharField(max_length=128, blank=True)
    publication_status = models.CharField(max_length=24, default="published")
    row_version = models.PositiveIntegerField(default=1)
    submitted_by = models.CharField(max_length=128, blank=True)
    reviewed_by = models.CharField(max_length=128, blank=True)
    approved_by = models.CharField(max_length=128, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    retired_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["document_key", "version_number"],
                name="unique_knowledge_document_version",
            )
        ]

    def __str__(self) -> str:
        return f"Knowledge {self.artifact_version_id} [{self.ingestion_status}]"


class KnowledgeChunk(models.Model):
    class IndexStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        INDEXED = "indexed", "Indexed"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(KnowledgeDocument, related_name="chunks", on_delete=models.PROTECT)
    ordinal = models.PositiveIntegerField()
    text = models.TextField()
    text_hash = models.CharField(max_length=64)
    locator = models.JSONField(default=dict)
    embedding_model = models.CharField(max_length=128, default="feature-hash-demo@1.0.0")
    embedding_dimension = models.PositiveSmallIntegerField(default=64)
    embedding = models.JSONField(default=list)
    language = models.CharField(max_length=16, default="en")
    injection_scan_status = models.CharField(max_length=24, default="clear")
    index_status = models.CharField(
        max_length=24, choices=IndexStatus.choices, default=IndexStatus.PENDING
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["ordinal"]
        constraints = [
            models.UniqueConstraint(
                fields=["document", "ordinal"], name="unique_knowledge_chunk_ordinal"
            )
        ]
        indexes = [models.Index(fields=["text_hash"], name="knowledge_text_hash_idx")]

    def __str__(self) -> str:
        return f"{self.document_id}:chunk:{self.ordinal}"


class KnowledgeSearch(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    query = models.TextField()
    principal_scopes = models.JSONField(default=list)
    filters = models.JSONField(default=dict)
    retrieval_config = models.JSONField(default=dict)
    result = models.JSONField(default=dict)
    abstained = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Knowledge search {self.id}"


class TrialCase(models.Model):
    class LifecycleStatus(models.TextChoices):
        DRAFT = "draft", "Draft"
        CLOSED = "closed", "Closed"
        REOPENED = "reopened", "Reopened"
        ARCHIVED = "archived", "Archived"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case_code = models.CharField(max_length=64, unique=True)
    connector_key = models.CharField(max_length=64)
    source_record_id = models.CharField(max_length=128)
    source_version = models.CharField(max_length=64)
    source_hash = models.CharField(max_length=64)
    mapping_version = models.CharField(max_length=64)
    classification = models.CharField(max_length=32, default="public_demo")
    acl_scopes = models.JSONField(default=list)
    mold_revision_ref = models.CharField(max_length=128)
    part_revision_ref = models.CharField(max_length=128)
    machine_code = models.CharField(max_length=64)
    material_code = models.CharField(max_length=64)
    material_lot = models.CharField(max_length=64, blank=True)
    product_type = models.CharField(max_length=128)
    operator_ref = models.CharField(max_length=128, default="synthetic-operator")
    purpose = models.CharField(max_length=255)
    outcome = models.CharField(max_length=64)
    started_at = models.DateTimeField()
    data_quality = models.JSONField(default=dict)
    lifecycle_status = models.CharField(
        max_length=16, choices=LifecycleStatus.choices, default=LifecycleStatus.CLOSED
    )
    row_version = models.PositiveIntegerField(default=1)
    closed_at = models.DateTimeField(null=True, blank=True)
    archive_reason = models.CharField(max_length=512, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["case_code"]
        constraints = [
            models.UniqueConstraint(
                fields=["connector_key", "source_record_id", "source_version"],
                name="unique_trial_source_version",
            )
        ]
        indexes = [
            models.Index(
                fields=["material_code", "machine_code"], name="trial_material_machine_idx"
            ),
        ]

    def __str__(self) -> str:
        return self.case_code


class TrialCorrectionRecord(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    trial = models.ForeignKey(TrialCase, related_name="corrections", on_delete=models.PROTECT)
    before_values = models.JSONField(default=dict)
    after_values = models.JSONField(default=dict)
    reason = models.CharField(max_length=512)
    corrected_by = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.trial_id}:correction:{self.id}"


class ProcessRun(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    trial = models.ForeignKey(TrialCase, related_name="runs", on_delete=models.PROTECT)
    run_number = models.PositiveSmallIntegerField()
    cycle_start = models.PositiveIntegerField(null=True, blank=True)
    cycle_end = models.PositiveIntegerField(null=True, blank=True)
    environment = models.JSONField(default=dict)
    result = models.CharField(max_length=64)
    data_quality = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["run_number"]
        constraints = [
            models.UniqueConstraint(fields=["trial", "run_number"], name="unique_trial_process_run")
        ]

    def __str__(self) -> str:
        return f"{self.trial.case_code}:run:{self.run_number}"


class ProcessParameter(models.Model):
    class ValueKind(models.TextChoices):
        SETPOINT = "setpoint", "Setpoint"
        ACTUAL = "actual", "Actual"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    process_run = models.ForeignKey(ProcessRun, related_name="parameters", on_delete=models.PROTECT)
    canonical_code = models.CharField(max_length=64)
    raw_name = models.CharField(max_length=128)
    value = models.FloatField()
    unit = models.CharField(max_length=32)
    value_kind = models.CharField(max_length=16, choices=ValueKind.choices)
    sampling_method = models.CharField(max_length=64)
    sampled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["canonical_code", "value_kind"]
        constraints = [
            models.UniqueConstraint(
                fields=["process_run", "canonical_code", "value_kind"],
                name="unique_run_parameter_kind",
            )
        ]

    def __str__(self) -> str:
        return f"{self.process_run_id}:{self.canonical_code}={self.value}{self.unit}"


class DefectObservation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    process_run = models.ForeignKey(ProcessRun, related_name="defects", on_delete=models.PROTECT)
    defect_code = models.CharField(max_length=64)
    severity = models.CharField(max_length=32)
    location = models.CharField(max_length=128)
    quantity_rate = models.FloatField(null=True, blank=True)
    quantity_unit = models.CharField(max_length=32, blank=True)
    inspection_method = models.CharField(max_length=128)
    evidence_refs = models.JSONField(default=list)

    class Meta:
        ordering = ["defect_code"]
        indexes = [models.Index(fields=["defect_code"], name="trial_defect_code_idx")]

    def __str__(self) -> str:
        return f"{self.process_run_id}:{self.defect_code}"


class CorrectiveAction(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    process_run = models.ForeignKey(ProcessRun, related_name="actions", on_delete=models.PROTECT)
    action_code = models.CharField(max_length=64)
    description = models.TextField()
    before_values = models.JSONField(default=dict)
    after_values = models.JSONField(default=dict)
    rationale_source = models.JSONField(default=dict)
    approved_by = models.CharField(max_length=128)
    executed = models.BooleanField(default=False)
    observed_outcome = models.JSONField(default=dict)
    expected_effect = models.TextField()
    stop_condition = models.TextField()
    evidence_refs = models.JSONField(default=list)

    class Meta:
        ordering = ["action_code"]
        constraints = [
            models.UniqueConstraint(
                fields=["process_run", "action_code"], name="unique_run_corrective_action"
            )
        ]

    def __str__(self) -> str:
        return f"{self.process_run_id}:{self.action_code}"


class ProcessCaseSearch(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request_snapshot = models.JSONField(default=dict)
    scoring_profile_version = models.CharField(max_length=64)
    result = models.JSONField(default=dict)
    abstained = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Process case search {self.id}"


class CAEStudy(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    study_code = models.CharField(max_length=64, unique=True)
    connector_key = models.CharField(max_length=64)
    integration_level = models.CharField(max_length=64)
    source_record_id = models.CharField(max_length=128)
    source_version = models.CharField(max_length=64)
    source_hash = models.CharField(max_length=64)
    mapping_version = models.CharField(max_length=64)
    solver_name = models.CharField(max_length=128)
    product_ref = models.CharField(max_length=128)
    mold_revision_ref = models.CharField(max_length=128)
    material_model_code = models.CharField(max_length=128)
    mesh_family = models.CharField(max_length=128)
    objective = models.TextField()
    owner = models.CharField(max_length=128)
    classification = models.CharField(max_length=32, default="public_demo")
    acl_scopes = models.JSONField(default=list)
    data_quality = models.JSONField(default=dict)
    lifecycle_status = models.CharField(max_length=16, default="active")
    row_version = models.PositiveIntegerField(default=1)
    archive_reason = models.CharField(max_length=512, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["study_code"]
        constraints = [
            models.UniqueConstraint(
                fields=["connector_key", "source_record_id", "source_version"],
                name="unique_cae_study_source_version",
            )
        ]

    def __str__(self) -> str:
        return self.study_code


class CAERun(models.Model):
    class Status(models.TextChoices):
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        INCOMPLETE = "incomplete", "Incomplete"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    study = models.ForeignKey(CAEStudy, related_name="runs", on_delete=models.PROTECT)
    run_code = models.CharField(max_length=64)
    solver_name = models.CharField(max_length=128)
    solver_version = models.CharField(max_length=64)
    mesh_artifact_ref = models.CharField(max_length=255)
    mesh_checksum = models.CharField(max_length=64)
    material_model_code = models.CharField(max_length=128)
    boundary_settings = models.JSONField(default=dict)
    process_settings = models.JSONField(default=dict)
    unit_system = models.CharField(max_length=32)
    status = models.CharField(max_length=24, choices=Status.choices)
    input_hash = models.CharField(max_length=64)
    data_quality = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["run_code"]
        constraints = [
            models.UniqueConstraint(fields=["study", "run_code"], name="unique_cae_study_run")
        ]

    def __str__(self) -> str:
        return f"{self.study.study_code}:{self.run_code}"


class CAEResult(models.Model):
    class ResultType(models.TextChoices):
        SCALAR = "scalar", "Scalar"
        REGION_COUNT = "region_count", "Region count"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run = models.ForeignKey(CAERun, related_name="results", on_delete=models.PROTECT)
    metric_code = models.CharField(max_length=128)
    result_type = models.CharField(max_length=32, choices=ResultType.choices)
    value = models.FloatField()
    unit = models.CharField(max_length=32)
    location = models.JSONField(default=dict)
    field_summary = models.JSONField(default=dict)
    quality_flags = models.JSONField(default=list)
    parser_name = models.CharField(max_length=128)
    parser_version = models.CharField(max_length=64)
    source_locator = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["metric_code"]
        constraints = [
            models.UniqueConstraint(fields=["run", "metric_code"], name="unique_cae_run_metric")
        ]
        indexes = [models.Index(fields=["metric_code"], name="cae_metric_code_idx")]

    def __str__(self) -> str:
        return f"{self.run_id}:{self.metric_code}"


class CAEComparison(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    baseline_run = models.ForeignKey(
        CAERun, related_name="baseline_comparisons", on_delete=models.PROTECT
    )
    candidate_run = models.ForeignKey(
        CAERun, related_name="candidate_comparisons", on_delete=models.PROTECT
    )
    compatibility_profile_version = models.CharField(max_length=64)
    request_snapshot = models.JSONField(default=dict)
    compatible = models.BooleanField(default=False)
    incompatibilities = models.JSONField(default=list)
    result = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"CAE comparison {self.id}"


class HMIExtraction(models.Model):
    class Status(models.TextChoices):
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    image_artifact_version = models.OneToOneField(
        ArtifactVersion, related_name="hmi_extraction", on_delete=models.PROTECT
    )
    profile_definition = models.ForeignKey(
        "HMIProfileVersion",
        related_name="extractions",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
    )
    profile_key = models.CharField(max_length=128)
    profile_version = models.CharField(max_length=32)
    extractor_version = models.CharField(max_length=64)
    status = models.CharField(max_length=24, choices=Status.choices)
    image_width = models.PositiveIntegerField()
    image_height = models.PositiveIntegerField()
    preprocessing = models.JSONField(default=dict)
    review_status = models.CharField(max_length=32, default="pending_review")
    error_code = models.CharField(max_length=128, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"HMI extraction {self.id} [{self.status}]"


class HMIExtractedField(models.Model):
    class ReviewStatus(models.TextChoices):
        NOT_REQUIRED = "not_required", "Not required"
        NEEDS_REVIEW = "needs_review", "Needs review"
        CONFIRMED = "confirmed", "Confirmed"
        CORRECTED = "corrected", "Corrected"
        REJECTED = "rejected", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    extraction = models.ForeignKey(HMIExtraction, related_name="fields", on_delete=models.PROTECT)
    parameter_code = models.CharField(max_length=64)
    display_label = models.CharField(max_length=128)
    raw_text = models.CharField(max_length=128, blank=True)
    normalized_value = models.FloatField(null=True, blank=True)
    unit = models.CharField(max_length=32)
    confidence = models.FloatField()
    source_region = models.JSONField(default=dict)
    validation_status = models.CharField(max_length=32)
    review_status = models.CharField(max_length=24, choices=ReviewStatus.choices)
    reviewer_value = models.FloatField(null=True, blank=True)
    reviewer_unit = models.CharField(max_length=32, blank=True)
    reviewed_by = models.CharField(max_length=128, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["parameter_code"]
        constraints = [
            models.UniqueConstraint(
                fields=["extraction", "parameter_code"], name="unique_hmi_extraction_field"
            )
        ]

    def __str__(self) -> str:
        return f"{self.extraction_id}:{self.parameter_code}"


class HMIProfileVersion(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        RETIRED = "retired", "Retired"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    profile_key = models.CharField(max_length=128)
    version = models.CharField(max_length=32)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    field_specs = models.JSONField(default=list)
    profile_checksum = models.CharField(max_length=64)
    change_summary = models.TextField(blank=True)
    created_by = models.CharField(max_length=128)
    published_by = models.CharField(max_length=128, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    row_version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["profile_key", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["profile_key", "version"], name="unique_hmi_profile_version"
            )
        ]

    def __str__(self) -> str:
        return f"{self.profile_key}@{self.version} [{self.status}]"


class HMICorrectionDecision(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    field = models.ForeignKey(
        HMIExtractedField, related_name="correction_decisions", on_delete=models.PROTECT
    )
    action = models.CharField(max_length=16)
    before_value = models.JSONField(default=dict)
    after_value = models.JSONField(default=dict)
    reason = models.CharField(max_length=512)
    decided_by = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.field_id}:{self.action}:{self.id}"


class HMIExport(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    extraction = models.ForeignKey(HMIExtraction, related_name="exports", on_delete=models.PROTECT)
    artifact_version = models.OneToOneField(
        ArtifactVersion, related_name="hmi_export", on_delete=models.PROTECT
    )
    template_version = models.CharField(max_length=64)
    reviewed_snapshot_hash = models.CharField(max_length=64)
    created_by = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"HMI export {self.id}"
