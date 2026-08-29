# Mold AI Platform — 歷史資料管理功能詳細修改規劃

> 文件狀態：已授權實作；Phase H0 基線建立中
> 適用範圍：目前 Demo 與未來 Enterprise 資料管理體驗
> 核心目標：讓使用者不只看見資料標題或摘要，而能完整查閱、追溯、受控修改、比較版本及確認資料來源，同時維持工程歷史與 AI 結果的可重現性。

---

## 一、規劃摘要

目前系統並不是缺少歷史資料。後端已有 35 個以上的 Django Model，且 Trial、CAE、HMI、CAD、知識、規則、設計審查、相似搜尋、Job 與 Audit 等領域已保存相當完整的巢狀資料。

主要缺口在前端與治理流程：

1. 多數清單只顯示標題、狀態、筆數或少量摘要。
2. 使用者無法由清單進入穩定、可重新整理、可分享 deep link 的詳細頁。
3. 後端已有的 ProcessRun、CAE Result、HMI Correction、ArtifactVersion 等內容未完整呈現。
4. 部分資料雖有 PATCH API，但缺少符合生命週期的受控編輯介面。
5. AuditEvent、JobEvent 與 Lineage 雖已記錄，尚無統一查閱介面。
6. 部分清單存在固定筆數或前端截斷，無法支援公司正式資料量。

因此本規劃不採用「所有資料直接 CRUD」的方式，而採用：

```text
工程工作區：建立資料、上傳檔案、執行分析與審查
                         │
                         ▼
歷史資料中心：搜尋、詳細檢視、關聯、版本、修正、Lineage、Audit
```

---

## 二、目標與非目標

### 2.1 目標

- 所有主要歷史資料都能由清單開啟完整內容。
- 詳細頁具有穩定 URL；重新整理、返回及外部 deep link 不遺失選取內容。
- 清單支援伺服器端搜尋、篩選、排序及分頁。
- 根據資料生命週期提供「編輯、建立新版本、建立修正、封存或重跑」等正確操作。
- 顯示資料的上下游關聯、來源、處理 Job、使用版本、品質及 Audit。
- 歷史 AI／工程結果可重現，不因後續修改而被靜默覆蓋。
- Demo 可先以現有帳號與權限運作，架構保留 Enterprise 細粒度權限。

### 2.2 非目標

- 不提供一般使用者直接修改資料庫或 Raw JSON。
- 不允許覆寫 CAD 原始檔、CAE 原始結果、HMI 原始 OCR、AuditEvent 或已發布內容。
- 不在第一階段進行大量刪除、跨資料集搬移或高風險批次修改。
- 不因改善歷史資料介面而改變現有 Canonical ID、Data Contract 或既有分析結果語意。

---

## 三、目前功能與缺口盤點

| 領域 | 主要資料結構 | 現有能力 | 主要缺口 | 建議修改方式 |
|---|---|---|---|---|
| 主資料 | Dataset、Product Type、Material、Machine、Location 等 | 清單、篩選、分頁、新增、修改、停用、封存 | 缺少每筆引用影響、變更時間軸及歷史值 | 保留現有管理介面，補 Detail、References、Audit |
| 模具登錄 | Project → ProductPart → Mold → MoldRevision | 清單、建立、Revision 發行；部分 Detail/PATCH API | UI 無詳細頁；ProductPart Detail/PATCH 需補齊 | 詳細頁＋安全欄位編輯；Revision 發行後不可原地覆寫 |
| CAD | Artifact → ArtifactVersion → CADModel → FeatureSet | 上傳、處理、預覽、近期選擇、相似搜尋 | 無中央歷史瀏覽、版本鏈、品質、Job、Lineage | Artifact metadata 可編輯；檔案替換建立新 ArtifactVersion |
| 模具規則 | RuleProfile → RuleVersion | 規則表、Clone、測試、送審、核准、發布、退役 | 目前只使用第一個 Profile；無版本選擇、Draft 規則編輯與 Diff | Draft 可改；Published 只能 Clone 新版本 |
| 知識文件 | KnowledgeDocument → KnowledgeChunk → KnowledgeSearch | 上傳、索引、工作流、搜尋 | UI 最多顯示 8 筆；無內容、Chunk、來源、版本及引用 | Published 文件建立新版本；舊引用保留 |
| 試模／製程 | TrialCase → ProcessRun → Parameter／Defect／Action＋Correction | 後端完整 Detail、Close、Reopen、Correction | UI 只顯示案例摘要；無 Run、參數、缺陷、改善措施 | Draft/Reopened 可編輯；Closed 只能 Correction 或受控 Reopen |
| CAE | CAEStudy → CAERun → CAEResult＋CAEComparison | 後端完整 Detail、Run 匯入、封存、比較 | UI 只顯示 Run 數；無設定、結果、品質、比較歷史 | 原始 Result 不可改；新增 Run 或新 Study 版本 |
| HMI | ProfileVersion；Extraction → Field → CorrectionDecision → Export | 上傳辨識、欄位覆核、Excel 匯出 | 無歷史 Extraction 清單、舊圖片、修正時間軸與匯出歷史 | Raw OCR 不可改；人工決策追加；Export 版本化 |
| 設計審查 | ReviewRun → Finding → Decision | 單次審查可查看 | 切頁後難以回溯；無歷史清單及兩次審查比較 | 結果唯讀；重跑建立新 ReviewRun |
| 搜尋與分析 | SimilaritySearch、KnowledgeSearch、ProcessCaseSearch、CAEComparison | 結果已保存 | 無統一歷史中心 | 結果唯讀；允許重跑、比較、標記或封存 |
| Job／Queue | Job → JobEvent | 狀態查詢、工作執行 | 無歷史清單、事件時間軸、受控 Retry/Cancel UI | Event 唯讀；Retry 建立新事件或新工作嘗試 |
| Audit／Lineage | AuditEvent、provenance、source locator、關聯 FK | 多數寫入操作已有 Audit | 沒有可搜尋 UI 及統一關聯圖 | 永久唯讀、追加式；需獨立權限 |

### 3.1 已確認的具體前端問題

- `EngineeringDataManagementWorkspace.vue` 已取得 Trial corrections、CAE runs/results 等資料，但畫面只使用摘要。
- `KnowledgeWorkspace.vue` 使用 `documents.slice(0, 8)`，超過 8 筆時無法完整瀏覽。
- `RuleManagementWorkspace.vue` 目前以第一個 profile 為主要顯示來源，缺少版本選擇器。
- `MoldRegistryWorkspace.vue` 只有清單及建立表單，缺少 record selection 與 detail view。
- `HMIWorkspace.vue` 聚焦目前一次擷取，未提供 extraction history browser。
- Trial 與 CAE 清單目前最多載入固定筆數，且清單 payload 可能夾帶完整巢狀內容，不適合公司資料量。
- `AuditEvent` 已存在，但目前沒有獨立 Audit API 與管理頁。

---

## 四、資訊架構與使用者體驗

### 4.1 新增「歷史資料中心」

建議新增以下路由：

```text
/data/overview
/data/molds
/data/cad-artifacts
/data/trials
/data/cae
/data/hmi
/data/knowledge
/data/rules
/data/analysis-results
/data/jobs
/data/audit-lineage
```

現有工程頁保留快速選擇、建立及執行功能；歷史資料中心負責完整管理。兩者透過穩定 deep link 互相連結。

### 4.2 採用 Hybrid Master–Detail

原附件提出 Drawer、Accordion 與獨立頁三種選擇。本規劃採用混合設計：

- 桌面版清單點擊後，先顯示右側 Quick Detail Drawer。
- Drawer 提供概要、主要狀態、常用動作與「開啟完整詳細頁」。
- 完整資料使用獨立路由，例如 `/data/trials/{id}`。
- 行動版不使用狹窄 Drawer，直接開啟全頁詳細頁。
- URL 保存目前 tab、選取版本或 Run，例如 `?tab=results&run={id}`。

這可同時滿足快速查看、重新整理、瀏覽器返回、外部 deep link 及複雜資料顯示需求。

### 4.3 標準清單功能

每個領域的清單至少具備：

- 關鍵字搜尋。
- Project、Mold、Revision、狀態、日期、來源、擁有者、材料、機台、資料品質篩選。
- 伺服器端排序與分頁。
- 頁面大小選擇。
- 一致的狀態、品質、封存與過期標籤。
- 載入中、空狀態、錯誤、無權限及已刪除／已封存狀態。
- 複製 deep link。
- 權限允許時下載原始檔或匯出中繼資料。
- 初期不提供批次硬刪除。

### 4.4 標準詳細頁

每個詳細頁共用以下骨架，依資料類型顯示適用頁籤：

1. **概要**：Canonical ID、名稱、版本、狀態、擁有者、來源、建立／更新時間。
2. **工程內容**：該領域的完整結構化資料。
3. **關聯資料**：Project、Mold、Revision、Artifact、Trial、CAE、Review 等互相連結。
4. **版本／修正**：版本鏈、Correction、Before/After、Supersedes。
5. **檔案／預覽**：3D、圖片、原始文件、檔案 metadata。
6. **分析結果**：Similarity、Review、CAE Comparison 或引用結果。
7. **Lineage**：來源、衍生關係、Parser／模型／規則版本及 Job。
8. **Audit**：Actor、時間、Action、Reason、Request、Decision。

### 4.5 共用元件

| 元件 | 用途 | 主要要求 |
|---|---|---|
| `DetailDrawer.vue` | 快速查看摘要 | 桌面右側滑入、行動版全頁、焦點鎖定、Esc 關閉、ARIA |
| `RecordHeader.vue` | 詳細頁標頭 | ID、狀態、版本、警告、主要動作、複製連結 |
| `DetailTabs.vue` | 統一頁籤 | URL 同步、權限與資料類型控制 |
| `PropertyGrid.vue` | Key-value 詳情 | Copy、長文字摺疊、單位與空值格式 |
| `TimelineList.vue` | Correction、Decision、Audit | 時間、Actor、摘要、展開 Before/After |
| `VersionSelector.vue` | 選擇版本／Run | 顯示 Current、Published、Superseded 狀態 |
| `VersionDiff.vue` | 結構化差異 | Added、Removed、Changed；禁止只顯示 Raw JSON diff |
| `RelationPanel.vue` | 上下游關聯 | 類型、狀態、版本、可點擊 deep link |
| `LineageGraph.vue` | 溯源 | 支援表格替代模式，避免僅靠圖形表達 |
| `DataTable.vue` | 統一清單 | Server-side filter/sort/page、loading/empty/error |
| `ConfirmActionDialog.vue` | 高風險動作 | Reason 必填、影響預覽、不可逆警告 |

---

## 五、資料修改與版本治理規則

### 5.1 共通原則

1. Draft 可依權限直接修改安全欄位。
2. Released、Published、Closed 或已作為分析輸入的資料，不得靜默覆寫。
3. 內容變更應建立新版本、Correction 或新的 Run。
4. Canonical code、原始檔 checksum、歷史結果、Audit 與 JobEvent 不可修改。
5. 已被引用的資料不得硬刪除；使用 deactivate、archive、retire、supersede 或 quarantine。
6. 每次修改必須記錄 Actor、Reason、Request ID、Before/After 及資料版本。
7. API 與 UI 同時執行權限與狀態檢查，不能只靠隱藏按鈕。

### 5.2 各資料類型規則

| 資料 | 可直接修改 | 必須新版本／修正 | 永遠不可修改 |
|---|---|---|---|
| Master Data | 顯示名稱、描述、有效期間 | 代碼語意重大改變時建立新項目 | Canonical code、Audit |
| Project／Part／Mold | 名稱、描述及安全 metadata | 識別語意變更時建立新記錄或 Revision | Canonical ID |
| MoldRevision | Draft 欄位 | Released 後建立新 Revision | 已發行 Revision 的歷史內容 |
| Artifact | 名稱、分類、材料、關聯、品質狀態 | 替換二進位檔建立 ArtifactVersion | 舊版本檔案、checksum |
| Rule | Draft RuleVersion | Published 後 Clone 新版本 | 已發布版本 |
| Knowledge | Draft metadata／內容 | Published 後建立 superseding version | 舊 Chunk 與歷史 Citation |
| Trial | Draft／Reopened 基本內容及子資料 | Closed 後建立 Correction 或受控 Reopen | 原始關閉快照 |
| CAE | Draft Study metadata | 新增 Run 或 superseding Study | 已匯入 Result 數值 |
| HMI Profile | Draft field specs | Published 後建立新 ProfileVersion | 已發布 ProfileVersion |
| HMI Extraction | Review 狀態與人工決策 | CorrectionDecision 追加 | 原始圖片、Raw OCR |
| Derived Result | 標籤、註記、封存狀態 | Rerun 建立新結果 | 歷史輸入與輸出內容 |
| Job／Audit／Lineage | 無 | Retry 建立新嘗試／事件 | 歷史事件本身 |

### 5.3 並行修改控制

所有可修改 API 應要求：

```json
{
  "row_version": 7,
  "reason": "更新試模結果描述",
  "changes": {}
}
```

若 `row_version` 已變更，回傳 `409 CONFLICT`，UI 顯示目前伺服器版本、使用者尚未儲存的內容，以及 Reload、Compare、Discard 選項。初期不提供自動合併工程資料。

---

## 六、詳細功能需求

### 6.1 Trial／Process

詳細頁需顯示：

- Case Code、狀態、Purpose、Outcome、Mold Revision、Machine、Material Lot、開始與結束時間、Data Quality。
- ProcessRun 清單與每個 Run 的順序、時間、操作人員及備註。
- ProcessParameter 的 code、value、unit、來源及品質。
- DefectObservation 的 defect type、location、severity、evidence。
- CorrectiveAction 的內容、執行順序、結果與責任人。
- TrialCorrectionRecord 的 before、after、reason、actor、time。
- Provenance、附件、關聯 CAE、Review 與 CAD 版本。

Draft／Reopened 可編輯；Closed 只能建立 Correction。Reopen 與 Close 均需理由、必要欄位及影響檢查。

### 6.2 CAE／Moldflow

- 顯示 Study code、Objective、Solver、Material Model、Mesh Family、Mold Revision。
- 提供 Run selector、Solver Version、Mesh、Boundary Settings、Process Settings、Unit System。
- Result table 顯示 metric code、value、unit、quality flag、source locator。
- 顯示 Parser／Importer 版本、建立 Job、原始檔及資料品質。
- 顯示 CAEComparison 歷史及兩個 Run／Study 的差異。
- 不提供直接修改 CAEResult；新資料使用「匯入新 Run」或新 Study。

### 6.3 HMI

- 新增 HMI 歷史清單及詳細頁。
- 顯示原始圖片、ProfileVersion、Raw OCR、Parsed／Effective Value、Unit、Confidence、Review Status。
- 顯示 CorrectionDecision 的 before／after、理由、審查人與時間。
- 顯示歷史 Export、checksum、建立時間與下載。
- 建立與 Trial、Machine、Material、ProcessRun 的連結。
- 原始 OCR 永遠唯讀；覆核以決策事件追加。

### 6.4 CAD／Registry

形成可瀏覽鏈：

```text
Project → ProductPart → Mold → MoldRevision
        → Artifact → ArtifactVersion → CADModel → FeatureSet
        → Job → Similarity／Review／CAE／Trial
```

- 顯示 Project description、Mold type、cavity count、Revision change summary。
- 顯示 Artifact 分類、材料、dataset、quality、lifecycle。
- 顯示所有 ArtifactVersion、格式、大小、sha256、malware status。
- 提供 3D 預覽、幾何資訊、FeatureSet schema 與 index status。
- 顯示 Processing Job、錯誤、重試、Derived-from 與所有下游分析。
- 補齊 ProductPart Detail/PATCH，確認 Artifact Detail 包含 versions、lineage、references。

### 6.5 Knowledge

- 移除 `documents.slice(0, 8)`，改用伺服器端分頁。
- 顯示 title、type、authority、owner、language、parser、chunker、publication status。
- 安全預覽原始內容及 Chunk；預設純文字，可信格式才以 sanitized Markdown 呈現。
- 支援受權限控制的原始文件下載。
- 顯示 ingestion Job、index status、搜尋引用次數及使用該版本的歷史回答。
- Published 文件修改使用「建立新版本」，保留 `supersedes` 關係及舊 Citation。

### 6.6 Rule

- 增加 Profile／Version selector，不再固定顯示第一個 Profile。
- 顯示版本時間軸、狀態、作者、審查者、發布時間及使用次數。
- Draft RuleVersion 支援受控欄位編輯，不可輸入任意可執行程式碼。
- 完整 Validate、Test、Submit、Approve、Publish、Retire 工作流。
- 顯示版本 Diff 與使用該 RuleVersion 的歷史 ReviewRun。

### 6.7 Derived Analysis History

建立 SimilaritySearch、ReviewRun、KnowledgeSearch、ProcessCaseSearch、CAEComparison 統一清單。每筆顯示輸入版本、參數、規則／模型版本、結果摘要、Job、建立者及時間。結果唯讀，提供 Re-run、Compare、Open Input、Open Output、Archive。

### 6.8 Job／Queue

- 依狀態、類型、時間、Entity 與 Request ID 篩選。
- 顯示 JobEvent、進度、重試次數、錯誤 code 與可讀訊息。
- 僅允許對支援狀態執行 Cancel／Retry。
- Retry 不覆寫舊結果，建立新 attempt 或關聯 Job。

### 6.9 Audit／Lineage

Audit 支援 Actor、Action、Entity、日期、Request ID、Decision、Reason 篩選，並由每個詳細頁直接開啟對應事件。Audit 永久唯讀；授權匯出也必須留下 AuditEvent。

Lineage 顯示 Source、Artifact／Document／Profile／Rule／Model version、Parser、Chunker、Feature schema、Job、衍生資料及歷史分析結果，提供圖形與表格兩種方式。

---

## 七、API 與 Data Contract 修改規劃

### 7.1 統一清單契約

```http
GET /api/v1/{resources}
  ?q=&status=&project_id=&mold_id=
  &date_from=&date_to=&sort=-updated_at
  &page=1&page_size=25
```

回傳 `items`、`page`、`page_size`、`total`、`sort`。清單 DTO 只包含摘要、狀態與 child counts，不回傳完整 runs、results、chunks 或 corrections。

### 7.2 統一詳細與治理端點

```http
GET    /api/v1/{resources}/{id}
PATCH  /api/v1/{resources}/{id}
POST   /api/v1/{resources}/{id}/actions
POST   /api/v1/{resources}/{id}/versions
POST   /api/v1/{resources}/{id}/corrections
GET    /api/v1/{resources}/{id}/references
GET    /api/v1/{resources}/{id}/lineage
GET    /api/v1/{resources}/{id}/audit
```

並非每種資源都支援所有端點；能力由 resource policy 決定。

### 7.3 統一錯誤

- `400 VALIDATION_ERROR`
- `401 AUTHENTICATION_REQUIRED`
- `403 PERMISSION_DENIED`
- `404 RECORD_NOT_FOUND`
- `409 VERSION_CONFLICT`
- `409 INVALID_LIFECYCLE_TRANSITION`
- `422 DATA_QUALITY_BLOCKED`
- `423 RECORD_LOCKED`

錯誤回應包含 `code`、`message`、`field_errors`、`request_id` 與安全的 `details`。

### 7.4 待確認後端缺口

| 項目 | 判定 | 修改需求 |
|---|---|---|
| Trial Detail | 基本完整 | 確認 Parameters、Defects、Actions、Corrections、Provenance |
| CAE Detail | 基本完整 | 確認 Runs、Results、Settings、Source、Quality |
| HMI History | 有基礎 | 補前端 contract；確認 corrections、exports、profile version |
| Knowledge Detail | 需驗證 | 補 chunks、versions、citations、download metadata |
| CAD Artifact Detail | 需擴充 | versions、CAD metadata、feature sets、lineage、references |
| ProductPart Detail | 缺口 | 新增 GET/PATCH 與引用檢查 |
| Rule Draft Editing | 缺口 | 新增受控修改 API 與 validation |
| Audit | 缺口 | 新增 read-only list/detail/filter API |
| Lineage | 目前分散 | 建立 normalized lineage response |
| 各類清單 | 不一致 | Summary DTO＋server-side filter/sort/page |

---

## 八、帳號、角色與權限

歷史資料管理需要帳號管理，因為查看範圍、修改責任、核准分工與 Audit Actor 都依賴可識別使用者。

| 角色 | 主要權限 |
|---|---|
| Viewer | 查看授權範圍內摘要與詳細資料 |
| Mold Engineer | 建立／修改範圍內 Draft、提交審查、建立 Correction |
| Data Steward | 維護主資料、metadata、mapping、品質與封存 |
| Rule／Knowledge Author | 建立及修改對應 Draft |
| Reviewer／Approver | 審查、核准或駁回；不得核准自己建立的內容 |
| Auditor | 查看 Audit、Lineage 與授權匯出，不具工程資料寫入權限 |
| Platform Admin | 帳號、角色、平台與 Job 管理；不得修改 Audit |

建議拆分 `trial:read/write/correct/reopen`、`cae:read/import/archive`、`hmi:read/review`、`artifact:read/metadata-write/download`、`rule:author/review/approve/publish`、`knowledge:author/review/publish`、`job:read/cancel/retry`、`audit:read/export`、`lineage:read`。Demo 可簡化角色映射，但 API 不應永久綁在單一 `engineering-data:manage`。

---

## 九、分階段實施計畫

每個 Phase 必須依序完成：

```text
需求／Contract 確認 → 實作 → 單元測試 → API／整合測試
→ 前端互動測試 → Docker／Sites Demo smoke test → 文件更新
→ 確認 git diff → 單一 Phase Git commit
```

### Phase H0 — 基線與契約盤點

- 建立 API／Model／UI coverage matrix。
- 記錄 endpoint、permission、lifecycle、payload 與缺欄位。
- 定義 List Summary、Detail、Audit、Lineage、Error Contract。
- 建立完整 Trial、CAE、HMI、CAD、Knowledge、Rule fixtures。

驗收：OpenAPI／型別／實際 payload 一致，列出所有 API 調整，現有測試通過。

建議 commit：`docs(history): define data history contracts and coverage baseline`

### Phase H1 — 歷史資料中心與共用 UI

- 新增 `/data` routes、DataTable、DetailDrawer、RecordHeader、DetailTabs、PropertyGrid。
- URL 保存 ID、tab、page、filters。
- 完成 loading、empty、error、unauthorized、archived 狀態。
- 中英 i18n、鍵盤操作、響應式設計。

驗收：選取、返回、重新整理不遺失狀態；Drawer、完整頁與 deep link 正常。

建議 commit：`feat(web): add historical data center foundation`

### Phase H2 — Trial、CAE、HMI 唯讀詳細檢視

- Trial 顯示 Runs、Parameters、Defects、Actions、Corrections、Provenance。
- CAE 顯示 Runs、Settings、Results、Quality、Source、Comparisons。
- HMI 顯示歷史、圖片、Fields、Corrections、Exports、Profile。
- 清單採 summary payload，詳細內容按需載入。

驗收：任一既有記錄均可完整查看；refresh 保持 record/tab/run；原始結果唯讀。

建議 commit：`feat(history): add trial cae and hmi detail views`

### Phase H3 — Registry 與 CAD 版本歷史

- Project、Part、Mold、Revision、Artifact、Version、CADModel、FeatureSet、Job 詳細頁。
- 補 ProductPart Detail/PATCH。
- 3D 預覽、下載、版本選擇、quality／quarantine、Lineage、分析 links。

驗收：Mold 到 ArtifactVersion、Job 與分析結果可完整追蹤，舊檔不可被覆寫。

建議 commit：`feat(history): add registry cad version and lineage views`

### Phase H4 — 受控編輯、Correction 與生命週期

- Trial Draft／Reopened editor、Process child editor、Closed correction wizard。
- CAE 新 Run 匯入 UI；HMI Profile Draft editor 與 review history。
- Registry 安全欄位、Artifact metadata／quality／archive 操作。
- `row_version`、409 UI、Reason、impact preview、Audit。

驗收：允許修改成功且有 Audit；禁止操作前後端均拒絕；並行編輯不覆寫歷史。

建議 commit：`feat(governance): add controlled historical data editing`

### Phase H5 — Rule 與 Knowledge 版本管理

- Rule selector、Draft editor、validation、workflow、version diff。
- Knowledge pagination、內容、Chunk、metadata、download、citation、new version。
- Published 內容只能 Clone／supersede。

驗收：新版本不破壞舊 Review／Citation；版本差異清楚可讀。

建議 commit：`feat(governance): add rule and knowledge version management`

### Phase H6 — 分析、Job、Audit 與 Lineage 中心

- 所有 derived analysis 歷史、Detail、Rerun、Compare、Archive。
- Job history、Event、Retry／Cancel。
- Read-only Audit API／UI、authorized export。
- Normalized Lineage API、graph＋table。

驗收：由結果可追蹤輸入、版本、Job、規則／模型與 Actor；Audit 永遠不可修改。

建議 commit：`feat(history): add analysis jobs audit and lineage center`

### Phase H7 — 效能、批次與 Enterprise 準備

- 所有清單 server-side pagination/filter/sort 與索引。
- N+1、nested serialization、下載及 3D asset 效能。
- 批次匯入 dry run、mapping、validation、reconciliation。
- 受控批次封存；Retention、legal hold、DLP、SIEM。
- Public Demo 與 Company Connector 的 scope／index／cache／export 隔離。

驗收：目標資料量達到 p95；批次失敗可回復；Public 與 Company 資料不混用。

建議 commit：`feat(enterprise): harden history management for company data`

---

## 十、測試與驗收策略

### 10.1 後端

- List／Detail payload、filter、sort、page、permission。
- Lifecycle transition、Draft update、new version、Correction、archive／restore。
- `row_version` conflict、歷史結果與 Audit immutable。
- Reference impact、禁止刪除、Public／Company scope isolation。

### 10.2 前端

- 清單、篩選、排序、分頁、空狀態。
- Drawer、Detail、tab、deep link、refresh、browser back。
- Trial／CAE／HMI nested content。
- Edit、validation、cancel、save、409 conflict。
- Version selector、Diff、Correction timeline、role-based actions。
- i18n 與日期／數值／單位格式。

### 10.3 E2E

1. Trial 詳細 → Closed correction → Audit。
2. CAE 選 Run → 看 Result → 匯入新 Run → 舊 Result 不變。
3. HMI 原圖 → 覆核 → 匯出 → correction/export 歷史。
4. Mold → Revision → ArtifactVersion → Preview → Job → Analysis。
5. Published Rule／Knowledge 修改被拒 → 建立新版本 → 舊結果可重現。
6. 兩人同時修改 → 第二人收到 409 並可比較。
7. Viewer、Engineer、Approver、Auditor、Admin 權限與 SoD。

### 10.4 每階段完成條件

- 單元、API、前端與 E2E 測試通過。
- Docker Compose smoke test 通過。
- Sites Demo deep link、登入及外網操作不退化。
- MCP 既有工具 schema 與行為不被破壞。
- 中英文 UI、文件、型別與 migration 完成。
- Git worktree 僅含該階段預期變更，再建立單一 commit。

---

## 十一、非功能需求

- 清單 API Demo p95 ≤ 800 ms；Enterprise 目標 p95 ≤ 1.5 s。
- 一般詳細頁 p95 ≤ 1.5 s；3D／文件 lazy load。
- 預設 page size 25，最大 100；搜尋 debounce 並取消過期 request。
- 所有 detail、download、audit、lineage 執行 object-level authorization。
- 文件預覽防 XSS；下載不暴露實體路徑；Audit payload 遮蔽 secret。
- 鍵盤可操作 Drawer、Dialog、Tabs、Table；不只用顏色表達狀態。
- 工程數值顯示單位；未知單位明確標示。

---

## 十二、風險與緩解

| 風險 | 緩解方式 |
|---|---|
| 把歷史資料當一般 CRUD | 狀態矩陣、新版本、Correction、immutable API |
| 清單回傳完整 nested payload | Summary DTO＋Detail lazy load＋pagination |
| Drawer 承載過多內容 | Drawer 僅 quick view，完整內容使用 route |
| 權限只在前端控制 | API object-level permission＋狀態驗證 |
| 文件預覽 XSS | 預設純文字、sanitization、CSP |
| Audit 洩漏敏感資料 | Event allowlist＋redaction |
| API payload 不一致 | H0 coverage matrix＋contract tests |
| Demo 與公司資料混用 | scope、dataset、index、cache、export 全鏈隔離 |

---

## 十三、優先順序與預估

| 優先級 | 階段 | 建議工期 | 主要價值 |
|---|---|---:|---|
| 最高 | H0 基線與契約 | 1–2 天 | 避免 API 與 UI 重工 |
| 最高 | H1 歷史中心基礎 | 3–5 天 | 一致瀏覽體驗與 deep link |
| 最高 | H2 Trial／CAE／HMI | 4–6 天 | 直接解決只有摘要的問題 |
| 高 | H3 Registry／CAD | 4–6 天 | 工程資料鏈與版本追蹤 |
| 高 | H4 受控編輯 | 5–8 天 | 安全維護與 Correction |
| 中高 | H5 Rule／Knowledge | 5–8 天 | 版本治理與可重現性 |
| 高 | H6 Analysis／Job／Audit／Lineage | 5–8 天 | 稽核、除錯及溯源 |
| 後續 | H7 Enterprise | 依資料量拆分 | 批次、公司資料與合規 |

---

## 十四、已採用的預設決策

1. 詳細頁採 Quick Drawer＋獨立完整路由，不採純 Accordion。
2. Knowledge 預設純文字；可信 Markdown 經 sanitization 後才渲染。
3. Demo 可簡化角色映射，但 API 採細粒度權限及 SoD。
4. 歷史全量保存，以伺服器端分頁顯示，不做最近 20 筆硬限制。
5. 先完成唯讀詳細檢視，再加入受控編輯。
6. 允許同步補足 Detail、Audit、Lineage、pagination 與 contract 缺口。
7. 初期不提供一般硬刪除；採封存、停用、退役、隔離或版本取代。
8. Audit／Lineage 不是最低優先附加功能；受控編輯上線時即必須記錄，集中 UI 於 H6 完成。

---

## 十五、開始實作前檢查清單

- [x] 確認 H0 coverage matrix 與 API contract。
- [x] 確認目前前後端 baseline tests；Docker／Sites Demo／MCP smoke test 於各實作階段持續驗證。
- [ ] 建立完整 Trial、CAE、HMI、CAD、Knowledge、Rule fixtures。
- [ ] 確認各 entity lifecycle 與可修改欄位。
- [ ] 確認 Demo role mapping 與 Enterprise permissions。
- [ ] 確認 deep link 不包含敏感資訊。
- [ ] 確認 Audit redaction 與不可變策略。
- [ ] 確認每個 Phase 的測試、文件與 Git commit 邊界。

完成以上檢查後，建議從 **Phase H0 → H1 → H2** 開始，先讓所有使用者能穩定找到並查看完整歷史資料，再逐步開放受治理的修改能力。
