import hashlib
import io
import math
import re
import uuid
import zipfile
from dataclasses import dataclass
from datetime import date
from xml.etree import ElementTree

from django.conf import settings
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.utils import timezone
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from .models import (
    Artifact,
    ArtifactVersion,
    Job,
    JobEvent,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeSearch,
)
from .vector_store import query_named_vectors, upsert_named_vector

KNOWLEDGE_CAPABILITY_ID = "knowledge.ingest"
KNOWLEDGE_CAPABILITY_VERSION = "1.0.0"
EMBEDDING_MODEL = "feature-hash-demo@1.0.0"
EMBEDDING_DIMENSION = 64
PARSER_VERSION = "secure-document@2.0.0"
CHUNKER_VERSION = "section-paragraph@1.0.0"
PUBLIC_DEMO_SCOPES = ["public-demo"]
PUBLIC_KNOWLEDGE_DATASET = "public-knowledge-demo-v1"
AUTOMATED_SMOKE_DATASET = "automated-smoke-v1"
KNOWLEDGE_DATASETS = {PUBLIC_KNOWLEDGE_DATASET, AUTOMATED_SMOKE_DATASET}
DOCUMENT_TYPES = {"demo_sop", "design_guideline", "trial_report", "case_note"}
AUTHORITY_LEVELS = {"demo", "reviewed_demo"}
SUPPORTED_EXTENSIONS = {
    ".txt": ("txt", "text/plain"),
    ".md": ("md", "text/markdown"),
    ".pdf": ("pdf", "application/pdf"),
    ".docx": (
        "docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ),
}
EICAR_MARKER = b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE"
TOKEN_PATTERN = re.compile(r"[^\W_]+", re.UNICODE)
CJK_RUN_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+")
INJECTION_PATTERNS = {
    "IGNORE_POLICY_INSTRUCTION": re.compile(
        r"\b(ignore|disregard|override)\b.{0,40}\b(previous|system|developer|policy|instructions?)\b",
        re.IGNORECASE | re.DOTALL,
    ),
    "ROLE_IMPERSONATION": re.compile(
        r"^\s*(system|assistant|developer)\s*:", re.IGNORECASE | re.MULTILINE
    ),
    "PROMPT_DISCLOSURE_REQUEST": re.compile(
        r"\b(reveal|print|show|expose)\b.{0,30}\b(system prompt|hidden instructions?)\b",
        re.IGNORECASE,
    ),
    "HIDDEN_MARKUP": re.compile(r"<!--.*?-->", re.DOTALL),
    "BIDI_CONTROL": re.compile("[\u202a-\u202e\u2066-\u2069]"),
}


class KnowledgeValidationError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.user_message = message


@dataclass(frozen=True)
class KnowledgeUploadRecords:
    artifact: Artifact
    version: ArtifactVersion
    document: KnowledgeDocument
    job: Job
    created: bool


def _safe_filename(filename: str) -> str:
    safe = filename.replace("\\", "/").rsplit("/", maxsplit=1)[-1].strip()
    if not safe or safe in {".", ".."}:
        raise KnowledgeValidationError("VALIDATION_FILENAME", "A valid filename is required.")
    return safe[:255]


def _hash_and_screen(upload: UploadedFile) -> str:
    digest = hashlib.sha256()
    marker_tail = b""
    upload.seek(0)
    for chunk in upload.chunks():
        digest.update(chunk)
        scan_window = marker_tail + chunk
        if EICAR_MARKER in scan_window:
            upload.seek(0)
            raise KnowledgeValidationError(
                "VALIDATION_MALWARE_TEST_SIGNATURE",
                "The upload contains a malware test signature and was rejected.",
            )
        marker_tail = scan_window[-(len(EICAR_MARKER) - 1) :]
    upload.seek(0)
    return digest.hexdigest()


def _extract_pdf(data: bytes) -> str:
    if not data.startswith(b"%PDF-"):
        raise KnowledgeValidationError("VALIDATION_SIGNATURE", "PDF signature is invalid.")
    try:
        reader = PdfReader(io.BytesIO(data), strict=True)
        if reader.is_encrypted:
            raise KnowledgeValidationError(
                "VALIDATION_PDF_ENCRYPTED", "Encrypted PDF files are not accepted."
            )
        root = reader.trailer.get("/Root", {})
        names = root.get("/Names", {}) if hasattr(root, "get") else {}
        if any(key in root for key in ("/OpenAction", "/AA")) or any(
            key in names for key in ("/JavaScript", "/EmbeddedFiles")
        ):
            raise KnowledgeValidationError(
                "VALIDATION_PDF_ACTIVE_CONTENT", "PDF active or embedded content is not accepted."
            )
        if len(reader.pages) > 200:
            raise KnowledgeValidationError(
                "VALIDATION_DOCUMENT_COMPLEXITY", "PDF files may contain at most 200 pages."
            )
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)
    except KnowledgeValidationError:
        raise
    except (PdfReadError, ValueError, TypeError) as exc:
        raise KnowledgeValidationError(
            "VALIDATION_PDF_PARSE", "The PDF is not safely readable."
        ) from exc


def _extract_docx(data: bytes) -> str:
    if not data.startswith(b"PK"):
        raise KnowledgeValidationError("VALIDATION_SIGNATURE", "DOCX signature is invalid.")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if len(entries) > 1_000 or sum(item.file_size for item in entries) > 25 * 1024 * 1024:
                raise KnowledgeValidationError(
                    "VALIDATION_ARCHIVE_BOMB", "The DOCX container exceeds safe complexity limits."
                )
            for item in entries:
                if item.file_size > max(item.compress_size, 1) * 100:
                    raise KnowledgeValidationError(
                        "VALIDATION_ARCHIVE_BOMB", "The DOCX compression ratio is unsafe."
                    )
                name = item.filename.lower()
                if "vbaproject.bin" in name:
                    raise KnowledgeValidationError(
                        "VALIDATION_DOCX_MACRO", "Macro-enabled Office content is not accepted."
                    )
                if name.endswith(".rels") and b'TargetMode="External"' in archive.read(item):
                    raise KnowledgeValidationError(
                        "VALIDATION_DOCX_EXTERNAL_LINK",
                        "External DOCX relationships are not accepted.",
                    )
            document = archive.read("word/document.xml")
    except KnowledgeValidationError:
        raise
    except (zipfile.BadZipFile, KeyError, OSError) as exc:
        raise KnowledgeValidationError(
            "VALIDATION_DOCX_PARSE", "The DOCX is not safely readable."
        ) from exc
    try:
        root = ElementTree.fromstring(document)
    except ElementTree.ParseError as exc:
        raise KnowledgeValidationError(
            "VALIDATION_DOCX_PARSE", "The DOCX document XML is invalid."
        ) from exc
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    paragraphs = []
    for paragraph in root.iter(f"{namespace}p"):
        text = "".join(node.text or "" for node in paragraph.iter(f"{namespace}t"))
        if text.strip():
            paragraphs.append(text.strip())
    return "\n\n".join(paragraphs)


def extract_knowledge_text(data: bytes, document_format: str) -> str:
    if document_format == "pdf":
        text = _extract_pdf(data)
    elif document_format == "docx":
        text = _extract_docx(data)
    else:
        try:
            text = data.decode("utf-8-sig", errors="strict")
        except UnicodeDecodeError as exc:
            raise KnowledgeValidationError(
                "VALIDATION_TEXT_ENCODING", "Knowledge files must use UTF-8 encoding."
            ) from exc
    if not text.strip():
        raise KnowledgeValidationError(
            "RAG_NO_TEXT", "No indexable text was found in the document."
        )
    return text


def validate_knowledge_upload(upload: UploadedFile) -> tuple[str, str, str, str]:
    if upload.size <= 0:
        raise KnowledgeValidationError("VALIDATION_EMPTY_FILE", "The uploaded file is empty.")
    if upload.size > settings.MAX_KNOWLEDGE_UPLOAD_BYTES:
        max_mb = settings.MAX_KNOWLEDGE_UPLOAD_BYTES // (1024 * 1024)
        raise KnowledgeValidationError(
            "VALIDATION_FILE_TOO_LARGE", f"The knowledge file exceeds the {max_mb} MB limit."
        )
    filename = _safe_filename(upload.name)
    suffix = "." + filename.lower().rsplit(".", maxsplit=1)[-1] if "." in filename else ""
    try:
        document_format, media_type = SUPPORTED_EXTENSIONS[suffix]
    except KeyError as exc:
        raise KnowledgeValidationError(
            "VALIDATION_UNSUPPORTED_FORMAT",
            "Only TXT, Markdown, PDF, and DOCX knowledge files are supported.",
        ) from exc
    sha256 = _hash_and_screen(upload)
    upload.seek(0)
    extract_knowledge_text(upload.read(), document_format)
    upload.seek(0)
    return filename, document_format, media_type, sha256


def create_knowledge_upload_records(
    upload: UploadedFile,
    *,
    title: str,
    document_type: str,
    authority_level: str,
    owner: str,
    language: str,
    effective_from: date | None,
    effective_to: date | None,
    idempotency_key: str | None,
    dataset_id: str = PUBLIC_KNOWLEDGE_DATASET,
    publication_status: str = "published",
    document_key: str | None = None,
    supersedes_document_id: str | None = None,
) -> KnowledgeUploadRecords:
    normalized_key = idempotency_key.strip() if idempotency_key else None
    if normalized_key:
        existing_job = (
            Job.objects.select_related(
                "input_artifact_version__artifact",
                "input_artifact_version__knowledge_document",
            )
            .filter(idempotency_key=normalized_key)
            .first()
        )
        if existing_job:
            if existing_job.capability_id != KNOWLEDGE_CAPABILITY_ID:
                raise KnowledgeValidationError(
                    "CONFLICT_IDEMPOTENCY_KEY",
                    "The idempotency key is already used by another capability.",
                )
            version = existing_job.input_artifact_version
            return KnowledgeUploadRecords(
                version.artifact, version, version.knowledge_document, existing_job, False
            )

    if document_type not in DOCUMENT_TYPES:
        raise KnowledgeValidationError(
            "VALIDATION_DOCUMENT_TYPE", "Unsupported knowledge document type."
        )
    if authority_level not in AUTHORITY_LEVELS:
        raise KnowledgeValidationError("VALIDATION_AUTHORITY_LEVEL", "Unsupported authority level.")
    if dataset_id not in KNOWLEDGE_DATASETS:
        raise KnowledgeValidationError("VALIDATION_DATASET", "Unsupported knowledge dataset.")
    if language not in {"en", "zh-Hant"}:
        raise KnowledgeValidationError("VALIDATION_LANGUAGE", "language must be en or zh-Hant.")
    if effective_from and effective_to and effective_from > effective_to:
        raise KnowledgeValidationError(
            "VALIDATION_EFFECTIVE_DATE", "effective_from cannot be later than effective_to."
        )
    filename, document_format, media_type, sha256 = validate_knowledge_upload(upload)
    if publication_status not in {"draft", "published"}:
        raise KnowledgeValidationError(
            "VALIDATION_PUBLICATION_STATUS", "publication_status must be draft or published."
        )
    supersedes = None
    if supersedes_document_id:
        supersedes = KnowledgeDocument.objects.filter(id=supersedes_document_id).first()
        if supersedes is None:
            raise KnowledgeValidationError(
                "VALIDATION_SUPERSEDES", "The superseded knowledge document does not exist."
            )
    if ArtifactVersion.objects.filter(
        sha256=sha256, artifact__kind=Artifact.Kind.KNOWLEDGE_SOURCE
    ).exists():
        raise KnowledgeValidationError(
            "CONFLICT_DUPLICATE_DOCUMENT",
            "An identical knowledge document version already exists.",
        )

    artifact_id = uuid.uuid4()
    version_id = uuid.uuid4()
    storage_key = f"knowledge/{artifact_id}/{version_id}/source.{document_format}"
    stored = False
    try:
        with transaction.atomic():
            artifact = Artifact.objects.create(
                id=artifact_id,
                name=(title.strip() or filename)[:255],
                kind=Artifact.Kind.KNOWLEDGE_SOURCE,
                classification="public_demo",
                dataset_id=dataset_id,
            )
            version = ArtifactVersion.objects.create(
                id=version_id,
                artifact=artifact,
                version_number=1,
                original_filename=filename,
                media_type=media_type,
                format=document_format,
                size_bytes=upload.size,
                sha256=sha256,
                storage_key=storage_key,
                source_system=(
                    "automated-smoke"
                    if dataset_id == AUTOMATED_SMOKE_DATASET
                    else "public-demo-upload"
                ),
                classification="public_demo",
                malware_status=ArtifactVersion.MalwareStatus.BASIC_SCREENED,
            )
            document = KnowledgeDocument.objects.create(
                artifact_version=version,
                document_key=(
                    supersedes.document_key
                    if supersedes
                    else (document_key or str(uuid.uuid4()))[:128]
                ),
                version_number=supersedes.version_number + 1 if supersedes else 1,
                supersedes=supersedes,
                document_type=document_type,
                authority_level=authority_level,
                effective_from=effective_from,
                effective_to=effective_to,
                owner=(owner.strip() or "demo-knowledge-curator")[:128],
                classification="public_demo",
                acl_scopes=PUBLIC_DEMO_SCOPES,
                language=language,
                parser_version=PARSER_VERSION,
                chunker_version=CHUNKER_VERSION,
                publication_status=publication_status,
            )
            job = Job.objects.create(
                capability_id=KNOWLEDGE_CAPABILITY_ID,
                capability_version=KNOWLEDGE_CAPABILITY_VERSION,
                state=Job.State.QUEUED,
                queue="general",
                resource_class="text",
                input_artifact_version=version,
                input_snapshot={
                    "schema_version": "1.0",
                    "artifact_version_id": str(version.id),
                    "sha256": sha256,
                    "document_type": document_type,
                    "dataset_id": dataset_id,
                    "classification": "public_demo",
                    "acl_scopes": PUBLIC_DEMO_SCOPES,
                    "parser_version": PARSER_VERSION,
                    "chunker_version": CHUNKER_VERSION,
                    "embedding_model": EMBEDDING_MODEL,
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
                raise RuntimeError("The deterministic knowledge storage key already exists.")
    except Exception:
        if stored:
            default_storage.delete(storage_key)
        raise
    return KnowledgeUploadRecords(artifact, version, document, job, True)


def scan_untrusted_text(text: str) -> list[str]:
    return [code for code, pattern in INJECTION_PATTERNS.items() if pattern.search(text)]


def _tokens(text: str) -> list[str]:
    tokens: list[str] = []
    for raw_token in TOKEN_PATTERN.findall(text):
        token = raw_token.casefold()
        if len(token) > 1:
            tokens.append(token)
        for run in CJK_RUN_PATTERN.findall(token):
            tokens.extend(run[index : index + 2] for index in range(len(run) - 1))
    return tokens


def text_vector(text: str) -> list[float]:
    vector = [0.0] * EMBEDDING_DIMENSION
    for token in _tokens(text):
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        index = int.from_bytes(digest[:4], "big") % EMBEDDING_DIMENSION
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign
    magnitude = math.sqrt(sum(value * value for value in vector))
    if magnitude:
        vector = [round(value / magnitude, 10) for value in vector]
    return vector


def chunk_document(text: str, document_format: str) -> list[dict[str, object]]:
    section = "Document"
    paragraph_number = 0
    chunks: list[dict[str, object]] = []
    buffer: list[str] = []
    start_paragraph = 1

    def flush(end_paragraph: int | None = None) -> None:
        nonlocal buffer, start_paragraph
        if not buffer:
            return
        chunks.append(
            {
                "text": "\n\n".join(buffer),
                "locator": {
                    "page": None,
                    "section": section,
                    "paragraph_start": start_paragraph,
                    "paragraph_end": (
                        end_paragraph if end_paragraph is not None else paragraph_number
                    ),
                },
            }
        )
        buffer = []
        start_paragraph = (end_paragraph if end_paragraph is not None else paragraph_number) + 1

    blocks = re.split(r"\n\s*\n", text.strip())
    for raw_block in blocks:
        block = raw_block.strip()
        if not block:
            continue
        if document_format == "md" and re.fullmatch(r"#{1,6}\s+.+", block):
            flush()
            section = re.sub(r"^#{1,6}\s+", "", block).strip()[:255]
            start_paragraph = paragraph_number + 1
            continue
        paragraph_number += 1
        if len(block) > 900:
            flush(paragraph_number - 1)
            for character_start in range(0, len(block), 900):
                piece = block[character_start : character_start + 900]
                chunks.append(
                    {
                        "text": piece,
                        "locator": {
                            "page": None,
                            "section": section,
                            "paragraph_start": paragraph_number,
                            "paragraph_end": paragraph_number,
                            "character_start": character_start,
                            "character_end": character_start + len(piece),
                        },
                    }
                )
            start_paragraph = paragraph_number + 1
            continue
        if buffer and sum(len(item) for item in buffer) + len(block) > 900:
            flush(paragraph_number - 1)
            start_paragraph = paragraph_number
        buffer.append(block)
    flush()
    return chunks


def index_knowledge_document(document: KnowledgeDocument) -> dict[str, object]:
    with default_storage.open(document.artifact_version.storage_key, "rb") as source:
        text = extract_knowledge_text(source.read(), document.artifact_version.format)
    findings = scan_untrusted_text(text)
    if findings:
        document.ingestion_status = KnowledgeDocument.IngestionStatus.QUARANTINED
        document.injection_scan_status = "suspicious"
        document.injection_findings = findings
        document.error_code = "RAG_DOCUMENT_QUARANTINED"
        document.save()
        return {"status": "quarantined", "findings": findings, "chunk_count": 0}
    if document.effective_to and document.effective_to < timezone.localdate():
        document.ingestion_status = KnowledgeDocument.IngestionStatus.OBSOLETE
        document.injection_scan_status = "clear"
        document.error_code = ""
        document.save()
        return {"status": "obsolete", "findings": [], "chunk_count": 0}

    raw_chunks = chunk_document(text, document.artifact_version.format)
    if not raw_chunks:
        raise KnowledgeValidationError(
            "RAG_NO_TEXT", "No indexable text was found in the document."
        )
    with transaction.atomic():
        chunks = KnowledgeChunk.objects.bulk_create(
            [
                KnowledgeChunk(
                    document=document,
                    ordinal=ordinal,
                    text=str(item["text"]),
                    text_hash=hashlib.sha256(str(item["text"]).encode("utf-8")).hexdigest(),
                    locator=item["locator"],
                    embedding_model=EMBEDDING_MODEL,
                    embedding_dimension=EMBEDDING_DIMENSION,
                    embedding=text_vector(str(item["text"])),
                    language=document.language,
                    injection_scan_status="clear",
                )
                for ordinal, item in enumerate(raw_chunks, start=1)
            ]
        )
    for chunk in chunks:
        upsert_named_vector(
            collection_name=settings.QDRANT_KNOWLEDGE_COLLECTION,
            dimension=EMBEDDING_DIMENSION,
            point_id=str(chunk.id),
            vector=chunk.embedding,
            payload={
                "classification": document.classification,
                "acl_scopes": document.acl_scopes,
                "document_type": document.document_type,
                "authority_level": document.authority_level,
                "artifact_version_id": str(document.artifact_version_id),
                "dataset_id": document.artifact_version.artifact.dataset_id,
                "active": True,
            },
        )
        chunk.index_status = KnowledgeChunk.IndexStatus.INDEXED
        chunk.save(update_fields=["index_status"])
    document.ingestion_status = KnowledgeDocument.IngestionStatus.INDEXED
    document.injection_scan_status = "clear"
    document.injection_findings = []
    document.chunk_count = len(chunks)
    document.indexed_at = timezone.now()
    document.error_code = ""
    document.save()
    return {"status": "indexed", "findings": [], "chunk_count": len(chunks)}


def _lexical_score(query_tokens: set[str], text: str) -> float:
    text_tokens = set(_tokens(text))
    if not query_tokens or not text_tokens:
        return 0.0
    return len(query_tokens & text_tokens) / len(query_tokens)


def search_knowledge(
    query: str,
    *,
    top_k: int,
    document_types: list[str],
    authority_levels: list[str],
    dataset_ids: list[str] | None = None,
) -> KnowledgeSearch:
    query = query.strip()
    if not 2 <= len(query) <= 500:
        raise KnowledgeValidationError(
            "VALIDATION_KNOWLEDGE_QUERY", "query must contain between 2 and 500 characters."
        )
    query_tokens = set(_tokens(query))
    if not query_tokens:
        raise KnowledgeValidationError(
            "VALIDATION_KNOWLEDGE_QUERY",
            "query must contain at least one searchable term longer than one character.",
        )
    if not 1 <= top_k <= 10:
        raise KnowledgeValidationError("VALIDATION_TOP_K", "top_k must be between 1 and 10.")
    if set(document_types) - DOCUMENT_TYPES or set(authority_levels) - AUTHORITY_LEVELS:
        raise KnowledgeValidationError("VALIDATION_KNOWLEDGE_FILTER", "Unsupported filter value.")
    selected_datasets = dataset_ids or [PUBLIC_KNOWLEDGE_DATASET]
    if set(selected_datasets) - KNOWLEDGE_DATASETS:
        raise KnowledgeValidationError("VALIDATION_KNOWLEDGE_FILTER", "Unsupported dataset filter.")

    principal_scopes = PUBLIC_DEMO_SCOPES
    filters: dict[str, list[str] | str | bool] = {
        "classification": "public_demo",
        "acl_scopes": principal_scopes,
        "dataset_id": selected_datasets,
        "active": True,
    }
    if document_types:
        filters["document_type"] = document_types
    if authority_levels:
        filters["authority_level"] = authority_levels
    if not KnowledgeDocument.objects.filter(
        ingestion_status=KnowledgeDocument.IngestionStatus.INDEXED,
        publication_status="published",
        classification="public_demo",
        artifact_version__artifact__dataset_id__in=selected_datasets,
    ).exists():
        candidates = []
    else:
        candidates = query_named_vectors(
            collection_name=settings.QDRANT_KNOWLEDGE_COLLECTION,
            vector=text_vector(query),
            limit=max(20, top_k * 4),
            filters=filters,
        )
    coarse = {candidate.feature_set_id: candidate.coarse_score for candidate in candidates}
    chunks = KnowledgeChunk.objects.select_related("document__artifact_version__artifact").filter(
        id__in=coarse,
        document__ingestion_status=KnowledgeDocument.IngestionStatus.INDEXED,
        document__publication_status="published",
        document__artifact_version__artifact__dataset_id__in=selected_datasets,
    )
    ranked: list[tuple[float, KnowledgeChunk, dict[str, float]]] = []
    today = timezone.localdate()
    for chunk in chunks:
        document = chunk.document
        if not set(document.acl_scopes) & set(principal_scopes):
            continue
        if document.classification != "public_demo":
            continue
        if document.effective_from and document.effective_from > today:
            continue
        if document.effective_to and document.effective_to < today:
            continue
        lexical = _lexical_score(query_tokens, chunk.text)
        if lexical <= 0:
            continue
        vector_score = max(0.0, coarse[str(chunk.id)])
        authority = 0.9 if document.authority_level == "reviewed_demo" else 0.6
        freshness = 1.0
        score = 0.55 * lexical + 0.25 * vector_score + 0.15 * authority + 0.05 * freshness
        ranked.append(
            (
                score,
                chunk,
                {
                    "lexical": lexical,
                    "vector": vector_score,
                    "authority": authority,
                    "freshness": freshness,
                },
            )
        )
    ranked.sort(key=lambda item: (-item[0], item[1].ordinal, str(item[1].id)))
    selected = ranked[:top_k]
    results: list[dict[str, object]] = []
    citations: list[dict[str, object]] = []
    claims: list[dict[str, object]] = []
    for rank, (score, chunk, score_breakdown) in enumerate(selected, start=1):
        document = chunk.document
        locator = chunk.locator
        locator_text = (
            f"section:{locator.get('section')},paragraphs:"
            f"{locator.get('paragraph_start')}-{locator.get('paragraph_end')}"
        )
        citation_id = f"citation:{document.artifact_version_id}:{chunk.id}"
        excerpt = chunk.text[:500]
        citation = {
            "citation_id": citation_id,
            "artifact_version_id": str(document.artifact_version_id),
            "document_id": str(document.id),
            "title": document.artifact_version.artifact.name,
            "locator": locator_text,
            "authority": document.authority_level,
            "effective_from": document.effective_from.isoformat()
            if document.effective_from
            else None,
            "effective_to": document.effective_to.isoformat() if document.effective_to else None,
            "source_url": f"/api/v1/artifact-versions/{document.artifact_version_id}/download",
        }
        results.append(
            {
                "rank": rank,
                "chunk_id": str(chunk.id),
                "excerpt": excerpt,
                "score": round(score, 6),
                "score_breakdown": {key: round(value, 6) for key, value in score_breakdown.items()},
                "citation_id": citation_id,
            }
        )
        citations.append(citation)
        claims.append(
            {
                "text": excerpt,
                "evidence_refs": [citation_id],
                "evidence_type": "document_excerpt",
            }
        )
    abstained = not bool(results)
    result = {
        "schema_version": "1.0",
        "answer_mode": "extractive_evidence",
        "answer": (
            "Insufficient authorized evidence was found; no conclusion was generated."
            if abstained
            else f"Found {len(results)} authorized source passages. Review the cited excerpts."
        ),
        "claims": claims,
        "citations": citations,
        "results": results,
        "abstained": abstained,
        "retrieved_at": timezone.now().isoformat(),
        "principal_scope_source": "server_demo_policy",
        "limitations": [
            "Stage 5 uses deterministic feature hashing, not a learned semantic embedding model.",
            "Answers are extractive evidence summaries; LLM synthesis is not enabled.",
            "Knowledge retrieval is isolated from Process/Trial and CAE evidence lanes.",
        ],
    }
    return KnowledgeSearch.objects.create(
        query=query,
        principal_scopes=principal_scopes,
        filters={
            "document_types": document_types,
            "authority_levels": authority_levels,
            "dataset_ids": selected_datasets,
        },
        retrieval_config={
            "embedding_model": EMBEDDING_MODEL,
            "collection": settings.QDRANT_KNOWLEDGE_COLLECTION,
            "weights": {"lexical": 0.55, "vector": 0.25, "authority": 0.15, "freshness": 0.05},
            "top_k": top_k,
            "dataset_ids": selected_datasets,
        },
        result=result,
        abstained=abstained,
    )


def knowledge_document_payload(document: KnowledgeDocument) -> dict[str, object]:
    version = document.artifact_version
    return {
        "document_id": str(document.id),
        "document_key": document.document_key,
        "version_number": document.version_number,
        "supersedes_document_id": str(document.supersedes_id) if document.supersedes_id else None,
        "artifact_id": str(version.artifact_id),
        "artifact_version_id": str(version.id),
        "dataset_id": version.artifact.dataset_id,
        "title": version.artifact.name,
        "original_filename": version.original_filename,
        "format": version.format,
        "sha256": version.sha256,
        "document_type": document.document_type,
        "authority_level": document.authority_level,
        "effective_from": document.effective_from.isoformat() if document.effective_from else None,
        "effective_to": document.effective_to.isoformat() if document.effective_to else None,
        "owner": document.owner,
        "classification": document.classification,
        "acl_scopes": document.acl_scopes,
        "language": document.language,
        "parser_version": document.parser_version,
        "chunker_version": document.chunker_version,
        "ingestion_status": document.ingestion_status,
        "injection_scan_status": document.injection_scan_status,
        "injection_findings": document.injection_findings,
        "chunk_count": document.chunk_count,
        "indexed_at": document.indexed_at.isoformat() if document.indexed_at else None,
        "error_code": document.error_code or None,
        "publication_status": document.publication_status,
        "row_version": document.row_version,
        "submitted_by": document.submitted_by or None,
        "reviewed_by": document.reviewed_by or None,
        "approved_by": document.approved_by or None,
        "published_at": document.published_at.isoformat() if document.published_at else None,
        "retired_at": document.retired_at.isoformat() if document.retired_at else None,
        "download_url": f"/api/v1/artifact-versions/{version.id}/download",
        "created_at": document.created_at.isoformat(),
    }
