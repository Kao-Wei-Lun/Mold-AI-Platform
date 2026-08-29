# 模具規定與工程資料新增／匯入強化需求規格書

版本：1.0 Draft  
日期：2026-08-29  
狀態：待評審；作為下一階段 Demo 完善與 Enterprise 延伸基線  
適用系統：Mold AI Platform `0.13.x-demo` 之後版本

## 1. 文件目的

本文件定義 Mold AI Platform 下一階段的兩項核心改良：

1. 將目前偏向唯讀瀏覽、版本流程及 Raw JSON 編輯的「模具規定」改造成可依模具類型、產品、材料及製程管理的完整治理中心。
2. 將分散在 CAD、Knowledge、HMI、Mold Registry、Engineering Data 與 Enterprise 頁面的新增能力，整合成可發現、可驗證、可追蹤的「新增資料／匯入中心」。

本文件延續下列既有原則：

- Draft 可以在權限範圍內修改；Published、Released、Closed 及既有分析輸入不可被靜默覆寫。
- 原始檔、歷史規則、AI／工程結果、AuditEvent 與 JobEvent 不可修改。
- 高風險刪除以 Archive、Retire、Supersede 或 Correction 取代 Hard Delete。
- Web UI 是主要管理介面；ChatGPT App／MCP 提供查詢、說明、狀態及受控 deep link。
- Demo 與 Enterprise 共用 Canonical Contract，正式化時主要替換 Connector、Storage、Identity 與部署方式。

## 2. 術語與 UI 命名決策

### 2.1 「主資料」名稱問題

「主資料」是 Master Data 的直譯，但一般工程使用者不一定知道它包含資料集、材料、機台、缺陷、位置或單位，容易誤認為「主要專案資料」或「模具主檔」。

本文件建議 UI 改用：

> **工程基礎資料**

英文顯示名稱建議為：

> **Engineering Reference Data**

不建議 UI 使用「Engineering Master Data」，因為仍保留使用者不熟悉的 Master Data 術語。

### 2.2 建議畫面文字

| UI 位置 | 建議文字 |
|---|---|
| 導覽項目 | 工程基礎資料 |
| 頁面標題 | 工程基礎資料與選項 |
| 頁面說明 | 管理資料集、產品類型、模具類型、材料、機台、缺陷、位置、單位及其他受控工程選項。 |
| 新增按鈕 | 新增工程選項 |
| 空狀態 | 尚無符合條件的工程基礎資料。您可以清除篩選或新增第一筆受控選項。 |
| 權限名稱（使用者可見） | 檢視工程基礎資料／管理工程基礎資料 |

### 2.3 相容性原則

- 現有 route `/governance/master-data`、API `/api/v1/master-data`、permission `master-data:*` 及程式 Model `MasterDataItem` 在第一階段不更名。
- 只先修改使用者可見文字、i18n、說明與文件，避免造成 API、MCP、測試及既有 deep link 的破壞性變更。
- 若未來要更名 API，必須先提供新舊 route 並存、deprecation header、遷移期與契約測試。

## 3. 現況盤點

### 3.1 已存在的能力

| 資料領域 | 目前能力 |
|---|---|
| 工程基礎資料 | Dataset、Product Type、Material、Machine、Defect、Location、Unit 的新增、修改、停用與封存 |
| Mold Registry | Project、Product Part、Mold、Mold Revision 的建立與受控修改 |
| CAD | STEP／STP／STL 上傳、解析、預覽、版本、特徵與索引 |
| 模具規定 | Profile Clone、Draft、Validation、Review、Approve、Publish、Retire、Diff 與 Audit |
| Knowledge | TXT／Markdown 上傳、版本、索引、發布流程、搜尋及 Citation |
| Trial | Trial Case 建立、Process Run、Correction、Close／Reopen／Archive |
| CAE | Study 建立、Run 匯入、Result、Comparison 與 Archive／Restore |
| HMI | PNG／JPG 上傳、OCR、人工覆核、Profile Version 與 Excel Export |
| Enterprise Import | Master Data／Project 的 JSON Dry Run、Commit、Idempotency 與 Reconciliation |
| 歷史治理 | Detail、版本、Job、Audit、Lineage、Enterprise Policy 與受控批次封存 |

### 3.2 使用者感受到功能不完整的原因

1. 新增入口散落在多個工作區，沒有統一的「新增資料」入口。
2. CAD、Knowledge、HMI 有上傳；Trial、CAE、Registry 多為表單；Enterprise Import 只接受 Raw JSON，體驗不一致。
3. 模具規定主頁使用第一個 Profile 作為主要顯示來源，缺少清楚的 Profile／版本選擇器。
4. 規則 Draft 編輯藏在歷史資料詳細頁，而且要求使用者修改 JSON Array。
5. `Mold.mold_type` 仍偏向自由文字；工程基礎資料中沒有可管理的 Mold Type。
6. `RuleProfile.product_scope`、`material_scope` 與 `RuleVersion.applicability` 已存在，但沒有一致的 UI、衝突檢查與解析說明。
7. Trial 與 CAE 雖有建立 API，工程頁仍以 Demo Fixture 為主要起點，容易讓使用者誤認只能使用內建資料。
8. 目前批次匯入只支援 `master_data` 與 `projects`，尚無 CSV／XLSX 上傳、欄位 Mapping 或逐列錯誤報告。

## 4. 目標與非目標

### 4.1 目標

- `RDI-GOAL-01`：使用者能在任意主要頁面找到「＋新增資料」，並依資料類型進入正確流程。
- `RDI-GOAL-02`：模具規定能依模具類型、產品類型、材料、製程、Scope 與有效日期套用。
- `RDI-GOAL-03`：Rule Author 不需要編輯 Raw JSON 即可完成 Draft 規則新增與修改。
- `RDI-GOAL-04`：每次 Design Review 均能說明為何選中某一規則 Profile，並固定保存其版本。
- `RDI-GOAL-05`：支援單筆表單、檔案上傳、批次匯入及未來 Connector 四種資料來源。
- `RDI-GOAL-06`：所有匯入先 Dry Run，提交後可追蹤 Job、逐筆結果、Audit、Lineage 與 Reconciliation。
- `RDI-GOAL-07`：新增資料可在歷史資料中心立即查看、關聯、版本化或受控封存。
- `RDI-GOAL-08`：外網 Sites Demo 與 ChatGPT MCP deep link 能開啟相同的資料與規則上下文。

### 4.2 非目標

- Demo 不宣稱直接解析未驗證的 Moldflow 原生專案檔、PDM 私有格式或公司內部資料庫。
- 不允許使用者直接修改資料庫或已發布規則的 Raw JSON。
- 不提供任意 Hard Delete 或繞過 Audit 的管理員捷徑。
- 第一階段不支援跨 Scope 的批次搬移或部分成功提交。
- 第一階段不透過 MCP 直接發布規則、提交批次匯入或執行不可逆操作。

## 5. 目標資訊架構

```text
工程工作區
├─ CAD
├─ 相似搜尋
├─ 設計審查
├─ Trial / Process
├─ CAE / Moldflow
└─ HMI → Excel

資料管理
├─ 資料總覽
├─ 新增資料
├─ 匯入中心
├─ 模具登錄
├─ 歷史資料
└─ Job / 匯入紀錄

工程治理
├─ 模具規定
├─ 知識文件
├─ 工程基礎資料
└─ Audit / Lineage

系統管理
├─ 帳號與權限
├─ Connector
├─ Enterprise Policy
└─ 系統狀態
```

### 5.1 建議 route

| Route | 用途 |
|---|---|
| `/data/new` | 全域新增資料選擇器 |
| `/data/imports` | 匯入工作清單、狀態及錯誤 |
| `/data/imports/new` | 建立新的匯入工作 |
| `/data/imports/{batch_id}` | Mapping、Dry Run、Commit、Reconciliation 與 Audit |
| `/governance/reference-data` | 新的使用者友善 route；初期可導向現有 `/governance/master-data` |
| `/governance/rules/new` | 建立 Rule Profile |
| `/governance/rules/{profile_id}` | Profile 詳細資料 |
| `/governance/rules/{profile_id}/edit` | Draft 結構化編輯器 |
| `/governance/rules/{profile_id}/test` | 規則驗證與工程測試 |
| `/governance/rules/{profile_id}/diff` | 版本比較 |

## 6. 工程基礎資料需求

### 6.1 資料種類

現有種類保留並增加：

| 種類 | Demo | 說明 |
|---|---|---|
| dataset | 已有 | 資料來源及用途分類 |
| product_type | 已有 | 產品類別 |
| material | 已有 | 材料或材料牌號 |
| machine | 已有 | 成型機或設備 |
| defect | 已有 | 缺陷代碼 |
| location | 已有 | 廠區、缺陷位置或受控位置 |
| unit | 已有 | Canonical Unit |
| mold_type | **新增，MUST** | 模具類型及子類型 |
| molding_process | **新增，MUST** | 射出、壓縮、包覆等製程類型 |
| rule_category | **新增，SHOULD** | 模具設計、產品設計、材料、製程、品質等規則分類 |
| solver | **新增，SHOULD** | CAE Solver 與版本家族 |
| steel_grade | Enterprise MAY | 模具鋼材牌號 |
| resin_family | Enterprise MAY | 樹脂家族與牌號 Mapping |

### 6.2 Mold Type 初始資料

Demo 應提供可修改的初始選項，但不得硬寫在前端：

- 一般射出模具
- 二板模
- 三板模
- 熱澆道模具
- 埋入／包覆成型模具
- 旋牙／退牙模具
- 多穴模具
- Family Mold

`attributes` 可保存 parent type、process family、hot runner、unscrewing、multi-cavity 等結構化屬性。

### 6.3 功能需求

- `RDI-REF-01`：Data Steward 應能新增、修改、停用與封存工程基礎資料。
- `RDI-REF-02`：Canonical Code 建立後不可修改；語意重大改變須新增另一筆 Code。
- `RDI-REF-03`：停用項目不得出現在新表單，但歷史資料仍顯示原始 Code 與名稱。
- `RDI-REF-04`：Mold Registry 的 Mold Type 必須使用受治理選項，不再接受任意自由文字。
- `RDI-REF-05`：規則、Trial、CAE、CAD Metadata 及搜尋篩選必須共用相同選項來源。
- `RDI-REF-06`：每筆資料須顯示引用數量、來源、有效日期、版本衝突及 Audit。
- `RDI-REF-07`：UI 必須顯示資料種類的人類可理解說明及範例。

## 7. 模具規定資料模型

### 7.1 保留的核心模型

- `RuleProfile`：一組可發布、可解析的規則集合版本。
- `RuleVersion`：Profile 中的一條工程規則版本。
- `ReviewRun.profile`：歷史 Design Review 使用的確切 Profile。
- `ReviewFinding.rule_version`：歷史 Finding 使用的確切規則。

### 7.2 建議新增或擴充欄位

`RuleProfile` 應增加：

- `priority`
- `is_default`
- `effective_from`
- `effective_to`
- `scope`／`classification`
- `resolution_status`
- `applicability_checksum`

新增 `RuleProfileApplicability`：

| 欄位 | 說明 |
|---|---|
| `profile` | 所屬 Rule Profile |
| `dimension` | mold_type、product_type、material、molding_process、project、location |
| `value_code` | 工程基礎資料或 Canonical Entity Code |
| `match_mode` | include／exclude |
| `created_at` | 建立時間 |

`RuleVersion` SHOULD 增加或明確化：

- `category_code`
- `title_zh_tw`／`title_en`
- `description_zh_tw`／`description_en`
- `tags`
- `evidence_requirements`
- `reference_locator`

### 7.3 相容性遷移

1. 先增加新欄位與表，不移除 `product_scope`、`material_scope`、`applicability`。
2. 將現有 JSON Scope backfill 至 `RuleProfileApplicability`。
3. 執行雙讀比對並產出 reconciliation report。
4. resolver 切換至新表後，舊欄位進入唯讀相容期。
5. 至少一個穩定 release 及 restore 測試後才考慮移除舊欄位。

## 8. 模具規定解析需求

### 8.1 解析順序

```text
模具類型＋產品類型＋材料＋製程
                  ↓ 找不到
模具類型＋產品類型＋材料
                  ↓ 找不到
模具類型＋產品類型
                  ↓ 找不到
模具類型
                  ↓ 找不到
Default Profile
```

- `RDI-RSL-01`：只有 Published、在有效期間內且 Scope 可見的 Profile 可被選中。
- `RDI-RSL-02`：先以 applicability specificity 排序，再比較明確 priority。
- `RDI-RSL-03`：兩個候選具有相同 specificity 與 priority 時必須 fail closed。
- `RDI-RSL-04`：Design Review 必須保存候選、選中結果、原因、輸入 Context 與 checksum。
- `RDI-RSL-05`：若使用者具有權限，可人工指定另一個 Published Profile，但必須填寫原因並寫入 Audit。
- `RDI-RSL-06`：歷史 Review 不得因新 Profile 發布而改變。
- `RDI-RSL-07`：UI 必須顯示「為何套用此規則版本」。

## 9. 結構化規則編輯器

### 9.1 Profile 建立方式

Rule Author 應能選擇：

1. 從空白建立。
2. 從公司核准範本建立。
3. Clone 既有 Published／Retired Profile。

### 9.2 Rule Editor 欄位

**基本資料**

- Rule ID、版本、中英文名稱及說明
- 規則分類、啟用狀態、排序與標籤

**判定條件**

- Evaluator：只允許受控 Evaluator Registry
- Operator：`≤`、`≥`、`=`、range 或 evidence-dependent
- Threshold、Unit、Tolerance
- Severity、Risk Type

**適用條件**

- Mold Type、Product Type、Material、Process
- 必要幾何證據與排除條件

**工程處置**

- Recommendation
- Reference Document、Revision、Classification、Section／Page

### 9.3 編輯原則

- `RDI-RUL-01`：一般 Rule Author 不需直接編輯 JSON。
- `RDI-RUL-02`：Draft 可以新增、複製、修改、停用、重新排序或移除 Rule。
- `RDI-RUL-03`：Published Rule 不可原地修改；編輯動作必須建立新 Draft Profile。
- `RDI-RUL-04`：Rule Author 不得核准自己建立或最後修改的版本。
- `RDI-RUL-05`：發布前必須通過 evaluator、operator、unit、reference、重複 Rule ID 及 applicability 衝突驗證。
- `RDI-RUL-06`：發布前應顯示受影響 Mold、Revision、CAD 與歷史 Review 數量。
- `RDI-RUL-07`：Raw JSON 只在 Platform Admin 進階模式顯示，並使用同一套 server-side validator。

### 9.4 詳細頁頁籤

- Overview
- Applicability
- Rules
- Test cases
- Version diff
- Workflow
- Usage
- Audit / Lineage

## 10. 統一新增資料入口

### 10.1 全域按鈕

所有主要頁面右上角 SHOULD 顯示「＋新增資料」。按下後顯示：

- 新增 Project／Part／Mold／Revision
- 上傳 CAD
- 新增 Trial／Process Run
- 建立 CAE Study／匯入 Run
- 上傳 HMI 圖片
- 上傳 Knowledge
- 建立／匯入模具規定
- 新增工程基礎資料
- 批次匯入

只顯示使用者有權限執行的項目；API 仍需獨立驗證權限。

### 10.2 四種來源

| 來源 | 適用情境 |
|---|---|
| Manual form | 單筆 Project、Mold、Trial、CAE Study、工程選項 |
| File upload | CAD、Knowledge、HMI、CAE Result |
| Batch import | CSV、XLSX、JSON 多筆資料 |
| Connector sync | Enterprise PDM、PLM、MES、QMS、Moldflow、SharePoint 等 |

## 11. 匯入中心流程

### 11.1 標準流程

```text
選擇資料類型
  → 下載範本或選擇來源
  → 設定 Scope、Classification 與關聯
  → 上傳檔案
  → 欄位 Mapping
  → Dry Run
  → 檢視新增／更新／略過／錯誤
  → 確認提交
  → 非同步 Job
  → Reconciliation、Audit、Lineage
```

### 11.2 建議資料模型

- `IngestionBatch`：一次匯入的整體狀態、Domain、Scope、Schema Version、Idempotency Key。
- `IngestionSourceFile`：原始檔 ArtifactVersion、SHA-256、MIME、大小及 screening。
- `MappingProfile`：來源欄位至 Canonical 欄位的版本化 Mapping。
- `IngestionIssue`：列號、欄位、錯誤代碼、訊息、原值及建議。
- `IngestionRecordResult`：每筆 created、updated、skipped、failed 與 Entity ID。
- `ReconciliationReport`：來源總數及落地結果是否平衡。
- `EntityAttachment`：原始檔、圖片、報告與 Mold／Revision／Trial／CAE 的關聯。

### 11.3 狀態機

```text
draft → uploaded → mapping_required → validating
      → validation_failed
      → validated → queued → committing
      → committed
      → failed / cancelled
```

已 committed 的 Batch 不可再次提交；同一 Idempotency Key 重送必須回傳原 Batch。

### 11.4 驗證

- 檔名、Extension、MIME 與內容簽章。
- 空檔、大小、惡意測試簽章、Path Traversal、Archive Bomb。
- Schema Version、必填欄位、型別、長度及日期。
- Canonical Code、Foreign Key、Unit Conversion 與生命週期。
- 重複 Canonical ID、Source ID、Source Version、SHA-256。
- Scope、Classification、DLP 與操作者權限。
- Excel Formula Injection 及不安全連結。
- Row Count、Header、Hidden Sheet 及巨集。
- Source Count 與 Reconciliation Balance。

Dry Run 不得建立 Domain Entity；只允許建立匯入工作、原始 Artifact、驗證問題與 Audit。

### 11.5 Commit Policy

- Demo 預設使用整批原子提交。
- 任一 Blocking Issue 存在時不得 Commit。
- 第一階段不提供「只匯入有效列」。
- Commit 必須由背景 Job 執行並具備 retry-safe、idempotent 與 stale-job recovery。
- Enterprise 可另行評審 Maker／Checker 及雙人核准。

## 12. 支援格式與階段

| Domain | Demo MUST | Demo SHOULD | Enterprise MAY |
|---|---|---|---|
| 工程基礎資料 | CSV、XLSX、JSON | Template download | ERP／PDM Connector |
| Project／Part／Mold／Revision | CSV、XLSX | Relationship validation | PDM／PLM Connector |
| CAD | STEP、STP、STL | 新 Artifact／新 Version 選擇 | Parasolid、JT、Native CAD Connector |
| 模具規定 | XLSX、CSV、JSON | Preview and conflict report | 公司規範資料庫 Connector |
| Knowledge | TXT、Markdown | PDF、DOCX（完成安全 Parser 後） | SharePoint／File Server Connector |
| Trial／Process | XLSX、CSV、JSON | Evidence attachment | MES／SPC／Trial DB Connector |
| CAE | Summary CSV、XLSX、JSON | Result image/report | Moldflow 等原生 Connector |
| HMI | PNG、JPG | Batch upload | Machine screenshot Connector |
| 帳號 | 管理員手動建立 | — | IdP／SCIM |

不得在 Parser、授權及 Golden Samples 未通過驗證前宣稱支援 proprietary format。

## 13. 各 Domain 詳細需求

### 13.1 Mold Registry 與 CAD

- `RDI-MOLD-01`：Mold Type 必須選自工程基礎資料。
- `RDI-MOLD-02`：建立 Revision 後可直接進入 CAD 上傳。
- `RDI-MOLD-03`：CAD 上傳時可選擇新 Artifact 或既有 Artifact 的新 Version。
- `RDI-MOLD-04`：替換檔案不得覆寫舊 ArtifactVersion。
- `RDI-MOLD-05`：Registry XLSX 匯入必須驗證 Project → Part → Mold → Revision 的階層。
- `RDI-MOLD-06`：封存前顯示 Trial、CAE、Review、Artifact 與 Knowledge 引用影響。
- `RDI-MOLD-07`：CAD 上傳必須明確區分「快速分析」與「正式歸檔」；快速分析不得強迫建立 Mold Revision，正式歸檔則必須關聯有效 Revision。
- `RDI-MOLD-08`：快速分析仍須建立 immutable ArtifactVersion、Checksum、Job 與 Lineage，並標記為 `unassigned`，不得當成未受追蹤的暫存檔。
- `RDI-MOLD-09`：快速分析可執行預覽、幾何解析、相似度與通用規則審查；模具專屬規則、正式 Trial／CAE 關聯及發布證據必須先完成受稽核的 Revision 關聯。
- `RDI-MOLD-10`：API 必須保存使用者選擇的 `ingestion_mode` 與 `governance_status`，Idempotency Replay 不得改變原始治理語意。

### 13.2 Trial／Process

- `RDI-TRI-01`：提供分步式 Trial 建立表單。
- `RDI-TRI-02`：允許新增多個 Process Run、Parameter、Defect 及 Corrective Action。
- `RDI-TRI-03`：Parameter 與 Unit 必須使用受治理 Code。
- `RDI-TRI-04`：支援 XLSX／CSV／JSON 匯入及逐列錯誤。
- `RDI-TRI-05`：Closed Trial 只能建立 Correction 或受控 Reopen。
- `RDI-TRI-06`：圖片、報告及量測證據應以 Artifact 關聯。

### 13.3 CAE

- `RDI-CAE-01`：建立 Study 後可建立或匯入 Run。
- `RDI-CAE-02`：保存 Solver、Version、Mesh、Material Model、Boundary、Process Setting 與 Unit System。
- `RDI-CAE-03`：結構化 Result 與原始摘要檔分別保存，並具完整 Lineage。
- `RDI-CAE-04`：原始 Result 不可修改；新分析應建立新 Run。
- `RDI-CAE-05`：Comparison 前必須執行相容性檢查。

### 13.4 Knowledge

- `RDI-KNW-01`：上傳、版本、內容、Chunk、索引、Citation 與發布流程整合在同一詳細頁。
- `RDI-KNW-02`：上傳時可指定 Mold Type、Product Type、文件類型、Authority 及有效日期。
- `RDI-KNW-03`：PDF／DOCX 必須經安全 Parser、Prompt Injection Scan 與 quarantine gate。
- `RDI-KNW-04`：新版本不得改寫歷史 Citation。

### 13.5 HMI

- `RDI-HMI-01`：上傳時可關聯 Machine、Mold Revision、Trial 與 HMI Profile。
- `RDI-HMI-02`：支援多圖片批次上傳與逐張 Job 狀態。
- `RDI-HMI-03`：Raw OCR 不可修改；人工決策追加保存。
- `RDI-HMI-04`：未完成必要人工確認不得 Export。
- `RDI-HMI-05`：每個 Excel Export 必須保存 Template Version、Source Hash 與 Review Snapshot Hash。

## 14. API 需求

### 14.1 Rule API

現有 API 保留，新增或擴充：

```text
POST  /api/v1/rule-profiles                     create blank/template/clone
GET   /api/v1/rule-profiles/{id}/applicability
PUT   /api/v1/rule-profiles/{id}/applicability
GET   /api/v1/rule-profiles/{id}/rules
POST  /api/v1/rule-profiles/{id}/rules
PATCH /api/v1/rule-profiles/{id}/rules/{rule_id}
POST  /api/v1/rule-profiles/{id}/rules/{rule_id}/clone
POST  /api/v1/rule-profiles/{id}/validate
POST  /api/v1/rule-profiles/{id}/impact-preview
POST  /api/v1/rule-resolution/preview
```

Draft 內移除 Rule 應是移除該 Draft Profile 的 membership／版本，不得刪除被歷史結果引用的 RuleVersion。

### 14.2 Ingestion API

```text
GET   /api/v1/ingestions
POST  /api/v1/ingestions
GET   /api/v1/ingestions/{id}
POST  /api/v1/ingestions/{id}/files
PUT   /api/v1/ingestions/{id}/mapping
POST  /api/v1/ingestions/{id}/validate
GET   /api/v1/ingestions/{id}/issues
POST  /api/v1/ingestions/{id}/commit
POST  /api/v1/ingestions/{id}/cancel
GET   /api/v1/ingestions/{id}/reconciliation
GET   /api/v1/import-templates/{domain}
```

所有 response 必須包含 `schema_version`、Canonical ID、typed error、request／correlation ID 及允許時的 deep link。

## 15. 帳號、角色與權限

| 角色 | 主要能力 |
|---|---|
| Viewer | 查看授權資料 |
| Engineer | 建立 CAD、Trial、CAE、HMI 資料 |
| Data Steward | 管理工程基礎資料、Registry 與 Mapping |
| Import Operator | 建立、上傳及驗證匯入工作 |
| Import Approver | Enterprise 批次 Commit 核准 |
| Rule Author | 建立及編輯 Draft 規定 |
| Rule Approver | 核准及發布規定 |
| Knowledge Author | 上傳與維護文件 |
| Auditor | 查看 Audit、Lineage 及 Reconciliation |
| Platform Admin | 帳號、Scope、Connector 與系統設定 |

建議新增 permission：

- `ingestion:read`
- `ingestion:create`
- `ingestion:validate`
- `ingestion:commit`
- `ingestion:cancel`
- `ingestion:template-manage`
- `rule-resolution:preview`
- `rule-impact:read`

權限必須先套用 Data Scope，再進行搜尋、計數、驗證或 Commit，避免跨 Scope 側通道。

## 16. Audit、Lineage 與版本

每次變更至少記錄：

- Actor、Role、Data Scope
- Action、Reason、Request ID、Correlation ID
- Entity、Version、Before／After
- Source File SHA-256、Schema Version、Mapping Version
- Job ID、Parser／Evaluator Version
- Validation、Commit 及 Reconciliation Result
- Rule Resolution Candidate、Winner 與 Reason

AuditEvent 永久唯讀；匯入原始檔、Published Rule、Review Result 及 Citation Target 不可覆寫。

## 17. MCP 與 ChatGPT App

### 17.1 建議新增唯讀 MCP Tool

- `list_rule_profiles`
- `get_rule_profile`
- `explain_rule_applicability`
- `resolve_rule_profile`
- `get_ingestion_status`
- `get_ingestion_issues`
- `open_data_upload`

### 17.2 安全邊界

- MCP 第一階段不得直接 Publish Rule、Commit Import 或 Hard Delete。
- ChatGPT 可說明目前 Context 會套用哪一版規則，並提供 Web deep link。
- 上傳、Mapping、核准及 Commit 必須在登入後的 Web UI 完成。
- MCP 回覆只能包含操作者 Scope 內的資料及統計。

## 18. 分階段實作計畫與 Git Gate

### Phase 0：文件與契約基線

交付：

- 本 SRS 評審版。
- Mold Type、Rule Applicability、Ingestion Contract、權限矩陣。
- 各 Domain Import Template Draft。
- Migration、Feature Flag、Backup／Restore 與 Rollback 計畫。

Gate：Markdown link／encoding 檢查、現有 regression baseline、文件 commit。

### Phase 1：工程基礎資料與 Rule Resolver

交付：

- UI「主資料」改名為「工程基礎資料」。
- Mold Type、Molding Process 及 Rule Category。
- RuleProfileApplicability 與 Rule Resolver。
- 現有 Demo Profile backfill。
- Design Review Resolution Snapshot。

Gate：Model、Migration、API、Resolver、Scope、衝突及歷史可重現測試通過後 commit。

### Phase 2：結構化模具規定 UI

交付：

- Profile List／Detail／Selector。
- Blank／Template／Clone 建立精靈。
- Applicability Editor、Rule Editor、Validation、Impact Preview、Diff。
- 完整 Draft → Publish Workflow UI。

Gate：Vue tests、i18n、accessibility、typecheck、production build、API regression 通過後 commit。

### Phase 3：統一 Ingestion Foundation

交付：

- 全域「＋新增資料」。
- Ingestion Batch、File、Mapping、Issue、Result 及 Reconciliation。
- `/data/imports` UI、Template Download、Dry Run、Commit、Job Progress。
- Audit、Lineage、Idempotency、stale-job recovery。

Gate：Dry Run 零 Domain 寫入、transaction rollback、duplicate delivery、scope isolation 及 worker recovery 通過後 commit。

### Phase 4A：高優先結構化匯入

交付：

- 工程基礎資料 CSV／XLSX／JSON。
- Project／Part／Mold／Revision CSV／XLSX。
- 模具規定 XLSX／CSV／JSON。
- Trial／Process XLSX／CSV／JSON。

每個 Domain 獨立測試及 commit。

### Phase 4B：檔案及工程結果匯入

交付：

- CAE Summary CSV／XLSX／JSON。
- Knowledge 安全 Parser 擴充。
- HMI Batch Upload。
- CAD 新 Artifact／新 Version 統一流程。

每個 Domain 獨立測試及 commit。

### Phase 5：資料管理 UX 整合

交付：

- 新導覽與 Data Library。
- 所有 Detail Page 的新增、版本、引用、Job、Audit、Lineage 連結。
- 統一 loading、empty、validation、success、error 與 permission state。
- 中英雙語、responsive、keyboard 與 deep link。

Gate：完整 Web suite、build、route/deep-link regression、外網 smoke 通過後 commit。

### Phase 6：安全、效能、備份及外網發布

交付：

- File Security、DLP、Formula Injection、IDOR、CSRF、XSS 測試。
- 10k 列匯入效能與 Job Recovery。
- Backup／Restore、Qdrant rebuild、Audit continuity。
- 單一 Docker image、Sites、HTTPS、MCP、deep link 外網驗收。

Gate：完整 API/Web test、migration drift、lint、build、security smoke、performance、external smoke 通過後 commit 及發布。

## 19. 測試需求

### 19.1 Unit／Model

- Rule Applicability specificity、priority、effective period 與 conflict。
- Published immutability、clone、checksum 與 row version。
- Mapping、validator、unit conversion、duplicate identity。
- Ingestion state machine、idempotency、reconciliation balance。

### 19.2 API

- 合法及非法 lifecycle transition。
- Session、Role、Scope、IDOR 及 typed error。
- Multipart upload、MIME、size、signature、malware test signature。
- Dry Run、Commit、retry、cancel 及 stale recovery。
- 歷史 Review、Citation、ArtifactVersion 與 RuleVersion reference 不變。

### 19.3 Web

- 全域新增資料選擇器依權限顯示。
- 結構化 Rule Editor 不需 JSON。
- Upload Wizard 的 Back／Forward／Refresh 狀態保持。
- Mapping、Issue navigation、Job progress、success deep link。
- 中文／英文、keyboard、screen reader、mobile layout。

### 19.4 Security

- Cross-scope search、count、facet、validation 及 cache leak。
- CSV／Excel Formula Injection、path traversal、archive bomb、MIME spoof。
- Prompt Injection 文件不得提升權限或觸發未核准 Tool。
- Viewer 透過 UI、API、deep link、MCP 嘗試修改均被拒絕。

### 19.5 效能初始門檻

- 清單 P95 ≤ 1.0 秒；Detail P95 ≤ 1.5 秒。
- 10k row Dry Run／Commit 各 ≤ 60 秒，使用非同步 Job 並回報進度。
- 100 個 Rule Profile 的 resolver P95 ≤ 300 ms。
- Demo 檔案大小沿用並驗證現有政策：CAD 200 MB、Knowledge 5 MB、HMI 10 MB；外網實際上限必須另做 Sites／Tunnel 測試並記錄。

## 20. UAT 驗收情境

- `UAT-RDI-01`：Data Steward 在 Web 新增「三板模」，Mold 建立表單立即可選取。
- `UAT-RDI-02`：Rule Author 建立三板模 Profile，使用結構化表單新增規則，不接觸 JSON。
- `UAT-RDI-03`：Rule Approver 核准發布；作者無法核准自己的版本。
- `UAT-RDI-04`：建立三板模 Mold／Revision 並上傳 STEP，Design Review 自動選中正確 Profile 並顯示原因。
- `UAT-RDI-05`：發布新版規則後，新 Review 使用新版；舊 Review 仍保留原版本與結果。
- `UAT-RDI-06`：上傳 Trial XLSX，Dry Run 指出列號與欄位錯誤且 Trial 資料零寫入。
- `UAT-RDI-07`：修正檔案後 Commit，Trial、Run、Parameter、Defect 與 Lineage 可完整查看。
- `UAT-RDI-08`：重送相同 Idempotency Key 不建立重複資料。
- `UAT-RDI-09`：Viewer 從 UI、API、MCP 嘗試修改資料均被拒絕且留下安全 Audit。
- `UAT-RDI-10`：CAD 新版上傳產生新 ArtifactVersion，舊 Design Review 不被改寫。
- `UAT-RDI-11`：ChatGPT App 查詢規則解析後，可由 deep link 開啟正確 Web Profile／Review／Import Job。
- `UAT-RDI-12`：外網重新整理、切頁、返回後，Wizard、Detail Tab 與選取 Context 不遺失。
- `UAT-RDI-13`：備份／還原後 Entity、Version、Artifact checksum、Lineage、Audit 及停權狀態一致。

## 21. Demo 與 Enterprise 邊界

### 21.1 下一版 Demo 必做

- 工程基礎資料新名稱及 Mold Type。
- Rule Applicability、Resolver、結構化 Rule Editor。
- 全域新增資料入口及 Ingestion Center。
- Master／Registry／Rule／Trial 的 CSV／XLSX／JSON 匯入。
- CAE Summary、Knowledge、HMI、CAD 的一致上傳體驗。
- Job、Audit、Lineage、Reconciliation、權限及外網 deep link。

### 21.2 Enterprise 後續

- 公司 IdP／SSO／SCIM。
- PDM／PLM／MES／QMS／Moldflow／SharePoint Connector。
- Object Storage、正式 Anti-malware、Secret Manager、SIEM Transport。
- 大檔 resumable upload、跨節點 Worker、HA、DR、正式容量測試。
- Maker／Checker、Legal Hold、Retention、DLP 與公司分類政策。

## 22. Definition of Done

每一階段只有在以下條件成立時才可完成：

1. Model、Migration、API、UI、i18n、Audit、Lineage 與文件同步。
2. Demo 舊資料升級與全新安裝均成功。
3. Unit、API、Web、Security-relevant regression 及階段 UAT 通過。
4. `makemigrations --check --dry-run`、lint、typecheck、build、`git diff --check` 通過。
5. 無跨 Scope 洩漏、未授權 mutation、Secret 或未受控 Raw JSON 旁路。
6. 效能未超出門檻，或有量測、原因與核准例外。
7. 備份、還原、失敗重試與回復方式已驗證。
8. 建立可讀且單一目的的 Git commit；不得把多個未驗證階段壓成一筆不透明提交。

## 23. 主要風險與緩解

| 風險 | 影響 | 緩解 |
|---|---|---|
| 每種模具建立完整重複規則 | 維護成本與版本漂移 | 先使用 Template Clone、Diff 與衝突報告；證明需要後再評審規則組合／繼承 |
| Published 規則原地修改 | 歷史 Review 不可重現 | Immutable Published + New Draft Version |
| Applicability 重疊 | Design Review 選錯規則 | Specificity + Priority + Ambiguity Fail Closed |
| 上傳入口多套實作 | 驗證、安全與 UX 不一致 | 共用 Ingestion Contract、Wizard、Job、Audit 與 Lineage |
| Partial Import 造成半套資料 | 關聯及統計污染 | Demo 使用 Atomic Commit |
| Proprietary 格式過早承諾 | Parser、授權及結果錯誤 | 未有 Golden Samples 與契約測試前只標示 Future Connector |
| MCP 執行高風險寫入 | 誤發布或誤匯入 | 第一階段唯讀 Tool + Web deep link + 人工確認 |
| 外網大檔不穩定 | Demo timeout 或中斷 | 量測實際上限；後續導入 resumable upload／object storage |

## 24. 建議開發順序

建議依序執行 Phase 0 → Phase 1 → Phase 2，先解決使用者最直接感受到的「模具規定不能直覺編輯、不能依模具類型選用」問題；其後執行 Phase 3 建立共用 Ingestion Foundation，再逐一新增 Domain Adapter。

不得先為每個頁面各做一套上傳功能，否則 Mapping、Security、Job、Audit、Lineage 與錯誤處理將再次分裂。
