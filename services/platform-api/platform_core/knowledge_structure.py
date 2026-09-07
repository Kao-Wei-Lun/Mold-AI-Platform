"""CPU-only structured document parsing and hierarchy-aware chunking.

The source bytes are assumed to have passed the security validation in
``platform_core.knowledge``.  This module never follows links, executes embedded
content, or performs network I/O.
"""

from __future__ import annotations

import hashlib
import io
import re
import zipfile
from dataclasses import dataclass
from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version
from typing import Any
from xml.etree import ElementTree

from pypdf import PdfReader

PARSER_VERSION = "structured-cpu@3.0.0"
DOCLING_PARSER_VERSION = "docling-native-cpu@2.126.0"
CHUNKER_VERSION = "hierarchical-semantic@2.0.0"
CHUNK_CONTRACT_VERSION = "2.0"
PROSE_LIMIT = 900
TABLE_LIMIT = 1_500
WORD_NAMESPACE = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


@dataclass(frozen=True)
class DocumentBlock:
    text: str
    content_type: str
    section_path: tuple[str, ...]
    paragraph_number: int
    page_no: int | None = None
    page_width: float | None = None
    page_height: float | None = None
    bbox: tuple[float, float, float, float] | None = None
    bbox_precision: str = "unavailable"
    source_start: int | None = None
    source_end: int | None = None


@dataclass(frozen=True)
class StructuredDocument:
    text: str
    blocks: tuple[DocumentBlock, ...]
    parser_version: str = PARSER_VERSION
    warnings: tuple[str, ...] = ()


def _section_ref(section_path: tuple[str, ...]) -> str:
    value = " > ".join(section_path) or "Document"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def validated_anchor(
    *,
    page_no: int | None,
    page_width: float | None,
    page_height: float | None,
    bbox: tuple[float, float, float, float] | None,
    bbox_precision: str,
) -> dict[str, object]:
    """Return a safe citation anchor, degrading invalid geometry to page-only."""
    valid_page = isinstance(page_no, int) and page_no > 0
    valid_size = (
        page_width is not None and page_height is not None and page_width > 0 and page_height > 0
    )
    valid_bbox = False
    normalized_bbox: list[float] | None = None
    if valid_page and valid_size and bbox is not None and len(bbox) == 4:
        x0, y0, x1, y1 = (float(value) for value in bbox)
        valid_bbox = 0 <= x0 < x1 <= page_width and 0 <= y0 < y1 <= page_height
        if valid_bbox:
            normalized_bbox = [round(x0, 3), round(y0, 3), round(x1, 3), round(y1, 3)]
    return {
        "page_no": page_no if valid_page else None,
        "page_size": (
            [round(float(page_width), 3), round(float(page_height), 3)] if valid_size else None
        ),
        "bbox": normalized_bbox,
        "bbox_available": valid_bbox,
        "bbox_precision": bbox_precision if valid_bbox else "unavailable",
        "coordinate_origin": "top-left",
        "coordinate_unit": "pt",
        "page_rotation": 0,
    }


def _text_blocks(text: str, *, markdown: bool) -> list[DocumentBlock]:
    blocks: list[DocumentBlock] = []
    headings: list[str] = []
    paragraph = 0
    source_cursor = 0
    raw_blocks = re.split(r"\n\s*\n", text.strip())
    for raw in raw_blocks:
        value = raw.strip()
        if not value:
            continue
        heading = re.fullmatch(r"(#{1,6})\s+(.+)", value) if markdown else None
        if heading:
            level = len(heading.group(1))
            headings = headings[: level - 1] + [heading.group(2).strip()[:255]]
            continue
        paragraph += 1
        start = text.find(value, source_cursor)
        if start < 0:
            start = source_cursor
        source_cursor = start + len(value)
        lines = [line.strip() for line in value.splitlines() if line.strip()]
        is_table = markdown and len(lines) >= 2 and all("|" in line for line in lines)
        blocks.append(
            DocumentBlock(
                text=value,
                content_type="table" if is_table else "prose",
                section_path=tuple(headings) or ("Document",),
                paragraph_number=paragraph,
                source_start=start,
                source_end=source_cursor,
            )
        )
    return blocks


def _docx_blocks(data: bytes) -> list[DocumentBlock]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        root = ElementTree.fromstring(archive.read("word/document.xml"))
    body = root.find(f"{WORD_NAMESPACE}body")
    if body is None:
        return []
    blocks: list[DocumentBlock] = []
    headings: list[str] = []
    paragraph = 0
    for child in body:
        if child.tag == f"{WORD_NAMESPACE}p":
            text = "".join(node.text or "" for node in child.iter(f"{WORD_NAMESPACE}t")).strip()
            if not text:
                continue
            style = child.find(f"{WORD_NAMESPACE}pPr/{WORD_NAMESPACE}pStyle")
            style_value = style.get(f"{WORD_NAMESPACE}val", "") if style is not None else ""
            heading_match = re.search(r"heading\s*([1-6])", style_value, re.IGNORECASE)
            if heading_match:
                level = int(heading_match.group(1))
                headings = headings[: level - 1] + [text[:255]]
                continue
            paragraph += 1
            blocks.append(DocumentBlock(text, "prose", tuple(headings) or ("Document",), paragraph))
        elif child.tag == f"{WORD_NAMESPACE}tbl":
            rows: list[list[str]] = []
            for row in child.findall(f"{WORD_NAMESPACE}tr"):
                cells = []
                for cell in row.findall(f"{WORD_NAMESPACE}tc"):
                    cell_text = " ".join(
                        node.text or "" for node in cell.iter(f"{WORD_NAMESPACE}t")
                    ).strip()
                    cells.append(cell_text.replace("|", "\\|"))
                if cells:
                    rows.append(cells)
            if rows:
                width = max(len(row) for row in rows)
                rows = [row + [""] * (width - len(row)) for row in rows]
                markdown = ["| " + " | ".join(rows[0]) + " |"]
                markdown.append("| " + " | ".join(["---"] * width) + " |")
                markdown.extend("| " + " | ".join(row) + " |" for row in rows[1:])
                paragraph += 1
                blocks.append(
                    DocumentBlock(
                        "\n".join(markdown),
                        "table",
                        tuple(headings) or ("Document",),
                        paragraph,
                    )
                )
    return blocks


def _pdf_blocks(data: bytes) -> tuple[list[DocumentBlock], list[str]]:
    reader = PdfReader(io.BytesIO(data), strict=True)
    blocks: list[DocumentBlock] = []
    warnings: list[str] = []
    paragraph = 0
    for page_index, page in enumerate(reader.pages, start=1):
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)
        fragments: list[tuple[str, tuple[float, float, float, float]]] = []

        def visitor(
            value: str,
            _cm: list[float],
            text_matrix: list[float],
            _font: dict[str, object] | None,
            font_size: float,
            *,
            current_page: int = page_index,
            current_width: float = width,
            current_height: float = height,
            current_fragments: list[tuple[str, tuple[float, float, float, float]]] = fragments,
        ) -> None:
            clean = value.strip()
            if not clean or len(text_matrix) < 6:
                return
            x = float(text_matrix[4])
            baseline = float(text_matrix[5])
            size = max(float(font_size), 1.0)
            candidate = (
                x,
                current_height - baseline - size,
                x + len(clean) * size * 0.55,
                current_height - baseline,
            )
            anchor = validated_anchor(
                page_no=current_page,
                page_width=current_width,
                page_height=current_height,
                bbox=candidate,
                bbox_precision="estimated-text-run",
            )
            if anchor["bbox_available"]:
                current_fragments.append(
                    (clean, tuple(anchor["bbox"]))  # type: ignore[arg-type]
                )

        page_text = page.extract_text(visitor_text=visitor) or ""
        page_paragraphs = [
            value.strip() for value in re.split(r"\n\s*\n|\n", page_text) if value.strip()
        ]
        if not page_paragraphs:
            warnings.append(f"PAGE_{page_index}_NO_EXTRACTABLE_TEXT")
            continue
        bbox = None
        if fragments:
            bbox = (
                min(item[1][0] for item in fragments),
                min(item[1][1] for item in fragments),
                max(item[1][2] for item in fragments),
                max(item[1][3] for item in fragments),
            )
        else:
            warnings.append(f"PAGE_{page_index}_BBOX_UNAVAILABLE")
        for value in page_paragraphs:
            paragraph += 1
            blocks.append(
                DocumentBlock(
                    value,
                    "prose",
                    (f"Page {page_index}",),
                    paragraph,
                    page_no=page_index,
                    page_width=width,
                    page_height=height,
                    bbox=bbox,
                    bbox_precision="estimated-text-run" if bbox else "unavailable",
                )
            )
    return blocks, warnings


def _docling_version() -> str:
    try:
        return version("docling-slim")
    except PackageNotFoundError:
        return "unavailable"


@lru_cache(maxsize=1)
def _docling_converter() -> Any:
    """Build the model-free converter once; URL inputs and model pipelines stay disabled."""
    from docling.datamodel.base_models import InputFormat
    from docling.document_converter import DocumentConverter, NativePdfFormatOption

    return DocumentConverter(
        allowed_formats=[InputFormat.PDF, InputFormat.DOCX, InputFormat.XLSX, InputFormat.MD],
        format_options={InputFormat.PDF: NativePdfFormatOption()},
    )


def _docling_bbox(
    provenance: Any, document: Any
) -> tuple[
    int | None,
    float | None,
    float | None,
    tuple[float, float, float, float] | None,
]:
    page_no = getattr(provenance, "page_no", None)
    if not isinstance(page_no, int) or page_no < 1:
        return None, None, None, None
    page = getattr(document, "pages", {}).get(page_no)
    size = getattr(page, "size", None)
    width = float(getattr(size, "width", 0.0) or 0.0) or None
    height = float(getattr(size, "height", 0.0) or 0.0) or None
    bbox = getattr(provenance, "bbox", None)
    if bbox is None or height is None:
        return page_no, width, height, None
    try:
        top_left = bbox.to_top_left_origin(page_height=height)
    except (AttributeError, TypeError, ValueError):
        top_left = bbox
    try:
        coordinates = tuple(float(getattr(top_left, field)) for field in ("l", "t", "r", "b"))
    except (AttributeError, TypeError, ValueError):
        return page_no, width, height, None
    anchor = validated_anchor(
        page_no=page_no,
        page_width=width,
        page_height=height,
        bbox=coordinates,
        bbox_precision="docling-native",
    )
    safe_bbox = anchor["bbox"]
    return page_no, width, height, tuple(safe_bbox) if isinstance(safe_bbox, list) else None


def _docling_blocks(
    data: bytes, document_format: str, max_pages: int
) -> tuple[str, list[DocumentBlock]]:
    from docling.datamodel.base_models import DocumentStream

    result = _docling_converter().convert(
        DocumentStream(name=f"knowledge-source.{document_format}", stream=io.BytesIO(data)),
        max_num_pages=max_pages,
        max_file_size=len(data),
    )
    document = result.document
    markdown = document.export_to_markdown()
    if document_format != "pdf":
        return markdown, _text_blocks(markdown, markdown=True)

    blocks: list[DocumentBlock] = []
    headings: list[str] = []
    paragraph = 0
    for item, level in document.iterate_items():
        raw_label = getattr(item, "label", "")
        label = str(getattr(raw_label, "value", raw_label))
        text = str(getattr(item, "text", "") or "").strip()
        if label in {"title", "section_header"} and text:
            heading_level = max(1, min(int(level or 1), 6))
            headings = headings[: heading_level - 1] + [text[:255]]
            continue
        if label == "table" or item.__class__.__name__ == "TableItem":
            try:
                text = str(item.export_to_markdown(document) or "").strip()
            except (AttributeError, TypeError, ValueError):
                text = ""
            content_type = "table"
        else:
            content_type = "prose"
        if not text:
            continue
        paragraph += 1
        provenance = next(iter(getattr(item, "prov", []) or []), None)
        page_no, width, height, bbox = (
            _docling_bbox(provenance, document)
            if provenance is not None
            else (None, None, None, None)
        )
        blocks.append(
            DocumentBlock(
                text=text,
                content_type=content_type,
                section_path=tuple(headings)
                or ((f"Page {page_no}",) if page_no else ("Document",)),
                paragraph_number=paragraph,
                page_no=page_no,
                page_width=width,
                page_height=height,
                bbox=bbox,
                bbox_precision="docling-native" if bbox else "unavailable",
            )
        )
    return markdown, blocks


def parse_structured_document(
    data: bytes,
    document_format: str,
    plain_text: str,
    *,
    prefer_docling: bool = True,
    docling_required: bool = False,
    max_pages: int = 200,
) -> StructuredDocument:
    warnings: list[str] = []
    if prefer_docling and document_format in {"pdf", "docx", "xlsx", "md"}:
        try:
            parsed_text, blocks = _docling_blocks(data, document_format, max_pages)
            if blocks:
                return StructuredDocument(
                    text=parsed_text or plain_text,
                    blocks=tuple(blocks),
                    parser_version=f"docling-native-cpu@{_docling_version()}",
                )
            raise ValueError("Docling returned no indexable blocks.")
        except Exception as exc:  # Docling backends expose several typed parse failures.
            if docling_required:
                raise
            warnings.append(f"DOCLING_FALLBACK:{exc.__class__.__name__}")
    if document_format == "pdf":
        blocks, pdf_warnings = _pdf_blocks(data)
        warnings.extend(pdf_warnings)
    elif document_format == "docx":
        blocks = _docx_blocks(data)
    else:
        blocks = _text_blocks(plain_text, markdown=document_format in {"md", "xlsx"})
    return StructuredDocument(
        text=plain_text,
        blocks=tuple(blocks),
        warnings=tuple(warnings),
    )


def _split_prose(text: str, limit: int = PROSE_LIMIT) -> list[tuple[str, int, int]]:
    if len(text) <= limit:
        return [(text, 0, len(text))]
    pieces: list[tuple[str, int, int]] = []
    cursor = 0
    while cursor < len(text):
        target = min(cursor + limit, len(text))
        end = target
        if target < len(text):
            candidates = [
                text.rfind(separator, cursor + limit // 2, target)
                for separator in ("。", ". ", "; ", "\n", " ")
            ]
            boundary = max(candidates)
            if boundary > cursor:
                end = boundary + 1
        value = text[cursor:end].strip()
        if value:
            pieces.append((value, cursor, end))
        cursor = max(end, cursor + 1)
    return pieces


def _table_pieces(text: str) -> list[tuple[str, int, int]]:
    if len(text) <= TABLE_LIMIT:
        return [(text, 0, len(text))]
    lines = text.splitlines()
    prefix = "\n".join(lines[:2])
    rows = lines[2:]
    pieces: list[tuple[str, int, int]] = []
    current: list[str] = []
    cursor = 0
    for row in rows:
        candidate = "\n".join([prefix, *current, row])
        if current and len(candidate) > TABLE_LIMIT:
            value = "\n".join([prefix, *current])
            pieces.append((value, cursor, cursor + len(value)))
            cursor += sum(len(item) + 1 for item in current)
            current = []
        current.append(row)
    if current:
        value = "\n".join([prefix, *current])
        pieces.append((value, cursor, cursor + len(value)))
    return pieces


def hierarchical_chunks(document: StructuredDocument) -> list[dict[str, object]]:
    chunks: list[dict[str, object]] = []
    for block in document.blocks:
        pieces = (
            _table_pieces(block.text) if block.content_type == "table" else _split_prose(block.text)
        )
        for text, local_start, local_end in pieces:
            anchor = validated_anchor(
                page_no=block.page_no,
                page_width=block.page_width,
                page_height=block.page_height,
                bbox=block.bbox,
                bbox_precision=block.bbox_precision,
            )
            section_path = list(block.section_path)
            locator = {
                "schema_version": CHUNK_CONTRACT_VERSION,
                "page": anchor["page_no"],
                "page_no": anchor["page_no"],
                "page_size": anchor["page_size"],
                "bbox": anchor["bbox"],
                "bbox_available": anchor["bbox_available"],
                "bbox_precision": anchor["bbox_precision"],
                "coordinate_origin": anchor["coordinate_origin"],
                "coordinate_unit": anchor["coordinate_unit"],
                "page_rotation": anchor["page_rotation"],
                "section": section_path[-1] if section_path else "Document",
                "section_path": section_path,
                "parent_ref": _section_ref(block.section_path),
                "paragraph_start": block.paragraph_number,
                "paragraph_end": block.paragraph_number,
                "source_start": (
                    block.source_start + local_start if block.source_start is not None else None
                ),
                "source_end": (
                    block.source_start + local_end if block.source_start is not None else None
                ),
                "content_type": block.content_type,
            }
            if len(pieces) > 1:
                locator["character_start"] = local_start
                locator["character_end"] = local_end
            chunks.append(
                {
                    "text": text,
                    "locator": locator,
                    "content_type": block.content_type,
                    "parent_ref": locator["parent_ref"],
                    "citation_anchor": anchor,
                    "parser_metadata": {
                        "parser_version": document.parser_version,
                        "chunker_version": CHUNKER_VERSION,
                        "warnings": list(document.warnings),
                    },
                }
            )
    return chunks
