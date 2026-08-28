# 04 — Canonical Data Model 與 Data Contract

完整 Web 資料管理、版本、狀態、匯入、封存及刪除政策另見
[11_Data_Management_SRS.md](11_Data_Management_SRS.md)；身分與授權實體見
[12_Identity_Access_Account_Management_SRS.md](12_Identity_Access_Account_Management_SRS.md)。

## 1. 目的

Canonical Model 是 Public Demo Data 與 Company Data 之間的穩定邊界。Connector 負責來源解析與 mapping；Capability 只依賴 Canonical Contract，不直接讀取 ABC、PDM、MES 或特定資料表。

## 2. 設計原則

- **CDM-001**：所有主實體使用平台 UUID；來源 ID 存於 `source_refs`，不得直接當跨系統主鍵。
- **CDM-002**：原始資料 immutable；正規化／衍生資料以新 artifact/version 表示。
- **CDM-003**：每個數值含 value、unit、method、quality、tolerance（適用時）與 source reference。
- **CDM-004**：時間同時保存 `event_time`、`ingested_at`、timezone/offset；未知時明確標示。
- **CDM-005**：Enum 與 schema 版本化；未知值保存 raw value 並進 mapping backlog。
- **CDM-006**：所有 entity/artifact 支援 classification、tenant/customer/project scope 與 policy tags。
- **CDM-007**：資料刪除、retention、legal hold 與 derived artifact 影響可追蹤。

## 3. 核心聚合

```text
MoldCase
├─ Project ─ Product ─ Part
├─ Mold ─ MoldRevision
├─ Drawing / CADModel / DerivedGeometry
├─ CAEStudy ─ CAERun ─ CAEResult
├─ Trial ─ ProcessRun ─ ProcessParameter
├─ Defect ─ RootCauseHypothesis ─ CorrectiveAction
├─ Quotation ─ CostBreakdown
├─ MaintenanceEvent ─ Component ─ ShotCounter
├─ KnowledgeDocument / KnowledgeChunk
├─ ReviewRun ─ Violation ─ Waiver
└─ ArtifactVersion / LineageEdge / AuditReference
```

## 4. 實體定義

### 4.1 MoldCase

跨模組搜尋與關聯的業務聚合，不等同單一檔案。

必要欄位：

- `mold_case_id`, `tenant_id`, `project_id`, `part_ids`, `mold_id`
- `case_type`, `product_type`, `lifecycle_status`
- `customer_scope`, `supplier_scope`, `classification`
- `effective_from`, `effective_to`, `source_refs`, `created_at`, `updated_at`

### 4.2 Artifact / ArtifactVersion

用於 CAD、Drawing、Image、PDF、CAE、Excel、Report、Mesh、Thumbnail、Embedding manifest。

- `artifact_id`：邏輯文件。
- `artifact_version_id`：immutable 內容版本。
- `media_type`, `format`, `size_bytes`, `sha256`, `storage_uri`
- `source_system`, `source_id`, `source_version`, `license/provenance`
- `classification`, `malware_status`, `parse_status`
- `created_by`, `created_at`, `supersedes_version_id`

Storage URI 不應直接暴露給 Client；由授權 download endpoint 發出短效存取。

### 4.3 CADModel / DerivedGeometry

- `cad_model_id`, `artifact_version_id`, `cad_format`, `unit_system`
- `kernel/parser_name`, `parser_version`, `geometry_status`
- `bbox`, `volume`, `surface_area`, `center_of_mass`
- `face_count`, `edge_count`, `surface_type_histogram`
- `mesh_artifact_version_id`, `multiview_artifact_ids`
- `geometry_feature_set_id`, `topology_feature_set_id`
- `quality_flags`: invalid topology、open shell、unit uncertain、tolerance issue 等。

Face/Edge reference 必須相對於特定 CAD artifact version，不得跨 revision 假設穩定。

### 4.4 FeatureSet / Embedding

- `feature_set_id`, `entity_ref`, `feature_type`, `schema_version`
- `extractor_name`, `extractor_version`, `parameters_hash`
- `vector_ref`, `dimension`, `metric`, `normalized`
- `index_name`, `index_version`, `created_at`
- `input_artifact_versions`, `quality_flags`

Embedding 不取代可解釋幾何欄位；兩者都須保存。

### 4.5 RuleProfile / RuleVersion

RuleProfile：`profile_id`, product/customer/material scope, version, status, effective dates, owner, approved_by。

RuleVersion：

- `rule_id`, `rule_version`, `title`, `description`
- `applicability_expression`, `measurement_definition`
- `condition_expression`, `limit`, `unit`, `tolerance`
- `severity`, `risk_type`, `recommendation_template`
- `reference_artifact_version_id`, `reference_location`
- `effective_from/to`, `owner`, `reviewer`, `approval_event_id`

規則表達式不得直接執行不受信任程式碼；採受限 DSL 或已註冊 evaluator。

### 4.6 ReviewRun / Violation / Waiver

ReviewRun 保存 `input_snapshot`、profile/rule versions、geometry engine version、status、started/completed time。

Violation：`violation_id`, `rule_ref`, result state, actual/limit/unit, severity, geometry_location, evidence artifact, quality/confidence, explanation reference。

Waiver：scope、reason、requested_by、approved_by、expiry、applies_to_revision、status。Waiver 是額外決策，不修改原始 violation。

### 4.7 SimilarityProfile / SimilarityResult

SimilarityProfile：產品線、feature lanes、weights、candidate index、reranker、normalization、filters、version、validation report。

SimilarityResult：

- query/candidate entity and revision refs
- overall score 與 geometry/topology/dimension/visual/metadata/manufacturing sub-scores
- rank、candidate generation score、rerank score
- major similarities/differences（含 evidence）
- profile/model/index versions、execution_id、created_at

分數僅在同一 Profile version 內可直接比較。

### 4.8 Trial / ProcessRun / Defect / Action

- Trial：mold/part/revision、machine、material lot、operator、time、purpose、outcome。
- ProcessRun：cycle/batch range、parameter set、environment、result、data quality。
- ProcessParameter：canonical parameter code、raw name、value、unit、setpoint/actual、sampling method/time。
- Defect：controlled defect code、severity、location、quantity/rate、image artifact、inspection method。
- CorrectiveAction：action code、before/after、rationale source、approval、execution、observed outcome。

### 4.9 CAEStudy / Run / Result

- Study：solver/product/mold/material/mesh family、objective、owner。
- Run：solver/version、mesh artifact、material model、boundary/process settings、status、input hash。
- Result：metric code、scalar/field/region type、value/unit、location、artifact、quality flag、parser version。

只有 compatibility rules 通過的 Run 才可計算 delta。

### 4.10 KnowledgeDocument / Chunk

- Document 對應 ArtifactVersion，具 document_type、authority_level、effective dates、owner、classification、ACL reference。
- Chunk 具 chunk_id、text hash、page/section/coordinates、embedding ref、parser/chunker version、language、hidden/injection scan status。
- Citation 由 `artifact_version_id + locator` 組成，不以臨時 URL 作唯一識別。

## 5. 共通 Envelope

所有 Capability request/response 應包含：

```json
{
  "schema_version": "1.0",
  "request_id": "uuid",
  "tenant_id": "uuid",
  "actor": {"type": "user", "id": "uuid"},
  "purpose": "engineering_demo",
  "context_refs": [],
  "submitted_at": "RFC3339",
  "idempotency_key": "client-generated"
}
```

Response envelope：

```json
{
  "schema_version": "1.0",
  "request_id": "uuid",
  "status": "accepted|succeeded|failed",
  "job_id": "uuid-or-null",
  "result": {},
  "evidence_refs": [],
  "lineage_ref": "uuid",
  "warnings": [],
  "created_at": "RFC3339"
}
```

## 6. Job 與 Event Contract

### 6.1 Job

- `job_id`, `capability_id`, `capability_version`, `tenant_id`, `actor_id`
- `state`, `priority`, `resource_class`, `queue`, `attempt`, `max_attempts`
- `input_snapshot_ref`, `result_ref`, `progress`, `stage`, `error_code`
- `created_at`, `started_at`, `heartbeat_at`, `completed_at`, `cancel_requested_at`
- `correlation_id`, `trace_id`, `idempotency_key`

### 6.2 Domain event

Event 採 past tense，至少包含 `event_id`, `event_type`, `event_version`, `aggregate_id`, `occurred_at`, `producer`, `tenant_id`, `classification`, `payload`, `lineage_ref`。

範例：`cad.artifact_ingested.v1`、`similarity.search_completed.v1`、`review.violation_waived.v1`。

Consumer 必須 idempotent；Event schema 只能向後相容新增 optional field，破壞性變更升 major version。

## 7. Lineage Contract

Lineage graph 以 node + edge 表示：

- Nodes：source record、artifact version、feature set、index、model/rule version、job execution、result、human decision。
- Edges：`ingested_from`, `parsed_from`, `derived_from`, `embedded_from`, `evaluated_with`, `approved_by`, `supersedes`, `exported_as`。

- **CDM-LIN-001**：每個外顯結果至少可追溯到 input、code/parser、model/rule、execution 與 human decision（若有）。
- **CDM-LIN-002**：Lineage 本身不可被一般使用者修改；更正採 append-only event。
- **CDM-LIN-003**：刪除來源時依 policy 標記／刪除衍生物並留下合規 tombstone。

## 8. Data quality Contract

共通 quality dimensions：completeness、validity、consistency、uniqueness、timeliness、lineage completeness。

每筆 mapping 輸出：

- `quality_status`: valid / warning / invalid / quarantined
- `quality_issues[]`: code、field、raw value、message、severity
- `mapping_version`, `validated_at`

Invalid 資料不得進 production index；warning 是否可用由 Capability policy 決定。

## 9. Schema 治理

- JSON Schema/OpenAPI 作為 wire contract；DB schema 不直接等同 API contract。
- Schema 儲存在 registry，具有 owner、compatibility test、example、changelog 與 deprecation date。
- 所有 money/unit/time/percentage 均使用明確型別，不以拼接字串傳遞。
- Log 不得完整輸出高敏感 payload；使用 field-level redaction。
- Contract test 同時套用 Public Connector、Mock Company Connector 與至少一個真實企業 Connector。
