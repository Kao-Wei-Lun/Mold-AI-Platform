import uuid

from django.core.exceptions import ValidationError
from django.db import models


class Artifact(models.Model):
    class Kind(models.TextChoices):
        CAD_SOURCE = "cad_source", "CAD source"
        CAD_PREVIEW = "cad_preview", "CAD preview"
        KNOWLEDGE_SOURCE = "knowledge_source", "Knowledge source"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    kind = models.CharField(max_length=32, choices=Kind.choices)
    classification = models.CharField(max_length=32, default="public_demo")
    dataset_id = models.CharField(max_length=128, default="public-demo-v1")
    product_type = models.CharField(max_length=128, blank=True)
    material_code = models.CharField(max_length=128, blank=True)
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
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    profile_key = models.CharField(max_length=128, unique=True)
    version = models.CharField(max_length=32)
    status = models.CharField(max_length=32, default="approved_demo")
    product_scope = models.JSONField(default=list)
    material_scope = models.JSONField(default=list)
    owner = models.CharField(max_length=128)
    approved_by = models.CharField(max_length=128)
    ruleset_checksum = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.profile_key


class RuleVersion(models.Model):
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


class KnowledgeDocument(models.Model):
    class IngestionStatus(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        INDEXED = "indexed", "Indexed"
        QUARANTINED = "quarantined", "Quarantined"
        FAILED = "failed", "Failed"
        OBSOLETE = "obsolete", "Obsolete"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

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
    created_at = models.DateTimeField(auto_now_add=True)

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
