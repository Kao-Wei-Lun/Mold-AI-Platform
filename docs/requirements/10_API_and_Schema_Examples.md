# 10 — API、Capability、MCP 與 Schema 範例

本文件提供 wire-level 初稿；實作時轉為 OpenAPI 3.1、JSON Schema 與 MCP tool schema，並由 contract tests 驗證。範例中的 ID/URL 均為假資料。

## 1. Capability Descriptor

```json
{
  "capability_id": "mold.similarity_search",
  "version": "1.0.0",
  "status": "approved_demo",
  "owner": "cad-ai-team",
  "input_schema": "schema://capabilities/mold.similarity_search/input/1.0",
  "output_schema": "schema://capabilities/mold.similarity_search/output/1.0",
  "permissions": ["mold:read", "similarity:run"],
  "resource_class": "gpu",
  "execution": "async",
  "timeout_seconds": 600,
  "dependencies": {
    "similarity_profile": "demo-general@1.0",
    "geometry_extractor": "geom-features@1.2",
    "embedding_model": "cad-embedding-demo@1"
  },
  "evidence_required": true,
  "mcp_exposure": "enabled",
  "risk_level": "R1"
}
```

## 2. Create Similarity Job

`POST /api/v1/similarity-searches`

```json
{
  "schema_version": "1.0",
  "request_id": "1f113d3a-8c26-4de4-9422-43ceeb61d166",
  "idempotency_key": "ui-NEW-001-20260825-001",
  "query": {
    "cad_artifact_version_id": "d018a5ef-17a8-4625-a79d-07025e7e5aaf"
  },
  "profile": "demo-general@1.0",
  "filters": {
    "dataset_ids": ["public-demo-v1"],
    "product_types": ["housing"],
    "material_codes": ["PC_ABS"]
  },
  "top_k": 20,
  "detailed_compare_top_k": 10
}
```

`202 Accepted`

```json
{
  "schema_version": "1.0",
  "request_id": "1f113d3a-8c26-4de4-9422-43ceeb61d166",
  "status": "accepted",
  "job_id": "fda708af-f04b-40d3-9525-214321f02a75",
  "links": {
    "status": "/api/v1/jobs/fda708af-f04b-40d3-9525-214321f02a75",
    "ui": "/similarity/jobs/fda708af-f04b-40d3-9525-214321f02a75"
  }
}
```

## 3. Job Status

```json
{
  "job_id": "fda708af-f04b-40d3-9525-214321f02a75",
  "capability": "mold.similarity_search@1.0.0",
  "state": "running",
  "stage": "reranking",
  "progress": 65,
  "attempt": 1,
  "created_at": "2026-08-25T10:00:00+08:00",
  "started_at": "2026-08-25T10:00:02+08:00",
  "heartbeat_at": "2026-08-25T10:00:08+08:00",
  "warnings": []
}
```

Typed error：

```json
{
  "error": {
    "code": "CAD_PARSE_UNSUPPORTED_GEOMETRY",
    "message": "The selected CAD could not be converted to a valid solid.",
    "retryable": false,
    "details": {"quality_flags": ["OPEN_SHELL", "UNIT_UNCERTAIN"]},
    "correlation_id": "corr-..."
  }
}
```

## 4. Similarity Result

```json
{
  "search_id": "8c728920-a734-49a7-9807-b6364c4bff01",
  "query_ref": {
    "mold_case_id": "NEW-001",
    "cad_artifact_version_id": "d018a5ef-17a8-4625-a79d-07025e7e5aaf"
  },
  "profile": "demo-general@1.0",
  "index_version": "cad-demo-2026-08-25",
  "results": [
    {
      "rank": 1,
      "mold_case_id": "A123",
      "revision_id": "a123-r4",
      "overall_score": 0.928,
      "sub_scores": {
        "geometry": 0.962,
        "dimension": 0.941,
        "topology": 0.918,
        "visual": 0.884,
        "metadata": 1.0
      },
      "similarities": [
        {"type": "overall_dimensions", "evidence_ref": "measurement-set:..."}
      ],
      "differences": [
        {"type": "rib_count", "query": 12, "candidate": 8, "evidence_ref": "compare:..."}
      ],
      "quality_flags": [],
      "links": {"ui": "/molds/A123/compare?query=NEW-001"}
    }
  ],
  "lineage_ref": "lineage:sim-8c728920"
}
```

## 5. Design Review Request/Result

Request：

```json
{
  "cad_artifact_version_id": "d018a5ef-17a8-4625-a79d-07025e7e5aaf",
  "rule_profile": "housing-PCABS@2.1",
  "context": {
    "product_type": "housing",
    "material_code": "PC_ABS",
    "customer_scope": "demo"
  }
}
```

Violation：

```json
{
  "violation_id": "b24a6685-0791-44ba-a908-09f666fe7118",
  "result": "FAIL",
  "rule": {"id": "MOLD-DESIGN-023", "version": "2.1"},
  "severity": "major",
  "measurement": {
    "name": "rib_thickness",
    "actual": 1.55,
    "limit": 1.20,
    "unit": "mm",
    "tolerance": 0.02,
    "method": "local_thickness_v2"
  },
  "geometry_location": {
    "artifact_version_id": "d018a5ef-17a8-4625-a79d-07025e7e5aaf",
    "refs": ["face:235", "region:rib-7"]
  },
  "risk_codes": ["SINK_MARK"],
  "reference": {"artifact_version_id": "guideline-v8", "locator": "section:4.3"},
  "quality_flags": [],
  "explanation": {
    "source": "derived_narrative",
    "evidence_refs": ["measurement:...", "rule:MOLD-DESIGN-023@2.1"]
  }
}
```

## 6. Process Recommendation

```json
{
  "analysis_id": "tri-...",
  "root_cause_candidates": [
    {
      "code": "INSUFFICIENT_HOLDING_PRESSURE",
      "score": 0.78,
      "score_type": "model_association",
      "evidence_refs": ["trial-case:A028301", "rule:PROC-017@1.3"]
    }
  ],
  "recommendations": [
    {
      "step": 1,
      "parameter_code": "holding_pressure",
      "current": {"value": 85, "unit": "MPa"},
      "suggested_range": {"min": 90, "max": 93, "unit": "MPa"},
      "constraints": ["machine_max_pressure", "material_profile:PC_ABS@4"],
      "requires_engineer_approval": true,
      "do_not_auto_apply": true,
      "evidence_refs": ["trial-case:A028301"]
    }
  ],
  "uncertainties": ["No current CAE result is linked to this trial."],
  "lineage_ref": "lineage:tri-..."
}
```

## 7. Machine UI Extraction

```json
{
  "image_artifact_version_id": "hmi-image-...",
  "profile": "demo-generic-injection@1.0",
  "fields": [
    {
      "parameter_code": "injection_pressure",
      "label": "Injection Pressure",
      "raw_text": "120 MPa",
      "value": 120,
      "unit": "MPa",
      "confidence": 0.98,
      "region": {"x": 0.12, "y": 0.21, "w": 0.23, "h": 0.05},
      "validation": "valid",
      "review_status": "not_required"
    }
  ],
  "export_status": "ready_after_review",
  "lineage_ref": "lineage:hmi-..."
}
```

## 8. Knowledge Answer

```json
{
  "answer": "Rib thickness and holding pressure are the most frequently supported factors in the retrieved demo cases.",
  "claims": [
    {
      "text": "12 of 18 retrieved cases mention rib thickness.",
      "evidence_refs": ["case-query-result:..."],
      "evidence_type": "structured_case_aggregation"
    }
  ],
  "citations": [
    {
      "artifact_version_id": "trial-report-v3",
      "locator": "page:4,section:Corrective Action",
      "authority": "demo"
    }
  ],
  "uncertainties": [],
  "retrieved_at": "2026-08-25T10:05:00+08:00"
}
```

## 9. MCP Tool Schema Example

```json
{
  "name": "get_similarity_explanation",
  "title": "Explain a mold similarity result",
  "description": "Use after a completed similarity search when the user asks why a result ranked where it did.",
  "inputSchema": {
    "type": "object",
    "additionalProperties": false,
    "required": ["search_id", "candidate_mold_case_id"],
    "properties": {
      "search_id": {"type": "string", "format": "uuid"},
      "candidate_mold_case_id": {"type": "string", "minLength": 1}
    }
  },
  "annotations": {"readOnlyHint": true, "destructiveHint": false}
}
```

MCP response 應包含精簡文字、完整 structured content 及 UI deep link；不得傳回其他候選的未授權 metadata。

## 10. UI Action Examples

Highlight violation：

```json
{
  "protocol_version": "1.0",
  "action_id": "3cc573a8-38bf-4ed4-a3a2-a2ad86496ae0",
  "type": "viewer.highlight_geometry",
  "target": {
    "artifact_version_id": "d018a5ef-17a8-4625-a79d-07025e7e5aaf",
    "geometry_refs": ["face:235"]
  },
  "parameters": {"color": "warning", "fit": true},
  "preconditions": [{"type": "page", "equals": "design_review"}],
  "requires_confirmation": false,
  "expires_at": "2026-08-25T10:15:00+08:00",
  "evidence_refs": ["violation:b24a6685-0791-44ba-a908-09f666fe7118"]
}
```

Prepare export：

```json
{
  "protocol_version": "1.0",
  "action_id": "e49dc44e-f0dc-4c58-8520-b5ae749cecc2",
  "type": "export.prepare",
  "target": {"result_ref": "machine-ui-extraction:..."},
  "parameters": {"format": "xlsx"},
  "requires_confirmation": true,
  "confirmation": {
    "title": "Prepare Excel export",
    "effect": "Creates a new versioned export containing the reviewed fields."
  },
  "expires_at": "2026-08-25T10:15:00+08:00"
}
```

## 11. Audit Event Example

```json
{
  "event_id": "audit-uuid",
  "event_type": "mcp.tool_called.v1",
  "occurred_at": "2026-08-25T10:08:00+08:00",
  "actor": {"type": "user", "id": "user-uuid"},
  "client": "chatgpt_plugin",
  "action": "get_similarity_explanation",
  "target_refs": ["search:8c728920", "mold:A123"],
  "authorization": {"decision": "allow", "policy_version": "policy@7"},
  "result": "succeeded",
  "correlation_id": "corr-...",
  "data_classification": "public_demo",
  "payload_hash": "sha256:..."
}
```

## 12. Error Code Families

- `AUTH_*`：認證／token。
- `PERMISSION_*`：scope／policy；避免洩漏資源是否存在。
- `VALIDATION_*`：schema、unit、unsupported format。
- `CAD_*`, `CAE_*`, `OCR_*`, `RAG_*`：Domain failure。
- `JOB_*`：queue、timeout、cancel、dependency。
- `PROVIDER_*`：LLM/embedding/vision external provider。
- `CONFLICT_*`：version/idempotency/lifecycle。
- `INTERNAL_*`：非預期錯誤；只回 correlation ID，不回 stack trace。

每個錯誤定義 HTTP/MCP representation、retryable、user-safe message、operator detail、alert severity。
