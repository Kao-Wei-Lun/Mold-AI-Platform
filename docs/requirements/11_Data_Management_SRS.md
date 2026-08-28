# 11 — Data Management Center Software Requirements Specification

版本：0.1 Draft  
日期：2026-08-28  
適用範圍：Mold AI Platform Demo 擴充版與 Enterprise 正式版

## 1. 文件目的

本文件定義 Mold AI Platform「資料管理中心」的完整需求，使具權限的人員可在 Web UI
中新增、查看、修改、版本化、核准、停用、封存、匯入與匯出平台使用的工程資料。

資料管理中心不是直接操作資料庫的通用 CRUD 工具。所有操作必須遵守 Canonical Data
Model、版本、權限、資料品質、Audit、Lineage、Retention 與工程核准流程。

## 2. 設計結論

1. 平台應提供獨立的「資料管理」功能區，而不是把管理功能散落在各工程工作頁。
2. 主檔可修改，但生效中的工程資料不得被覆寫。
3. CAD、規則、知識文件、CAE 原始結果等資料以新版本取代舊版本。
4. 已完成的工程結果、Audit 與 Lineage 採 append-only 或唯讀。
5. 一般使用者看到的「刪除」預設代表停用或封存；實體刪除僅限符合 Retention、Legal
   Hold、關聯與權限政策的管理流程。
6. 資料新增、修改、核准及封存要求可識別的 Actor，因此本功能必須與帳號及權限管理
   同時導入，詳細需求見
   [12_Identity_Access_Account_Management_SRS.md](12_Identity_Access_Account_Management_SRS.md)。

## 3. 目標與非目標

### 3.1 目標

- 將目前寫在前端或 fixture 的 Dataset、Product Type、Material、Machine、Defect 等選項
  升級成可治理主檔。
- 建立 Project → Product/Part → Mold → Mold Revision → Artifact 的正式關係。
- 允許工程人員在受控流程中管理 CAD、Rule、Trial、CAE、Knowledge 與 HMI 資料。
- 讓所有變更可回答「誰、何時、為何、從哪個版本改成什麼」。
- 支援 UI 單筆管理、批次匯入及未來 Company Connector 共用相同 Canonical Contract。
- 避免刪除或修改歷史資料後，使既有搜尋、審查、報告或核准結果失去依據。

### 3.2 非目標

- 不提供任意 SQL、直接資料表編輯器或資料庫管理工具。
- 不允許在瀏覽器直接修改 Qdrant vector 或 Object Storage 檔案。
- 不以本系統取代完整 PDM/PLM、MES、QMS、ERP 或 IAM 平台。
- 不允許 LLM 或 MCP 自動核准、發布、硬刪除或大量改寫工程資料。
- Demo 不宣稱已完成正式多租戶、法規保存或企業 SSO 上線。

## 4. 使用者角色

- **Viewer**：查看授權資料、版本、關聯與可下載內容。
- **Data Editor**：建立及修改草稿資料。
- **Data Steward**：管理主檔、Mapping、資料品質、合併與封存。
- **Mold Engineer**：管理授權範圍內的 Mold、Revision、CAD metadata。
- **Rule Owner**：建立 Rule Draft、執行測試並送審。
- **Technical Reviewer**：技術審查規則或工程資料。
- **Approver**：核准發布、Waiver 或受控例外。
- **Knowledge Curator**：管理文件、權威層級、分類與有效期間。
- **Platform Admin**：管理系統設定、帳號與營運工作，但不可修改 Audit。
- **Auditor**：唯讀檢視資料版本、核准、Lineage、Audit 與匯出紀錄。

## 5. 資料分類與操作政策

### 5.1 四類操作政策

| 政策 | 適用資料 | Create | Read | Update | Delete |
|---|---|---:|---:|---:|---:|
| Master Mutable | Dataset、Product Type、Material、Machine、Defect Code、Location | 是 | 是 | 是 | 停用／封存 |
| Versioned Engineering | Mold Revision、CAD、Rule、Knowledge、CAE Import、HMI Profile | 是 | 是 | 僅草稿或 metadata；內容建立新版本 | 封存／退役 |
| Workflow Record | Trial、Review、Decision、Waiver、Correction、Approval | 是 | 是 | 依狀態；結案後追加更正 | 不可一般刪除 |
| Immutable Operational | Audit、Lineage、完成 Job、已發布 Result、Export manifest | 系統產生 | 是 | 否 | 依保存政策的受控清除 |

### 5.2 共通資料狀態

可管理實體至少支援以下適用狀態：

```text
Draft → In Review → Approved → Active
  └──────────────→ Rejected
Active → Superseded / Retired / Archived
任何未信任輸入 → Quarantined
```

- `Draft` 可由具編輯權限者修改。
- `In Review` 預設鎖定內容，只允許退回或追加審查意見。
- `Approved/Active` 不得直接修改內容；變更必須建立新版本。
- `Archived` 預設不出現在一般選單、搜尋與新工作輸入中。
- `Quarantined` 不得進入 production index 或下游工程判定。

## 6. 資訊架構與導覽

資料管理中心應具有下列路由：

```text
/data                         資料總覽
/data/master                  基礎主檔
/data/molds                   模具
/data/molds/:id/revisions     模具版本
/data/artifacts               CAD／Drawing／Artifact
/data/rules                   模具設計規定
/data/trials                  製程與試模
/data/cae                     CAE／Moldflow
/data/knowledge               知識文件
/data/hmi                     HMI Profile 與擷取紀錄
/data/imports                 批次匯入
/data/jobs                    Job 與 Queue
/data/audit                   Audit
/data/lineage/:ref            Lineage
/data/archive                 封存與保留政策
```

### 6.1 資料總覽

應顯示：

- 各資料類別 Active、Draft、Invalid、Quarantined、Archived 數量。
- CAD parse/index coverage、Knowledge index coverage、CAE mapping coverage。
- 待審核 Rule、待處理資料品質問題、失敗匯入及 Stale Job。
- 最近變更、最近匯入及即將到期的 Rule/Document/Waiver。
- 目前使用的 Public、Synthetic、Company Connector 與同步狀態。
- 依使用者權限過濾後的統計；不得顯示無權資料數量造成側通道洩漏。

### 6.2 清單頁共同要求

- 關鍵字搜尋、條件篩選、排序、分頁與空狀態引導。
- 欄位顯示設定、儲存個人 View、CSV/XLSX 匯出。
- Create、Import、Export、Archive 等按鈕依權限及狀態顯示。
- 批次選取必須顯示影響筆數、可執行操作及確認摘要。
- 狀態、版本、資料來源、品質、分類及最後修改時間應可直接辨識。
- 大量清單應採 server-side filter/sort/page，不得把全部資料載入瀏覽器。
- URL 應保存非敏感 filter/page 狀態；不得把 token 或敏感資料放入 query string。

### 6.3 詳細頁共同要求

詳細頁至少包含：

- Overview：代碼、名稱、狀態、Owner、Scope、Classification。
- Relationships：所屬 Project/Part/Mold 及下游引用。
- Versions：版本差異、建立者、核准者、生效日與 supersedes 關係。
- Files/Artifacts：原始檔與衍生檔的授權下載。
- Quality：驗證結果、警告、Mapping issue、Quarantine 原因。
- Lineage：來源、解析、索引、規則、結果與人工決定。
- Audit：建立、修改、狀態轉移、匯出、封存及權限拒絕事件。
- Danger Zone：停用、封存、重建索引等高風險動作。

## 7. 共通資料模型

### 7.1 Managed Entity Envelope

所有受管理主實體至少包含：

- `id`：平台 UUID。
- `code`：人類可讀且在指定 Scope 內唯一的代碼。
- `name`, `description`。
- `status`, `version`, `row_version`。
- `tenant_id`, `business_unit_id`, `project_scope`, `customer_scope`。
- `classification`, `acl_policy_ref`, `policy_tags`。
- `owner_id`, `steward_id`。
- `effective_from`, `effective_to`。
- `source_system`, `source_refs`, `mapping_version`。
- `quality_status`, `quality_issues`。
- `created_by`, `created_at`, `updated_by`, `updated_at`。
- `archived_by`, `archived_at`, `archive_reason`。

### 7.2 樂觀鎖定

- 所有 Update 要求攜帶 `row_version` 或 HTTP `If-Match/ETag`。
- 版本不一致時回傳 `409 CONCURRENT_MODIFICATION`，並顯示伺服器最新值與差異入口。
- Client 不得靜默覆蓋其他使用者的修改。

## 8. 基礎主檔需求

### 8.1 主檔種類

第一期至少建立：

- Dataset
- Product Type
- Material
- Machine／Machine Model
- Defect Code
- Defect Location
- Process Parameter Definition
- Unit Definition
- Document Type
- Authority Level
- Approver Group

### 8.2 功能需求

- **DM-MST-001**：Data Steward 應可建立、查看、修改、停用及封存主檔。
- **DM-MST-002**：代碼一旦被工程紀錄引用不得直接修改；變更採 Alias 或新代碼。
- **DM-MST-003**：主檔應支援顯示名稱多語系，但 canonical code 不隨語言改變。
- **DM-MST-004**：停用值不得用於新紀錄，但歷史紀錄仍顯示原值。
- **DM-MST-005**：Material 應可保存家族、牌號、供應商牌號、單位、有效範圍及 Alias。
- **DM-MST-006**：Machine 應可保存廠牌、型號、噸位、控制器、地點、狀態與 HMI Profile。
- **DM-MST-007**：Defect 應使用 controlled code，並可配置名稱、嚴重度、位置與檢驗方法。
- **DM-MST-008**：所有工程表單應從主檔 API 取得選項，不再將正式選項寫死於前端。
- **DM-MST-009**：主檔更新應使 Cache 在定義 SLA 內失效，並保留更新 Audit。
- **DM-MST-010**：刪除被引用主檔時應拒絕並回傳引用摘要。

## 9. Mold、Revision 與 CAD 管理

### 9.1 關係模型

```text
Project → Product → Part → Mold → MoldRevision
                                  ├─ ArtifactVersion
                                  ├─ CADModel / FeatureSet
                                  ├─ ReviewRun
                                  ├─ TrialCase
                                  └─ CAEStudy
```

### 9.2 功能需求

- **DM-CAD-001**：應可建立 Mold 與 Mold Revision，並配置唯一代碼、Part、產品、材料與 Owner。
- **DM-CAD-002**：應支援上傳 STEP/STL；Enterprise 依核准矩陣增加其他格式與 Connector。
- **DM-CAD-003**：原始檔內容 immutable；替換檔案必須建立新 ArtifactVersion。
- **DM-CAD-004**：應檢查副檔名、MIME、Magic Bytes、大小、SHA-256、Malware 與重複內容。
- **DM-CAD-005**：管理者可修改未影響內容的 metadata，但所有修改需 Audit。
- **DM-CAD-006**：可從管理頁啟動重新解析、特徵重建與重新索引 Job。
- **DM-CAD-007**：重新解析不得覆寫舊 FeatureSet；新結果保存 parser/extractor/index version。
- **DM-CAD-008**：應顯示 3D Preview、尺寸、體積、表面積、拓撲統計與品質旗標。
- **DM-CAD-009**：封存 CAD 前應顯示其 Review、Similarity、Trial、CAE、Knowledge 引用。
- **DM-CAD-010**：已被核准工程結果引用的 CAD 版本不得硬刪除。
- **DM-CAD-011**：應支援 Duplicate/Merge 審查，但 Merge 只重導 canonical reference，不刪除原始 provenance。
- **DM-CAD-012**：歷史模具圖應可依 Mold、Revision、Product、Material、Dataset、日期與來源查詢。

## 10. 模具設計規定管理

### 10.1 Rule lifecycle

```text
Draft → Technical Review → Approved → Effective → Superseded / Retired
             └──────────→ Rejected → Draft
```

### 10.2 功能需求

- **DM-RUL-001**：Rule Owner 可建立 Rule Profile 與 Draft Rule Version。
- **DM-RUL-002**：Rule 可設定 applicability、measurement、condition、limit、unit、tolerance、severity、reference 與 recommendation。
- **DM-RUL-003**：Rule expression 僅允許受限 DSL 或已註冊 evaluator，不得執行任意程式碼。
- **DM-RUL-004**：發布前必須執行 positive、negative、boundary、not-applicable、not-evaluable fixtures。
- **DM-RUL-005**：送審後內容鎖定；退回 Draft 才能修改。
- **DM-RUL-006**：Author、Technical Reviewer 與 Approver 應支援職責分離。
- **DM-RUL-007**：Approved/Effective Rule 的變更必須複製成新版本。
- **DM-RUL-008**：UI 應顯示版本差異及受影響 Product/Material/Customer scope。
- **DM-RUL-009**：退役 Rule 不影響歷史 ReviewRun，舊結果繼續指向舊版本。
- **DM-RUL-010**：發布、退役、緊急停用及例外核准必須寫入 Audit 與 Lineage。

## 11. Process／Trial 管理

- **DM-TRI-001**：可建立 Trial Case、Process Run、Parameter、Defect Observation 與 Corrective Action。
- **DM-TRI-002**：草稿 Trial 可修改；結案後變更採 Correction Record，不覆寫原紀錄。
- **DM-TRI-003**：參數保存 raw name/value/unit 與 canonical value/unit。
- **DM-TRI-004**：Defect 必須引用受控 Defect Code；未知值進 Mapping Backlog。
- **DM-TRI-005**：Corrective Action 應保存 before/after、reason、approval、stop condition 與 observed outcome。
- **DM-TRI-006**：任何建議不得被資料管理操作直接寫入機台。
- **DM-TRI-007**：結案與重開應要求權限、原因及 Audit。
- **DM-TRI-008**：可依 Mold Revision、Material、Machine、Defect、Outcome 與日期查詢。

## 12. CAE／Moldflow 管理

- **DM-CAE-001**：可匯入 CAE Study、Run、Result 及其 Artifact。
- **DM-CAE-002**：原始 solver export immutable；解析錯誤需新 Parser Result 或新版本。
- **DM-CAE-003**：應保存 solver/version、material model、mesh、process settings、unit system 與 input hash。
- **DM-CAE-004**：Metric mapping 應由受控定義管理，未知欄位進 Mapping Backlog。
- **DM-CAE-005**：只有通過 compatibility gate 的 Run 可計算差異。
- **DM-CAE-006**：封存前應顯示被 Review、Trial、Knowledge 或報告引用的情況。
- **DM-CAE-007**：Enterprise 原始結果存取需遵循 solver 授權及資料分類。

## 13. Knowledge／RAG 管理

- **DM-KNW-001**：Curator 可匯入 TXT、Markdown 及 Enterprise 核准格式。
- **DM-KNW-002**：Document 應保存 title、type、authority、language、owner、effective date、classification 與 ACL。
- **DM-KNW-003**：新檔或內容修正建立新 ArtifactVersion；不得覆寫已引用 Chunk。
- **DM-KNW-004**：應顯示 Parser、Chunker、Injection Scan、Chunk Count 與 Index 狀態。
- **DM-KNW-005**：Quarantined 文件不得進入檢索。
- **DM-KNW-006**：Authority 或 ACL 變更應觸發索引安全範圍更新。
- **DM-KNW-007**：Retired 文件不再用於新回答，但歷史 Citation 保留版本定位。
- **DM-KNW-008**：Citation 必須指向 ArtifactVersion 與 locator，不依賴臨時下載 URL。

## 14. HMI 與 Excel 管理

- **DM-HMI-001**：應管理 HMI Profile 的廠牌、型號、畫面、語言、區域、欄位、單位與有效範圍。
- **DM-HMI-002**：Profile 採版本化；新版本不得改變既有 Extraction 的解釋依據。
- **DM-HMI-003**：Extraction 保存原圖、Field、Confidence、Region、Review Decision 與 Lineage。
- **DM-HMI-004**：低信心或驗證失敗欄位必須人工確認後才能匯出。
- **DM-HMI-005**：Export Artifact immutable，並保存 Template Version 與來源 Extraction。
- **DM-HMI-006**：人工修正採 Decision 記錄，不覆寫 OCR Raw Value。

## 15. Job、Audit 與 Lineage 管理

- **DM-GOV-001**：Job 頁可查詢狀態、進度、Queue、Attempt、Actor、Input 與 Result reference。
- **DM-GOV-002**：只有可取消狀態可要求取消；完成 Job 不得偽裝成 cancelled。
- **DM-GOV-003**：Retry 僅能建立受控新 Attempt，並保留舊錯誤。
- **DM-GOV-004**：Audit 頁為唯讀，可依 Actor、Action、Entity、日期、結果與 Correlation ID 搜尋。
- **DM-GOV-005**：Audit export 必須另外記錄 Audit，並受較高權限限制。
- **DM-GOV-006**：Lineage 圖應顯示 source → artifact → parse/feature → index/rule/model → result → decision/export。
- **DM-GOV-007**：一般管理者不得修改或刪除 Audit/Lineage。

## 16. 批次匯入、匯出與 Connector

### 16.1 匯入流程

```text
Upload/Register Source
→ Scan and Parse
→ Field Mapping
→ Dry Run Validation
→ Added/Updated/Skipped/Error Preview
→ Human Confirmation
→ Asynchronous Commit Job
→ Reconciliation and Audit Report
```

- **DM-IMP-001**：主檔應支援 CSV/XLSX，工程檔依模組支援 ZIP + Manifest 或 Connector。
- **DM-IMP-002**：匯入前必須提供 Dry Run，不得在預覽階段寫入正式資料。
- **DM-IMP-003**：Mapping 應保存版本、原始欄位、轉換、單位與 null semantics。
- **DM-IMP-004**：相同 Source Version 重跑必須 idempotent。
- **DM-IMP-005**：部分失敗政策必須明確為 all-or-nothing 或逐筆 commit；不可默默混用。
- **DM-IMP-006**：匯入報告應列出 Added、Updated、Skipped、Warning、Error 與 Canonical IDs。
- **DM-IMP-007**：匯出必須先套用 row/field 權限與資料遮罩。
- **DM-IMP-008**：大量匯出採非同步 Job、短效下載與過期清除。
- **DM-IMP-009**：Public/Synthetic/Company Connector 產出相同 Canonical Contract。

## 17. 刪除、封存與資料保存

### 17.1 刪除層級

1. **Deactivate**：不再提供新紀錄選用。
2. **Archive**：從一般清單及搜尋移除，但保留授權檢視。
3. **Purge Derived Data**：依政策重建或清除 Preview/Feature/Index。
4. **Hard Delete**：僅限未被引用、保存期屆滿、無 Legal Hold 且具專門權限。
5. **Tombstone**：來源依法刪除後保留不含內容的稽核與關聯證明。

### 17.2 功能需求

- **DM-DEL-001**：Archive 前顯示直接及重要間接引用數量。
- **DM-DEL-002**：操作人需填寫原因，並可要求第二人核准。
- **DM-DEL-003**：Legal Hold 資料不得 Purge 或 Hard Delete。
- **DM-DEL-004**：清除 Artifact 時應處理 derivative、vector、cache、backup retention 及 Lineage tombstone。
- **DM-DEL-005**：回復 Archived 資料需權限與 Audit；被 Superseded 資料不得恢復為 Active 而跳過核准。

## 18. API 與事件需求

### 18.1 API 原則

- UI、Connector、MCP 必須經 Domain API，不直接存取 DB。
- CRUD API 應使用一致 error envelope、idempotency、pagination、filter 與 ETag。
- 命令型動作使用明確 endpoint，例如 `/submit-review`, `/approve`, `/archive`, `/reindex`，
  不以任意 `PATCH status` 取代流程驗證。
- 批次及重型操作回傳 `202 + job_id`。
- 所有 Object download 使用授權 streaming 或短效 URL。

### 18.2 代表性端點

```text
GET/POST        /api/v1/data/materials
GET/PATCH       /api/v1/data/materials/{id}
POST            /api/v1/data/materials/{id}/deactivate
GET/POST        /api/v1/data/molds
POST            /api/v1/data/molds/{id}/revisions
POST            /api/v1/data/mold-revisions/{id}/artifacts
POST            /api/v1/data/rules/{id}/versions
POST            /api/v1/data/rule-versions/{id}/submit-review
POST            /api/v1/data/rule-versions/{id}/approve
POST            /api/v1/data/entities/{type}/{id}/archive
GET             /api/v1/data/entities/{type}/{id}/versions
GET             /api/v1/data/entities/{type}/{id}/audit
GET             /api/v1/data/lineage/{ref}
POST            /api/v1/data/imports/dry-run
POST            /api/v1/data/imports/{id}/commit
```

### 18.3 Domain events

至少定義：

- `master_data.created/updated/deactivated.v1`
- `mold.revision_created.v1`
- `artifact.version_ingested.v1`
- `rule.version_submitted/approved/published/retired.v1`
- `trial.closed/corrected.v1`
- `knowledge.version_published/retired.v1`
- `entity.archived/restored.v1`
- `import.committed/failed.v1`

## 19. MCP 與 Assistant 邊界

- MCP 可提供查詢、建立低風險 Draft、啟動匯入 Dry Run 或開啟管理頁 deep link。
- MCP 不得直接發布 Rule、核准 Waiver、Hard Delete、批次封存或變更權限。
- 任何寫入 Tool 必須使用與 Web UI 相同的 Actor、AuthZ、Validation、Audit 與 Confirmation。
- LLM 提議的 metadata、mapping 或 Rule 內容一律為不受信任 Draft，需人工確認。
- Tool 回傳最小必要欄位，不回傳無權或跨 Scope 資料。

## 20. 非功能需求

- **DM-NFR-001**：一般清單 API P95 目標 ≤ 1 秒；詳細頁 P95 目標 ≤ 1.5 秒，正式門檻依企業容量校準。
- **DM-NFR-002**：清單至少支援 100 萬級 metadata 的 server-side pagination/filter 設計。
- **DM-NFR-003**：單筆寫入必須在 DB transaction 中同時建立 Domain/Audit 所需狀態。
- **DM-NFR-004**：Search index 更新採 outbox/event 或可重試機制，避免 DB 與 index 無法對帳。
- **DM-NFR-005**：所有管理頁支援鍵盤操作、清楚 focus、錯誤定位與中英文 UI。
- **DM-NFR-006**：敏感欄位不寫入一般 log；匯出與下載需安全 header。
- **DM-NFR-007**：備份與還原應涵蓋 DB、Artifact、Index rebuild manifest 及 IAM mapping。
- **DM-NFR-008**：Connector、Import 與 Bulk Action 具配額、Rate Limit、Timeout 與取消策略。

## 21. Demo 與 Enterprise 邊界

| 項目 | Demo | Enterprise |
|---|---|---|
| 帳號 | 本機受控帳號 | 公司 OIDC/SAML SSO |
| 主檔 | 少量手動 CRUD | 正式 Owner、Scope、同步及 Approval |
| 資料來源 | Public/Synthetic/手動上傳 | PDM/PLM/MES/QMS/CAE Connector |
| 權限 | 固定角色、單一 Demo scope | RBAC + ABAC + 多組織 Scope |
| 刪除 | 封存為主 | Retention、Legal Hold、DLP、核准 |
| 匯入 | CSV/XLSX/ZIP Demo | 大量、排程、Reconciliation |
| Audit | 應用程式 Audit | Append-only、SIEM、合規保存 |

## 22. 待確認事項

- 公司實際 Project、Part、Mold 與 Revision 編碼規則。
- Material、Machine、Defect 的 Source of Truth 與主檔 Owner。
- 哪些資料由本平台維護，哪些只能從 PDM/MES/QMS 唯讀同步。
- Rule 審核層級與職責分離要求。
- 各資料分類的 Retention、Legal Hold、刪除及匯出政策。
- 同一 Mold 是否可能跨 Customer、Supplier 或 Business Unit 共用。
- 正式容量：Mold、Revision、Artifact、Trial、CAE、Document 與每日變更量。
