# 模具台帳工作區與完整模具履歷改善規劃

版本：1.1 Implemented Demo Baseline

日期：2026-08-31

狀態：Demo Phase 1–6 已完成

適用範圍：Mold AI Platform Demo 與未來 Enterprise 版本

實作完成日期：2026-09-01

實作紀錄：Phase 1–6 已依本文件完成；各階段均在測試通過後建立獨立 Git Commit。Enterprise Connector、SSO、正式容量規劃與公司資料 UAT 仍屬未來企業導入範圍。

## 1. 文件目的

本文件定義「模具台帳」的產品定位、資訊架構、頁面流程、資料契約、生命週期、權限、稽核、Lineage、匯入整合、測試與分階段實作計畫。

本次改善不重新建立另一套模具資料模型，而是把目前已存在的：

- `Project → ProductPart → Mold → MoldRevision → Artifact → ArtifactVersion` 階層；
- Project、Part、Mold、Revision 建立與更新 API；
- Revision 發布與取代流程；
- CAD 正式歸檔；
- 歷史資料詳細頁；
- Audit、Lineage、權限與 optimistic locking；
- 模具規劃、設計審查、CAE 與試模的關聯；

整理成工程師可搜尋、可瀏覽、可理解、可修改、可追溯的完整模具入口。

核心目標為：

> 使用者從一個模具代碼出發，即可看懂它屬於哪個專案與零件、有哪些版本、每個版本有哪些 CAD、規劃、審查、CAE 與試模紀錄，並在權限允許時完成安全的新增、修改、發布、停用與封存。

## 2. 產品定位與責任邊界

### 2.1 模具台帳的定位

模具台帳是工程資料的「身份與版本中心」，負責回答：

- 這是哪一套模具？
- 屬於哪個專案與產品零件？
- 目前正式使用哪一個模具版本？
- 每個版本有哪些正式 CAD 與工程紀錄？
- 資料從哪個系統而來、由誰建立、何時修改？
- 哪些後續分析使用過這筆資料？

### 2.2 與其他工作區的分工

| 工作區 | 主要責任 | 不應承擔的責任 |
|---|---|---|
| 模具台帳 | 管理模具身份、階層、版本、狀態與工程履歷入口 | 不執行 CAD 幾何分析或規則判定 |
| CAD 與工件 | 上傳、處理、預覽及建立 Artifact Version | 不建立另一套平行模具身份 |
| 模具規劃 | 根據台帳 Context 選出適用標準與工程要求 | 不修改台帳或已發布模具規定 |
| 設計審查 | 對指定 CAD 與規則版本執行確定性檢查 | 不決定模具主檔身份 |
| 工程資料庫 | 跨 Domain 查詢完整歷史資料 | 不取代模具台帳的模具中心導覽 |
| 工程基礎資料 | 管理模具類型、產品類型、材料等受控代碼 | 不保存個別模具實例 |

### 2.3 核心設計決策

1. 模具台帳 MUST 是階層與關聯導向，不再只是四個互不相連的平面清單。
2. 列表與詳細資料 MUST 分離；列表用於尋找，詳細頁用於理解與操作。
3. 新增表單 MUST 由明確按鈕開啟，不得永久占用主要瀏覽空間。
4. 已發布版本的工程身份與歷史關聯 MUST 保持不可變。
5. 系統不得提供會破壞歷史 Lineage 的實體刪除；一般使用者使用停用、退役或封存。
6. 模具代碼、版本代碼及外部來源識別碼建立後不得任意改寫。
7. Demo 與 Enterprise 使用相同 Canonical Contract；Enterprise 主要替換 Connector、Identity、Storage 與部署拓撲。

## 3. 名詞與介面文字

| 技術名稱 | 建議介面名稱 | 說明 |
|---|---|---|
| Project | 專案 | 客戶、產品開發案或內部專案範圍 |
| ProductPart | 產品／零件 | 模具生產的目標產品或零件 |
| Mold | 模具 | 具有穩定模具代碼的實體或受治理工程對象 |
| MoldRevision | 模具版本 | 模具設計或結構的一次正式改版 |
| Artifact | CAD 工件 | 同一工程工件的受治理資料身份 |
| ArtifactVersion | CAD 檔案版本 | 每次實際上傳或處理的不可變檔案版本 |
| Registry | 模具台帳 | 模具身份、版本與關聯工程履歷入口 |
| Released | 正式使用中 | 可供新規劃、審查與正式工程工作選用 |
| Superseded | 已被新版取代 | 仍可追溯，但不再是最新正式版本 |
| Retired | 已停用 | 模具不再供新的工作選用 |
| Archived | 已封存 | 保留歷史但自一般進行中清單隱藏 |

一般 UI 不以 UUID、`row_version`、checksum 或 `source_revision_id` 作為主標題；這些資訊保留在技術資訊、Audit 或 Lineage 區塊。

## 4. 使用者與主要情境

### 4.1 角色

| 角色 | 主要工作 |
|---|---|
| 模具工程師 | 找模具、查看版本、建立草稿版本、開啟 CAD 與規劃 |
| 專案工程師 | 依專案／產品查看模具狀態與進度 |
| 設計工程師 | 查看指定 Revision 與 CAD，啟動設計審查 |
| 製程／CAE／試模工程師 | 從模具版本進入 CAE、製程與試模歷史 |
| Data Steward | 維護階層、主檔品質、Mapping 與匯入批次 |
| Auditor／Viewer | 唯讀查看版本、Audit 與 Lineage |
| Platform Admin | 管理權限與技術性恢復，不參與日常工程核准 |

### 4.2 主要使用情境

- 以模具代碼快速找到目前正式版本。
- 從專案逐層展開到零件、模具、版本與 CAD。
- 建立新專案、零件、模具與第一個草稿版本。
- 從既有正式版本建立下一個草稿版本。
- 查看版本差異、變更摘要與來源。
- 發布新版並自動將前一個 Released 版本標示為 Superseded。
- 查看與指定版本關聯的 CAD、模具規劃、設計審查、CAE 與試模。
- 停用或封存不再使用的模具，保留歷史關聯。
- 從 CSV／XLSX 批次匯入完整階層並處理 Mapping 問題。

## 5. 現況與主要缺口

### 5.1 已完成能力

- Project、Part、Mold、Revision 資料模型與 API。
- 四類資料清單與建立表單。
- Mold Type、Product Type、Material 的受控選項。
- Revision `draft → released → superseded → archived` 生命週期。
- 新 Revision 發布時取代前一個 Released 版本。
- CAD Artifact 與 Mold Revision 關聯。
- `registry:read`、`registry:manage` 權限。
- `row_version` optimistic locking。
- 變更理由與 Audit Event。
- 歷史資料中心內的 Registry 詳細資料與受控修改。
- CSV／XLSX Registry ingestion adapter。

### 5.2 主要缺口

1. 四個頁籤是平面清單，無法直觀看到 Project → Part → Mold → Revision 階層。
2. 清單沒有完整關鍵字搜尋、篩選、排序與分頁。
3. 台帳卡片沒有明確「查看詳細資料」入口。
4. 詳細資料與編輯能力分散在工程資料庫，不易發現。
5. 新增表單永久顯示，瀏覽與新增工作互相干擾。
6. 無法從一個模具頁面集中查看版本、CAD、規劃、審查、CAE 與試模。
7. 新版建立、版本比較、發布與取代關係不夠明確。
8. 停用、退役、封存及其影響缺少一致說明。
9. 匯入中心與台帳頁之間缺少批次狀態、錯誤與修正入口。
10. 大量資料下缺少效能、虛擬化、儲存篩選條件與匯出設計。

## 6. 目標資訊架構

```text
模具台帳
├─ 台帳總覽
│  ├─ 統計與資料品質
│  ├─ 最近更新
│  └─ 需要處理的版本／Mapping
├─ 模具清單（預設入口）
│  ├─ 搜尋與篩選
│  ├─ 階層／表格切換
│  └─ 新增資料
├─ 專案詳細頁
├─ 產品／零件詳細頁
├─ 模具詳細頁
│  ├─ 總覽
│  ├─ 模具版本
│  ├─ CAD 與圖檔
│  ├─ 工程履歷
│  ├─ Lineage
│  └─ Audit
└─ 模具版本詳細頁
   ├─ 版本摘要
   ├─ CAD 與處理狀態
   ├─ 規劃與審查
   ├─ CAE／試模
   ├─ 版本差異
   ├─ Lineage
   └─ Audit
```

### 6.1 建議穩定 Routes

```text
/governance/mold-registry
/governance/mold-registry/projects/{project_id}
/governance/mold-registry/parts/{part_id}
/governance/mold-registry/molds/{mold_id}
/governance/mold-registry/revisions/{revision_id}
```

既有 `/data/molds/{id}` 路由可保留為工程資料庫的通用詳細頁。台帳 Route 與資料庫 Route MUST 共用 API 與元件，不得形成兩份不一致的資料。

## 7. 台帳總覽規格

### 7.1 頁首

頁首建議顯示：

- 標題：`模具台帳`
- 副標題：`管理模具身份、版本與完整工程履歷`
- 主要動作：`＋ 新增資料`
- 次要動作：`批次匯入`、`重新整理`

### 7.2 統計卡片

至少顯示：

- 使用中專案數；
- 使用中模具數；
- 正式版本數；
- 草稿版本數；
- 無 CAD 的正式版本數；
- 待處理 Mapping／資料品質問題數。

統計卡片 SHOULD 可點擊並套用對應篩選，不只是裝飾性數字。

### 7.3 預設主視圖

預設以「模具」作為主要清單，因為多數工程人員會以模具代碼開始工作。Project 與 Part 作為篩選與階層導覽，不應要求使用者先切換四次頁籤。

使用者可在兩種視圖切換：

- **表格視圖**：適合搜尋、排序、批量查看。
- **階層視圖**：依 Project → Part → Mold → Revision 展開。

視圖偏好 MAY 保存在使用者個人設定，不得改變 Server Contract。

## 8. 搜尋、篩選與清單規格

### 8.1 搜尋

全域搜尋 MUST 支援核准欄位：

- 專案代碼／名稱；
- 零件編號／名稱；
- 模具代碼／名稱；
- Revision code；
- 外部來源識別碼。

不得搜尋使用者無權查看的 Scope，也不得將未授權資料送到前端再隱藏。

### 8.2 篩選

| 篩選 | 選項 |
|---|---|
| 專案 | 授權範圍內 Active Project |
| 產品／零件 | 依專案連動 |
| 模具類型 | 工程基礎資料 Active Code |
| 產品類型 | 工程基礎資料 Active Code |
| 材料 | 工程基礎資料 Active Code |
| 模具狀態 | active、retired、archived |
| 版本狀態 | draft、released、superseded、archived |
| CAD 狀態 | 有 CAD、無 CAD、處理失敗、品質阻擋 |
| 更新時間 | 日期區間 |

### 8.3 排序與分頁

預設依 `updated_at desc`。允許排序欄位必須由 Server allowlist 控制。Demo 預設 `page_size=25`，最大 100；Enterprise 可用 cursor pagination，但不得改變列表語意。

### 8.4 模具列表欄位

- 模具代碼與名稱；
- 所屬專案；
- 產品／零件；
- 模具類型；
- 穴數；
- 目前正式版本；
- CAD 工件數；
- 未完成資料品質提示；
- 狀態；
- 最後更新時間；
- 快速動作：查看、建立新版、開啟 CAD、開始規劃。

手機版改為摘要卡片，不以水平捲動隱藏主要動作。

## 9. 詳細資料頁規格

### 9.1 模具詳細頁頁首

顯示：

- 模具代碼；
- 模具名稱；
- Project／Part breadcrumb；
- 模具類型與穴數；
- 目前正式版本；
- 狀態；
- 資料來源；
- 最後更新者與時間。

主要動作依權限與狀態顯示：

- 編輯基本資料；
- 建立新版本；
- 上傳／查看 CAD；
- 建立模具規劃；
- 停用模具；
- 封存模具。

### 9.2 詳細頁 Tabs

#### 總覽

- 基本資料；
- 產品與專案關係；
- 目前正式版本；
- 關聯資料數量；
- 資料品質警示；
- 最近工程活動。

#### 模具版本

以時間線或表格呈現：

- Revision code；
- 狀態；
- 變更摘要；
- 發布時間；
- CAD 數量；
- 來源系統；
- 建立者；
- 被取代關係。

#### CAD 與圖檔

- Artifact 與 Artifact Version；
- 原始檔名、格式、大小、checksum 摘要；
- 處理與品質狀態；
- 3D 預覽入口；
- 下載權限；
- 正式歸檔或快速分析標示。

#### 工程履歷

統一列出：

- 模具規劃案；
- 設計審查；
- 相似模具搜尋；
- CAE／Moldflow；
- Process／Trial；
- HMI Extraction（若有關聯）；
- Job 與衍生結果。

每筆履歷顯示狀態、版本、建立者、時間與 Deep Link。

#### Lineage

提供圖形與無障礙表格兩種呈現：

```text
Mold Revision
├─ used_by → Mold Plan
├─ contains → CAD Artifact Version
├─ reviewed_by → Design Review
├─ simulated_by → CAE Study
└─ tested_by → Trial Run
```

#### Audit

依時間顯示建立、修改、發布、取代、停用、封存、匯入與 Mapping 修正事件。唯讀，不允許修改或刪除。

### 9.3 Revision 詳細頁

Revision 詳細頁 MUST 明確區分：

- 版本身份與狀態；
- 變更摘要；
- 前一版／下一版；
- CAD 工件與檔案版本；
- 工程工作使用狀況；
- 是否允許發布、封存或建立後繼版本；
- 發布新版後對舊版的影響。

## 10. 新增與編輯體驗

### 10.1 新增資料入口

`＋ 新增資料` 開啟分步式 Drawer 或 Modal：

1. 選擇新增類型：專案、產品／零件、模具、模具版本。
2. 顯示所選類型的必要父層 Context。
3. 填寫受控欄位。
4. 顯示重複代碼與資料品質預檢。
5. 確認變更理由。
6. 建立後開啟新紀錄詳細頁。

若使用者從 Project 或 Mold 詳細頁啟動新增，父層欄位 MUST 預先帶入且清楚顯示來源。

### 10.2 編輯基本資料

詳細頁提供 `編輯基本資料`，開啟結構化 Drawer。可修改欄位：

| 實體 | 可修改 | 不可直接修改 |
|---|---|---|
| Project | 名稱、說明、狀態 | Project code、Scope、來源身份 |
| Part | 名稱、產品類型、材料、狀態 | Part number、Project 歸屬 |
| Mold | 名稱、模具類型、穴數、狀態 | Mold code、Project 歸屬 |
| Draft Revision | 變更摘要 | Revision code、Mold 歸屬 |
| Released Revision | 原則上唯讀 | 變更以新 Revision 表達 |

所有修改 MUST：

- 要求變更理由；
- 攜帶 `row_version`；
- 對 409 衝突顯示可理解的重新載入／比較提示；
- 成功後顯示 Toast 並更新詳細頁；
- 寫入 Audit Event。

### 10.3 建立新版本

在 Mold 詳細頁按 `建立新版本`：

- 自動顯示目前 Released 版本作為來源；
- 建議下一個 Revision code，但允許依公司規則輸入；
- 填寫變更摘要與理由；
- 建立 Draft；
- 不複製 Artifact binary；可選擇建立 CAD 後續工作入口；
- 保留 `source_revision_id` Lineage。

### 10.4 發布版本

發布前預檢至少包含：

- 必要基本資料完整；
- 模具仍為 Active；
- Revision 為 Draft；
- Revision code 唯一；
- 必要 CAD／品質 Gate 是否達標（Demo 可為警告，Enterprise 可設定阻擋）；
- 影響摘要：哪個 Released 版本會變成 Superseded；
- 操作者權限與理由。

發布成功後不得改寫既有規劃、審查或分析 Snapshot。

### 10.5 停用與封存

- **停用模具**：不再提供給新的規劃與歸檔選用，歷史仍可讀。
- **封存模具**：從一般清單隱藏，仍可用明確篩選找回。
- **封存 Revision**：不得封存仍是目前 Released 的 Revision，必須先發布後繼版或停用模具。
- UI MUST 顯示受影響的 Active Draft、CAD、規劃與下游工作數量。
- 不提供日常實體刪除。

## 11. 關聯工程動作

從 Mold 或 Revision 詳細頁可安全啟動：

- 上傳正式 CAD；
- 開啟 3D 預覽；
- 建立模具規劃；
- 建立設計審查；
- 尋找相似模具；
- 建立／查看 CAE；
- 建立／查看試模紀錄。

每個動作使用標準 Deep Link／Context Contract，至少攜帶：

- `mold_id`；
- `mold_revision_id`；
- `cad_artifact_version_id`（若已選）；
- `correlation_id`。

不得只透過前端自由文字名稱建立關聯。

## 12. 資料契約與不變條件

### 12.1 階層不變條件

- Part 必須屬於一個 Project。
- Mold 必須屬於 Project；若關聯 Part，Part 必須屬於同一 Project。
- Revision 必須屬於一個 Mold。
- Artifact 正式歸檔時必須屬於一個 MoldRevision。
- 同一父層下代碼唯一，大小寫比較規則由 Server 固定。
- Released Revision 的身份與核心內容不可原地改寫。
- 一套 Active Mold 最多一個目前 Released Revision。

### 12.2 建議列表回應

```json
{
  "schema_version": "registry-list-v2",
  "items": [],
  "page": {
    "page": 1,
    "page_size": 25,
    "total": 0
  },
  "applied_filters": {},
  "aggregations": {
    "status": {},
    "mold_type": {},
    "cad_readiness": {}
  }
}
```

### 12.3 建議模具詳細回應

詳細 API SHOULD 一次提供頁首與 Overview 所需摘要，但大型子集合使用分頁子端點，避免單一 payload 無限制成長。

```json
{
  "schema_version": "registry-mold-detail-v2",
  "mold": {},
  "current_revision": {},
  "counts": {
    "revisions": 0,
    "cad_artifacts": 0,
    "mold_plans": 0,
    "design_reviews": 0,
    "cae_studies": 0,
    "trial_runs": 0
  },
  "data_quality": [],
  "allowed_actions": []
}
```

`allowed_actions` 只用於 UI discoverability；API 仍必須再次執行權限與狀態驗證。

## 13. API 規劃

### 13.1 保留既有端點

```text
GET|POST  /api/v1/registry/projects
GET|PATCH /api/v1/registry/projects/{id}
GET|POST  /api/v1/registry/parts
GET|PATCH /api/v1/registry/parts/{id}
GET|POST  /api/v1/registry/molds
GET|PATCH /api/v1/registry/molds/{id}
GET|POST  /api/v1/registry/revisions
GET|PATCH /api/v1/registry/revisions/{id}
GET|PATCH /api/v1/registry/artifacts/{id}
```

### 13.2 建議新增／擴充端點

| Method | Endpoint | 用途 |
|---|---|---|
| GET | `/api/v1/registry/overview` | 統計與資料品質摘要 |
| GET | `/api/v1/registry/tree` | 經授權、可分段載入的階層資料 |
| GET | `/api/v1/registry/molds/{id}/history` | 版本與主要工程活動摘要 |
| GET | `/api/v1/registry/molds/{id}/engineering-records` | 跨 Domain 分頁履歷 |
| GET | `/api/v1/registry/revisions/{id}/engineering-records` | 指定 Revision 履歷 |
| GET | `/api/v1/registry/molds/{id}/lineage` | 標準化 Lineage |
| POST | `/api/v1/registry/molds/{id}/revisions` | 由指定 Mold 建立新版本 |
| POST | `/api/v1/registry/revisions/{id}/actions` | release、archive 等受控動作 |
| POST | `/api/v1/registry/molds/{id}/actions` | retire、reactivate、archive |
| GET | `/api/v1/registry/molds/{id}/impact-preview` | 停用／封存前影響預覽 |

所有 list endpoint MUST 支援 `q`、`status`、`project_id`、`part_id`、`mold_type`、`has_cad`、`sort`、`page`、`page_size` 等 allowlisted query。

## 14. 權限與職責分離

### 14.1 建議權限

| Permission | 能力 |
|---|---|
| `registry:read` | 查看授權 Scope 內台帳 |
| `registry:create` | 建立 Project／Part／Mold／Draft Revision |
| `registry:edit` | 修改允許欄位 |
| `registry:release` | 發布 Revision |
| `registry:retire` | 停用／重新啟用 Mold |
| `registry:archive` | 封存資料 |
| `registry:import` | 執行 Registry 匯入 |
| `registry:export` | 匯出授權資料 |
| `audit:read` | 查看 Audit |
| `lineage:read` | 查看 Lineage |

Demo 可由 `registry:manage` 映射上述寫入權限；Enterprise SHOULD 拆分，避免建立者同時擁有所有發布與封存權限。

### 14.2 Scope 與資料隔離

- 所有列表、統計、搜尋、關聯數量與匯出 MUST 先套用 Scope／Classification 過濾。
- 不得透過數量、錯誤訊息、Deep Link 或 Lineage 洩漏未授權紀錄存在。
- MCP 預設只提供唯讀查詢；不得透過 Assistant 繞過 release／archive 人工確認。

## 15. Audit 與 Lineage

### 15.1 Audit Event

事件至少記錄：

- actor、角色與授權來源；
- action；
- target type／ID；
- before／after 安全摘要；
- reason；
- request／correlation ID；
- source system；
- timestamp；
- 匯入批次 ID（若適用）。

### 15.2 Lineage

Lineage MUST 支援：

- Project contains Part；
- Part has Mold；
- Mold has Revision；
- Revision supersedes Revision；
- Revision contains Artifact／ArtifactVersion；
- Revision used_by MoldPlan／DesignReview／CAE／Trial；
- ArtifactVersion produced FeatureSet／Preview／Embedding；
- ImportBatch created／updated Registry record。

## 16. 匯入、Connector 與資料品質

### 16.1 Demo 匯入

- 支援 CSV／XLSX；
- 先 Dry Run，再 Commit；
- 驗證完整 Project → Part → Mold → Revision 階層；
- 顯示新增、更新、跳過、錯誤與 Mapping Backlog 數量；
- 不允許匯入直接發布 Revision；Commit 最多建立 Draft；
- 完成後可從批次結果開啟新增或更新的台帳紀錄。

### 16.2 Enterprise Connector

未來可接 PDM／PLM／ERP，但需定義欄位 ownership：

| 欄位 | 建議權威來源 |
|---|---|
| Project／Part identity | PLM／ERP |
| Mold code／Revision | PLM／模具管理系統 |
| CAD binary／native revision | PDM／PLM |
| AI 衍生特徵與結果 | Mold AI Platform |
| 狀態 Mapping | Connector policy |

來源系統擁有的欄位在 UI 顯示唯讀與來源標示；本地修正使用 Mapping／Correction，不得靜默覆寫來源。

### 16.3 資料品質規則

至少檢查：

- 必要父層存在；
- 代碼重複；
- Part 與 Mold Project 不一致；
- Mold Type／Product Type／Material 無法 Mapping；
- Released Revision 無 CAD；
- 多個 Released Revision；
- 已封存父層仍有 Active 子層；
- 外部來源識別碼衝突；
- 孤兒 Artifact。

品質問題可為 Warning 或 Blocking，等級由可版本化 Policy 控制。

## 17. 錯誤、回饋與復原

- 400：欄位錯誤要對應至表單欄位。
- 403：說明沒有權限，不顯示未授權資料內容。
- 404：缺少或不可見紀錄採相同安全回應。
- 409 `VERSION_CONFLICT`：顯示他人已修改，提供重新載入與安全比較。
- 409 `INVALID_LIFECYCLE_TRANSITION`：說明目前狀態與允許動作。
- 422 `DATA_QUALITY_BLOCKED`：列出阻擋 Gate 與修正入口。
- 423 `RECORD_LOCKED`：顯示鎖定原因與擁有者（若可揭露）。

成功建立、修改、發布、停用或封存後 MUST 顯示 Toast、更新清單與詳細資料，不得只靠頁面無聲變化。

## 18. 響應式、雙語與無障礙

- 繁體中文與英文不得改變資料語意或造成按鈕溢位。
- Tab、Tree、Table、Drawer、Modal 皆支援鍵盤操作。
- 狀態不得只以顏色表達，必須包含文字。
- Tree 提供正確 ARIA hierarchy；Lineage 同時提供表格替代。
- 開啟新增／編輯 Drawer 時焦點移入；關閉後回到原動作。
- 手機版保留搜尋、查看、建立新版等主要動作。
- 200% 縮放下不得遮蔽儲存、取消或生命週期確認按鈕。

## 19. 非功能需求與效能

### 19.1 初始 Demo 指標

| 指標 | 目標 |
|---|---:|
| 台帳清單 API p95 | ≤ 1,000 ms |
| 模具詳細 Overview p95 | ≤ 1,000 ms |
| 關鍵字搜尋 p95（10,000 Molds） | ≤ 1,500 ms |
| 首頁可互動時間（外網 Demo） | ≤ 3 秒，排除首次冷啟動 |
| 建立／更新同步請求 p95 | ≤ 1,500 ms |
| 分頁最大 page size | 100 |

大量關聯資料使用分頁與延遲載入；不得在模具列表一次載入所有 CAD、Audit 或 Lineage nodes。

### 19.2 可觀測性

- API request ID；
- list/detail/mutation latency；
- 409 衝突率；
- 匯入錯誤率；
- Data quality issue counts；
- released-without-CAD 指標；
- Connector lag（Enterprise）。

## 20. Demo 與 Enterprise 邊界

### 20.1 Demo MUST

- 公開合成資料；
- 本機帳號與既有 RBAC；
- 表格／階層瀏覽；
- 搜尋、篩選、詳細頁；
- 結構化新增與編輯；
- Revision 建立與發布；
- CAD、規劃、審查、CAE、Trial 關聯摘要；
- Audit／Lineage；
- CSV／XLSX Dry Run 與 Commit；
- Sites 外網可用；
- 單一 Mold AI application image。

### 20.2 Enterprise SHOULD

- SSO、細粒度 ABAC 與職責分離；
- PDM／PLM Connector；
- 欄位 ownership 與雙向同步政策；
- 客戶／廠區／供應商隔離；
- 大量資料 cursor pagination 與搜尋索引；
- 電子簽核、保留政策與 Legal Hold；
- 多節點高可用部署；
- 匯出審批與浮水印；
- 企業資料品質 Dashboard。

## 21. 分階段實作與 Git Gate

### Phase 0：文件與現況基線

內容：

- 核准本文件；
- 盤點既有 Route、API、元件與測試；
- 建立 Registry UX traceability matrix；
- 鎖定舊 API 相容性。

Gate：文件連結、Markdown 格式、Git clean。

建議 Commit：`docs: define mold registry workspace improvement plan`

### Phase 1：清單、搜尋與資訊架構

內容：

- 頁首、副標題與主要動作；
- 模具預設清單；
- 搜尋、篩選、排序、分頁；
- 表格／階層切換；
- URL query state；
- 響應式列表。

Gate：API query contract、權限範圍、Vue component、keyboard、mobile、performance。

建議 Commit：`feat: improve mold registry discovery`

### Phase 2：穩定詳細頁與完整履歷

內容：

- Project／Part／Mold／Revision stable routes；
- Overview、Versions、CAD、Engineering History tabs；
- Deep Link；
- 空狀態、載入與錯誤狀態。

Gate：直接 URL、重新整理、404／403、關聯分頁、前後端 contract。

建議 Commit：`feat: add mold registry detail workspaces`

### Phase 3：新增、編輯與生命週期

內容：

- 新增 Drawer／Wizard；
- 詳細頁編輯；
- 建立下一版；
- 發布、取代、停用、重新啟用與封存；
- impact preview；
- 409 conflict UX。

Gate：RBAC、欄位不可變、state machine、optimistic locking、Audit、完整 regression。

建議 Commit：`feat: govern mold registry mutations`

### Phase 4：工程關聯與 Lineage

內容：

- CAD、Mold Plan、Review、Similarity、CAE、Trial 摘要；
- 跨頁 Deep Link；
- Lineage graph/table；
- Audit timeline；
- Assistant context。

Gate：跨 Domain isolation、lineage consistency、deep-link reload、無資料洩漏。

建議 Commit：`feat: connect mold registry engineering history`

### Phase 5：匯入與資料品質

內容：

- 台帳頁匯入入口；
- Dry Run／Commit 結果；
- Mapping Backlog；
- Data quality dashboard；
- 匯入批次到紀錄 Lineage。

Gate：CSV／XLSX、安全掃描、10,000-row performance、atomic commit、rollback、Audit。

建議 Commit：`feat: integrate registry import and quality workflows`

### Phase 6：外網 Demo 與發布強化

內容：

- 完整測試；
- 外網 Sites smoke；
- Demo UAT；
- 效能基準；
- 單一 Compose project／application image；
- 文件與操作手冊更新。

Gate：Backend、Engineering Web、Sites、Compose、Security、Performance、Git clean。

建議 Commit：`chore: release improved mold registry demo`

## 22. 測試矩陣

### 22.1 Backend

- 階層 constraint；
- 唯一代碼；
- Scope／Classification isolation；
- 搜尋、篩選、排序、分頁；
- Revision state machine；
- 發布後 supersede；
- optimistic locking；
- archive impact；
- Audit／Lineage；
- 關聯資料分頁；
- 匯入 atomicity 與 Mapping。

### 22.2 Frontend

- 清單、階層與 query state；
- 直接詳細頁與 reload；
- 新增 Drawer 焦點與取消；
- 編輯欄位與 Server error mapping；
- 409 conflict；
- 發布與封存確認；
- 空狀態；
- 中英文；
- 200% zoom；
- mobile layout；
- keyboard／ARIA。

### 22.3 E2E／外網

1. 從 Sites 開啟模具台帳。
2. 搜尋 Demo Mold。
3. 開啟 Mold 詳細頁。
4. 查看 Released Revision 與 CAD。
5. 建立 Draft Revision。
6. 上傳／關聯 CAD。
7. 發布新版並確認舊版 Superseded。
8. 建立模具規劃並返回相同 Revision。
9. 查看 Audit 與 Lineage。
10. 驗證無權限帳號不能修改。
11. 驗證只有單一 Mold AI Compose Project 與 Application Image。

## 23. 驗收標準

- `ACC-REG-001`：使用者能在 10 秒內以模具代碼找到模具並辨識目前正式版本。
- `ACC-REG-002`：使用者能從 Project 展開至 Part、Mold、Revision 與 CAD，無需切換四個平面頁籤。
- `ACC-REG-003`：每個 Project、Part、Mold、Revision 都有穩定可重新整理的詳細 Route。
- `ACC-REG-004`：具權限者可從詳細頁完成受控編輯；無權限者只看到唯讀狀態。
- `ACC-REG-005`：發布新版後，前一正式版自動變為 Superseded，歷史工作仍指向原版本。
- `ACC-REG-006`：模具詳細頁可查看 CAD、規劃、審查、CAE 與試模摘要及 Deep Link。
- `ACC-REG-007`：停用與封存前顯示影響，且不破壞 Audit／Lineage。
- `ACC-REG-008`：10,000 筆模具資料搜尋 p95 不超過 1,500 ms。
- `ACC-REG-009`：CSV／XLSX 匯入錯誤不會部分寫入；Commit 可追溯至批次。
- `ACC-REG-010`：繁中／英文、鍵盤、mobile 與 200% zoom 驗收通過。
- `ACC-REG-011`：外網 Sites、MCP Deep Link、安全標頭與本機帳號邊界通過。
- `ACC-REG-012`：完整測試通過後建立分階段 Git Commit，最終工作目錄 clean。

## 24. 風險與對策

| 風險 | 影響 | 對策 |
|---|---|---|
| 台帳與工程資料庫形成兩套詳細頁 | 功能與資料不一致 | 共用 API、Route adapter 與 Detail components |
| 關聯資料一次載入過多 | 詳細頁變慢 | 摘要 counts + 分頁／延遲載入 |
| 任意修改 Released Revision | 歷史不可重現 | Released 唯讀，變更建立新 Revision |
| 物理刪除模具 | 破壞規劃與審查 Lineage | 只提供 retire／archive |
| PDM／PLM 與本地同時修改 | 欄位 ownership 衝突 | Connector policy、來源標示、Mapping／Correction |
| 前端隱藏取代 Server 權限 | 未授權操作 | API 每次重新授權與狀態驗證 |
| 大量 Tree 一次展開 | 記憶體與 API 負載 | Lazy tree、分段載入、深度限制 |
| 使用者混淆 Mold 與 Revision | 上傳或規劃掛錯版本 | Breadcrumb、目前正式版標示、明確欄位說明 |

## 25. 建議先行決策

為避免實作阻塞，建議採用以下預設：

1. 頁面名稱維持「模具台帳」，副標題為「管理模具身份、版本與完整工程履歷」。
2. 預設入口以模具清單為主，不再預設顯示 Project 頁籤。
3. 保留表格與階層兩種視圖，預設 Desktop 為表格。
4. 新增與編輯使用右側 Drawer；生命週期確認使用 Modal。
5. Mold code、Revision code 與父層歸屬建立後不可直接修改。
6. Released Revision 不可直接編輯；結構變更建立下一個 Draft Revision。
7. 不提供日常 Hard Delete；使用 retire／archive。
8. 詳細頁優先整合既有 Engineering Database 元件，不重新建立平行 API。
9. 第一階段先完成發現與詳細頁，再開放完整修改和跨 Domain 履歷。
10. Demo 保留 `registry:manage` 相容權限，Enterprise 再拆分 create／edit／release／archive。

## 26. Definition of Done

- 模具台帳從平面新增頁轉為可搜尋、可展開、可查看完整內容的工程入口。
- Project、Part、Mold、Revision、CAD 關係清楚且可直接導覽。
- 新增、編輯、建立新版、發布、停用與封存均有一致、安全流程。
- Released 與歷史工程結果保持不可變、可重現。
- CAD、模具規劃、設計審查、CAE、試模、Audit 與 Lineage 可從模具頁找到。
- 權限、Scope、Classification 與 optimistic locking 由 Server 落實。
- 匯入、Mapping 與資料品質問題可追溯並有修正入口。
- 繁中／英文、Accessibility、Responsive、效能與外網 Demo 驗收通過。
- 每一 Phase 測試通過後建立獨立 Git Commit，最終只保留最新單一 Mold AI Application Image。
