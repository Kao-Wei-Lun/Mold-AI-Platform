# 模具規劃工作區與規則選用體驗改善規劃

版本：1.1 Implemented Baseline

日期：2026-08-31

狀態：Phase 0–6 已實作；Demo Release Gate 受持續驗證

適用範圍：Mold AI Platform Demo 與未來 Enterprise 版本

## 1. 文件目的

本文件定義 Mold AI Platform「模具規劃」能力的產品定位、資訊架構、操作流程、資料模型、API、權限、稽核、測試與分階段實作計畫。

目前治理端已能建立、編輯、驗證、送審、核准、發布及停止發布 Rule Profile，也已具備依模具類型、產品類型、材料、製程、位置、Scope、有效日期、Specificity 與 Priority 自動解析規則的後端能力。然而使用者在介面上仍主要透過「規定設定檔」下拉選單理解規則，缺少完整的工程規劃情境、推薦理由、候選比較、規劃結果保存與後續工作交接。

本次改善的核心不是新增另一個 Rule Profile 編輯器，而是將既有規則治理與解析能力組成工程師可理解的模具規劃流程：

> 使用者先說明正在規劃哪一個產品、模具與製程，系統再解析適用的模具設計標準，說明為何選中、有哪些要求與缺口，最後保存可追溯的規劃結果並交接至設計審查、CAD、相似搜尋及 CAE。

## 2. 核心產品決策

### 2.1 分離工程工作與治理工作

系統 MUST 將以下兩種不同使用目的分開：

| 工作區 | 主要使用者 | 目的 | 建議 Route |
|---|---|---|---|
| 模具規劃 | 模具工程師、設計工程師、專案工程師 | 建立工程情境、解析標準、比較候選、確認要求、保存規劃結果 | `/engineering/mold-planning` |
| 模具規定 | Rule Author、Reviewer、Approver、Data Steward | 建立及治理審查規則組與版本 | `/governance/rules` |

治理端不得因模具規劃功能而失去既有版本、驗證、Diff、Workflow、Usage、Audit 與 Lineage 能力。工程端不得直接修改已發布規則內容。

### 2.2 不再以 Profile 下拉選單作為主要體驗

「規定設定檔」下拉選單只可保留為進階選擇或人工覆寫控制，不得再作為模具規劃頁面的主要起點。預設流程 MUST 為：

1. 選擇規劃對象。
2. 補齊工程條件。
3. 執行規則解析。
4. 顯示推薦規則組、候選與選中理由。
5. 檢視適用要求與缺少資料。
6. 保存規劃結果。
7. 交接至後續工程工作。

### 2.3 重用既有 Rule Resolver

既有 Resolver 已支援：

- 只選擇 Published、Eligible、有效日期內、Scope 可見且 Classification 相符的規則組。
- Include／Exclude Applicability。
- Mold Type、Product Type、Material、Molding Process、Project 與 Location 維度。
- Specificity 優先，再比較 Priority。
- 同分候選 Fail Closed。
- Default Profile fallback。
- 具權限者人工覆寫，且必須填寫理由。
- 保存候選、選中結果、原因、Context 與 Applicability Checksum。

新功能 SHOULD 封裝與擴充既有 Resolver，不得在前端重新實作另一套排序邏輯。

## 3. 名詞與介面用語

### 3.1 建議名稱

| 目前或技術名稱 | 使用者介面名稱 | 說明 |
|---|---|---|
| Rule Profile | 審查規則組 | 一組可共同套用的模具設計與審查規則 |
| Rule Profile Version | 規則版本 | 審查規則組的不可變發布版本 |
| Applicability | 適用條件 | 決定規則組適用範圍的工程條件 |
| Rule Resolver | 標準解析 | 根據工程情境解析應使用的規則組 |
| Resolution Candidate | 候選標準 | 符合可見性、日期與適用條件的規則組 |
| Specificity | 條件符合度 | 符合的明確適用條件數量，不宣稱為 AI 機率 |
| Manual Override | 人工改選 | 具權限者改用另一個合格候選，必須說明理由 |
| Retire | 停止發布 | 不再供新規劃與新審查解析，但保留歷史結果 |
| Mold Plan | 模具規劃案 | 一次可保存、可追溯的模具規劃結果 |
| Planning Requirement | 規劃要求 | 從選定規則版本解析出的必要或建議工程要求 |

### 3.2 避免使用的文字

- 不在一般工程頁面直接顯示 `profile_key`、UUID 或 Checksum 作為主要名稱。
- 不將條件符合度稱為「AI 信心分數」或「預測準確率」。
- 不以「設定檔」取代工程師可理解的規則組名稱。
- 不以「套用成功」掩蓋缺少資料、Default fallback 或人工覆寫。

技術識別碼、Checksum 與完整版本資訊應保留在「技術資訊」或 Audit／Lineage 區塊。

## 4. 現況與缺口

### 4.1 已完成能力

- Rule Profile Catalog 與完整生命週期。
- Blank、Template、Clone 三種 Draft 建立方式。
- 結構化 Applicability Editor。
- 結構化 Rule Editor。
- Deterministic Validation。
- Impact Preview。
- Version Diff。
- Published Profile 自動解析。
- Ambiguity Fail Closed。
- 人工覆寫理由與 Audit。
- Design Review 保存解析 Snapshot 與精確 Rule Profile Version。

### 4.2 主要使用體驗缺口

1. 使用者必須先理解「規定設定檔」才知道如何開始。
2. Profile Selector 主要顯示 Key、Version 與狀態，缺少工程語意。
3. 無法從 Project、Part、Mold、Revision 或 CAD Context 建立規劃。
4. 沒有清楚區分自動推薦、Default fallback 與人工覆寫。
5. 候選規則組不能以工程維度並排比較。
6. 缺少「為何選中／為何排除」的集中說明。
7. 缺少規劃要求摘要、高風險項目、缺少資料與人工確認項目。
8. 規劃結果沒有獨立保存、狀態、版本與負責人。
9. 無法從規劃結果一鍵交接至 Design Review、CAD、Similarity 或 CAE。
10. 工程端與治理端的角色與操作仍容易混淆。

## 5. 目標資訊架構

```text
工程分析
├─ CAD 與工件
├─ 模具規劃                 ← 新增
├─ 相似度搜尋
├─ 設計審查
├─ 工程知識搜尋
├─ 製程／試模
├─ CAE／Moldflow
└─ HMI → Excel

治理管理
├─ 知識文件管理
├─ 模具規定                 ← 保留規則治理
├─ 模具台帳
├─ 工程資料治理
├─ 工程資料庫
├─ 帳號與存取
└─ 工程基礎資料
```

### 5.1 模具規劃頁面結構

```text
模具規劃
├─ 規劃案清單
│  ├─ 我的草稿
│  ├─ 等待確認
│  ├─ 已完成
│  └─ 已封存
│
└─ 規劃案工作區
   ├─ 1. 規劃對象
   ├─ 2. 工程條件
   ├─ 3. 推薦標準
   ├─ 4. 規劃要求
   └─ 5. 保存與交接
```

## 6. 目標使用流程

### 6.1 標準流程

```text
建立模具規劃案
  ↓
選擇 Project／Part／Mold／Revision／CAD
  ↓
自動帶入已治理的產品、材料、模具與製程資料
  ↓
使用者補齊缺少條件並確認資料來源
  ↓
伺服器執行 Rule Resolution Preview
  ↓
顯示推薦規則組、其他候選、排除原因與缺口
  ↓
使用者接受推薦，或具權限者填寫理由後人工改選
  ↓
產生必要規定、建議規定、風險及缺少證據摘要
  ↓
保存模具規劃案與不可變解析 Snapshot
  ↓
開始設計審查／CAD／相似搜尋／CAE
```

### 6.2 無符合規則

若沒有符合的 Published Profile，系統 MUST：

- 顯示 `RULE_PROFILE_NOT_FOUND` 的使用者友善說明。
- 列出造成無法解析的條件。
- 顯示缺少的工程基礎資料或適用條件。
- 提供返回修改條件與聯絡 Rule Owner 的動作。
- 不得靜默選擇任意 Profile。

### 6.3 候選衝突

若多個候選具有相同 Specificity 與 Priority，系統 MUST Fail Closed，並顯示：

- 衝突的規則組與版本。
- 相同的符合條件。
- Priority 與 Effective Period。
- 前往治理端檢查的 Deep Link。
- 具權限者可否人工改選；若允許，必須填寫理由。

## 7. 模具規劃工作區 UI 規格

### 7.1 規劃案清單

清單 SHOULD 顯示：

- 規劃案名稱與編號。
- Project、Part、Mold、Revision。
- Product Type、Material、Mold Type、Molding Process。
- 選定審查規則組與版本。
- 解析模式：自動、Default、人工改選。
- 狀態、負責人、更新時間。
- 後續 Design Review／CAE／Similarity 是否已建立。

清單 MUST 支援搜尋、狀態篩選、負責人篩選、Mold Type 篩選、分頁及穩定排序。

### 7.2 Step 1：規劃對象

欄位與行為：

| 欄位 | Demo | 來源 | 規則 |
|---|---|---|---|
| 規劃案名稱 | MUST | 使用者輸入 | 3–120 字元 |
| Project | SHOULD | Mold Registry | 可依 Scope 搜尋 |
| Product Part | SHOULD | Mold Registry | 依 Project 過濾 |
| Mold | MUST | Mold Registry | 依 Part 過濾 |
| Mold Revision | MUST | Mold Registry | 預設最新 Released；可選 Draft |
| CAD Artifact Version | SHOULD | CAD Registry | 只顯示該 Revision 的可見版本 |
| 規劃目的 | MUST | 受控選項 | 新模、改模、設變、試模改善、其他 |

選取 Mold／Revision 後 SHOULD 自動帶入可用 Context，且每個自動帶入值都要顯示來源。

### 7.3 Step 2：工程條件

第一階段 MUST 支援：

- Mold Type。
- Product Type。
- Material。
- Molding Process。
- Project。
- Location。

第二階段 SHOULD 支援：

- 模穴數。
- 預計產量與模具壽命目標。
- 成型機噸數或 Machine Family。
- 零件尺寸與重量級距。
- 外觀等級與品質等級。
- 客戶特殊規範。
- 熱澆道、退牙、多材料或嵌件等結構特徵。

每個欄位 MUST 顯示以下資料狀態之一：

- `Registry`：由 Mold Registry 帶入。
- `CAD`：由 CAD Metadata／Geometry 帶入。
- `Reference Data`：使用工程基礎資料選擇。
- `User confirmed`：使用者確認或補填。
- `Missing`：尚未提供，可能影響解析。

自由文字不得直接進入 Resolver；必須先 Mapping 至 Canonical Code。

### 7.4 Step 3：推薦標準

預設推薦卡 MUST 顯示：

- 使用者可理解的規則組名稱。
- 規則版本與 Published／Effective 狀態。
- Rule Owner 與 Approved By。
- 啟用規則數。
- 符合的適用條件。
- 未參與判定或缺少的條件。
- Priority。
- 解析模式。
- 選中理由。
- 規則來源文件摘要。

不得只顯示百分比。若 UI 需要摘要指標，應顯示：

> 符合 4 個明確適用條件；Specificity 4；Priority 20。

其他候選規則組應置於「查看其他候選」區塊，不搶占主要決策畫面。

### 7.5 候選比較

使用者 SHOULD 可選擇 2–3 個候選進行比較，至少包含：

| 比較項目 | 說明 |
|---|---|
| 規則組／版本 | 顯示使用者名稱與技術版本 |
| 適用條件 | 各維度 Include／Exclude |
| 符合條件 | 本次 Context 實際符合的項目 |
| Priority | Resolver 的次要排序依據 |
| 有效期間 | 是否即將到期 |
| 啟用規則數 | 規則規模 |
| 規則分類 | 模具設計、產品設計、材料、製程、品質 |
| 高風險規則 | Severity 為 high／critical 的規則 |
| 差異摘要 | 新增、移除、門檻差異及來源差異 |

比較結果必須來自伺服器 Canonical Contract，不得由前端自行推導工程判定。

### 7.6 人工改選

人工改選 MUST：

- 只顯示 Published、Effective、Eligible、Scope 可見且 Applicability 合格的候選。
- 只對具有 `rules:override` 權限的使用者開放。
- 顯示「系統推薦」與「改選目標」差異。
- 強制輸入 3–512 字元理由。
- 二次確認改選影響。
- 保存 Actor、Reason、原推薦、改選結果、Context、時間與 Correlation ID。

不得允許人工選擇不合格或未發布 Profile。

### 7.7 Step 4：規劃要求

系統 MUST 將選定 Profile 的規則整理成可操作摘要：

- 必須符合。
- 建議符合。
- 高風險或 Critical。
- 需要 CAD Geometry Evidence。
- 需要 CAE Evidence。
- 需要人工確認。
- 目前資料不足，無法判定。

每筆規劃要求至少顯示：

- Rule ID 與名稱。
- 分類與 Severity。
- 門檻、單位與容許差。
- Recommendation。
- Reference Document／Revision／Locator。
- Evidence Requirement。
- 本規劃階段狀態：未檢查、資料不足、可交設計審查、人工確認。

模具規劃不直接宣稱規則通過；實際幾何或製程判定仍由 Design Review／CAE／Trial Capability 執行。

### 7.8 Step 5：保存與交接

完成後 SHOULD 提供：

- 保存草稿。
- 標記規劃完成。
- 建立設計審查。
- 開啟／上傳 CAD。
- 使用同一 Mold Revision 執行相似搜尋。
- 建立 CAE 比較情境。
- 匯出規劃摘要 PDF／DOCX（後續階段）。
- 複製可授權 Deep Link。

所有交接 MUST 傳遞 Entity ID 與 Context Reference，不得依賴自由文字重新描述。

## 8. 治理端「模具規定」改善

即使新增工程端模具規劃，治理端也應改善 Profile 選擇方式。

### 8.1 規則組目錄

將單一下拉選單改為可搜尋的規則組目錄：

- 卡片／資料表切換。
- 搜尋名稱、Profile Key、Owner、Rule ID。
- Mold Type、Product Type、Material、Process、Location 篩選。
- Workflow Status、Resolution Status、Effective Status 篩選。
- Published、Draft、已停止發布分區。
- 每個 Profile Key 顯示最新版本及版本數量。
- 支援比較、開啟、Clone 與建立 Draft。

### 8.2 規則組卡片

卡片 SHOULD 顯示：

- 規則組名稱。
- Profile Key／Version（次要資訊）。
- 狀態與有效期間。
- Applicability 標籤。
- Priority／Default。
- 規則數與 Critical 規則數。
- Owner／Approver。
- 被 Mold、Review 與 Planning 引用的數量。

### 8.3 保留的治理頁籤

- 總覽。
- 適用條件。
- 規定。
- 版本差異。
- 工作流程。
- 使用影響。
- Audit／Lineage。

## 9. 功能需求

### 9.1 模具規劃案

- `MPL-PLAN-001`：使用者 MUST 可建立、保存、重新開啟及封存模具規劃案。
- `MPL-PLAN-002`：規劃案 MUST 關聯 Mold 與 Mold Revision；Demo SHOULD 可關聯 Project、Part 與 CAD Artifact Version。
- `MPL-PLAN-003`：規劃 Context MUST 使用 Canonical Code，並保存每個值的來源。
- `MPL-PLAN-004`：Draft 可修改；完成後若變更 Context，MUST 建立新的 Resolution Revision 或重新開啟並留下 Audit。
- `MPL-PLAN-005`：規劃案刪除不列入 Demo；使用封存保留歷史。

### 9.2 標準解析

- `MPL-RSL-001`：解析 MUST 由伺服器執行並重用既有 Rule Resolver。
- `MPL-RSL-002`：Preview 不得寫入 Design Review 或修改 Profile。
- `MPL-RSL-003`：解析結果 MUST 回傳候選、排除摘要、選中結果、模式、理由及 Checksum。
- `MPL-RSL-004`：缺少必要 Context 時，MUST 回傳 typed missing fields，不執行猜測。
- `MPL-RSL-005`：Ambiguous、Not Found、Override Not Eligible MUST Fail Closed。
- `MPL-RSL-006`：Default fallback MUST 明確標示，不得呈現為一般自動推薦。

### 9.3 比較與規劃要求

- `MPL-CMP-001`：比較 MUST 限制為同 Scope 可見候選。
- `MPL-CMP-002`：比較 MUST 顯示工程差異，不只顯示 Metadata。
- `MPL-REQ-001`：保存規劃時 MUST 固定 Rule Profile、Rule Version 與 Checksum。
- `MPL-REQ-002`：後續發布新 Profile 不得改寫既有規劃要求。
- `MPL-REQ-003`：規劃要求 MUST 能追溯至 Rule Version 與 Reference。

### 9.4 交接

- `MPL-HO-001`：建立 Design Review 時 MUST 傳遞 Planning ID、Mold Revision、CAD Artifact Version 與選定 Profile。
- `MPL-HO-002`：Design Review MUST 驗證傳入 Profile 仍與保存的規劃 Snapshot 一致。
- `MPL-HO-003`：每個交接 MUST 建立 Lineage／Audit Reference。

## 10. 建議資料模型

### 10.1 MoldPlan

| 欄位 | 說明 |
|---|---|
| `id` | UUID |
| `plan_code` | Scope 內可辨識代碼 |
| `name` | 規劃案名稱 |
| `purpose` | new_mold、modification、design_change、trial_improvement、other |
| `project_id` | 可選 Project |
| `part_id` | 可選 Product Part |
| `mold_id` | 必要 Mold |
| `mold_revision_id` | 必要 Mold Revision |
| `cad_artifact_version_id` | 可選 CAD Artifact Version |
| `status` | draft、ready、completed、archived |
| `owner_id` | 負責人 |
| `scope_id` | Data Scope |
| `classification` | 資料分類 |
| `row_version` | Optimistic Concurrency |
| `created_at`／`updated_at` | 時間 |

### 10.2 MoldPlanContext

建議以結構化 Child Records 或受 Schema 約束的 JSON 保存：

- `dimension`。
- `value_code`。
- `source_type`。
- `source_ref`。
- `confirmed_by`。
- `confirmed_at`。

Demo 可先使用 versioned JSON Contract；Enterprise SHOULD 正規化常用查詢維度。

### 10.3 MoldPlanResolution

每次解析建立不可變 Revision：

- `resolution_number`。
- `context_checksum`。
- `selected_profile_id`。
- `ruleset_checksum`。
- `applicability_checksum`。
- `selection_mode`。
- `reason`。
- `override_reason`。
- `candidate_snapshot`。
- `exclusion_summary`。
- `resolved_by`。
- `resolved_at`。

### 10.4 MoldPlanRequirement

- `mold_plan_resolution_id`。
- `rule_version_id`。
- `requirement_type`：must、should、manual_confirmation。
- `evidence_requirement`。
- `planning_status`。
- `source_reference_snapshot`。

規劃要求不得複製成可獨立修改的規則文字；顯示內容應引用精確 Rule Version 或保存必要 Snapshot，以確保歷史可重現。

## 11. API 與 Data Contract 規劃

### 11.1 建議端點

| Method | Endpoint | 用途 |
|---|---|---|
| GET | `/api/v1/mold-plans` | 規劃案清單、篩選及分頁 |
| POST | `/api/v1/mold-plans` | 建立 Draft 規劃案 |
| GET | `/api/v1/mold-plans/{id}` | 取得完整規劃案 |
| PATCH | `/api/v1/mold-plans/{id}` | 更新 Draft Context／Metadata |
| POST | `/api/v1/mold-plans/{id}/resolve` | 執行並保存一次解析 Revision |
| POST | `/api/v1/mold-plans/{id}/resolution-preview` | 不保存的解析預覽 |
| GET | `/api/v1/mold-plans/{id}/candidates/compare` | 比較 2–3 個候選 |
| POST | `/api/v1/mold-plans/{id}/select-profile` | 具權限人工改選 |
| POST | `/api/v1/mold-plans/{id}/actions` | complete、reopen、archive |
| POST | `/api/v1/mold-plans/{id}/handoffs/design-review` | 建立 Design Review |

### 11.2 Resolution Preview 回傳重點

```json
{
  "schema_version": "1.0",
  "context": {},
  "missing_fields": [],
  "selection_mode": "automatic",
  "selected": {
    "profile_id": "uuid",
    "display_name": "汽車外觀件模具設計標準",
    "version": "2.0",
    "specificity": 4,
    "priority": 20,
    "matched_dimensions": ["mold_type", "product_type", "material", "molding_process"]
  },
  "candidates": [],
  "excluded_summary": [],
  "reason": "Selected the most specific published profile...",
  "applicability_checksum": "sha256"
}
```

回傳 MUST 同時包含機器可讀 Code 與使用者可理解 Display Label。前端不得用英文錯誤訊息直接取代正式 UI 文案。

## 12. 權限、稽核與 Lineage

### 12.1 建議權限

| 權限 | 用途 |
|---|---|
| `mold-planning:read` | 查看 Scope 內規劃案 |
| `mold-planning:create` | 建立與修改自己的 Draft |
| `mold-planning:manage` | 修改 Scope 內規劃、重新指派、封存 |
| `mold-planning:complete` | 標記規劃完成 |
| `rules:override` | 人工改選合格 Profile |
| `rules:read` | 查看規則組與來源 |

Platform Admin 在 Demo 具備全部權限；一般 Viewer 只讀；Rule Author 不因可編輯規則而自動取得規劃改選權限。

### 12.2 必須稽核的事件

- 建立規劃案。
- 修改 Context。
- 執行解析。
- 自動選擇、Default fallback 或解析失敗。
- 人工改選及理由。
- 完成、重新開啟、封存。
- 建立 Design Review／CAE／Similarity 交接。

Audit 不得記錄 Token、API Key、未遮罩敏感資料或完整未授權來源內容。

### 12.3 Lineage

```text
Project / Part / Mold / Revision
            ↓
      MoldPlan Context
            ↓
   MoldPlan Resolution Revision
            ↓
RuleProfile + RuleVersion + Reference
            ↓
Design Review / Similarity / CAE / Export
```

## 13. Assistant、MCP 與 Deep Link

### 13.1 Assistant Context

模具規劃頁最小 Context SHOULD 包含：

- `page: mold_planning`。
- `mold_plan_id`。
- `mold_revision_id`。
- `cad_artifact_version_id`。
- `resolution_id`。
- `selected_profile_id`。

Assistant 可回答「為什麼選這套標準」、「還缺哪些資料」及「哪幾條規定需要 CAE」，但不得自行發布規則或繞過人工改選權限。

### 13.2 MCP

Demo 後續 MAY 新增：

- `get_mold_plan`。
- `preview_mold_plan_rule_resolution`。
- `explain_mold_plan_rule_selection`。

MCP 預設只讀；建立、改選、完成或封存需要明確工具、授權與確認。Deep Link Target 建議新增 `mold_plan`，必要參照為 `mold_plan_id`，可選 `resolution_id`。

## 14. Demo 與 Enterprise 邊界

### 14.1 Demo MUST

- 使用現有公開合成 Project／Part／Mold／Revision／CAD。
- 建立、保存及重新開啟規劃案。
- 自動帶入與補填六個既有 Resolver 維度。
- 顯示推薦、Default、衝突、無結果與人工改選情境。
- 顯示 2–3 個候選比較。
- 產生規劃要求摘要。
- 一鍵建立 Design Review。
- 中英文 UI、權限、Audit、Lineage、外網 Sites Demo。

### 14.2 Enterprise SHOULD

- PDM／PLM 專案與 BOM Context。
- MES Machine／Location Context。
- QMS Customer／Quality Requirement。
- 公司規範與客戶特殊規範 Connector。
- 多 Scope／多 Site 規則繼承。
- 正式送審、電子簽核與通知。
- PDF／DOCX 規劃報告與公司版型。
- 跨模具規劃 KPI 與規則覆蓋率分析。

## 15. 非功能需求

- Resolution Preview 在 Demo 資料量下 p95 SHOULD ≤ 2 秒。
- 規劃案清單 API p95 SHOULD ≤ 1 秒，預設每頁 25 筆。
- 所有 Mutation MUST 使用 CSRF／Session 或受治理 Gateway Identity。
- 所有 PATCH／Action MUST 使用 `row_version` 防止覆寫。
- 鍵盤操作、Label、Focus、Error Summary 與色彩對比 MUST 符合既有 Accessibility 基線。
- Desktop 以五步驟工作區呈現；小於 900px 改為單欄；不得依賴固定像素寬度。
- Resolver、Requirement Snapshot 與 Handoff Contract MUST 具 `schema_version`。
- 前端錯誤 MUST 使用 Typed Error Code 對應繁中與英文文案。

## 16. 分階段實作計畫

每個 Phase 必須獨立測試，測試通過後建立一筆 Git Commit；不得將未通過 Gate 的下一 Phase 混入同一 Commit。

### 16.0 實作追蹤

| Phase | 狀態 | Git Commit | 主要結果 |
|---|---|---|---|
| 文件基線 | 完成 | `dce2812` | 建立本需求、資料契約、測試與分段 Git Gate |
| Phase 0 | 完成 | `62a1baa` | 工程端模具規劃 Route、導覽、雙語空間與治理端責任分離 |
| Phase 1 | 完成 | `783ed5c` | 工程 Context、來源標示、伺服器規則解析預覽與 typed states |
| Phase 2 | 完成 | `ad67674` | 候選目錄、2–3 組比較與治理端可搜尋規則組目錄 |
| Phase 3 | 完成 | `4fee152` | MoldPlan、Context、Resolution、Requirement 持久化與生命週期 |
| Phase 4 | 完成 | `4feeb05` | 不可變規劃要求、Design Review Handoff、Audit 與 Lineage |
| Phase 5 | 完成 | `7f91201` | 受權限人工改選、Assistant Context、13-tool MCP 與 Deep Link |
| Phase 6 | 完成 | 見本階段發布 Commit | 效能、安全、Golden Scenario、外網與單一 Docker 發布 Gate |

### Phase 0：資訊架構與命名基線

交付：

- 新增 `mold_planning` Route、導覽、Icon 與中英文文案。
- 將治理端介面用語由 Profile／設定檔調整為審查規則組／規則版本。
- 建立空的規劃案清單與引導頁，不改動後端規則邏輯。
- 保留 `/governance/rules` 全部既有功能。

Gate：Routing、i18n、Navigation、Responsive、Accessibility 測試。  
建議 Commit：`feat: establish mold planning workspace`

### Phase 1：規劃 Context 與解析預覽

交付：

- 規劃對象與工程條件表單。
- Registry／CAD／Reference Data 自動帶入與來源標示。
- Resolution Preview API，封裝既有 Resolver。
- 推薦卡、選中理由、Default／Not Found／Ambiguous 狀態。
- 此階段可先不保存 MoldPlan。

Gate：Resolver regression、permission、typed error、context validation、component、API 與外網 UAT。  
建議 Commit：`feat: add mold planning rule preview`

### Phase 2：候選目錄與比較

交付：

- 其他候選展開區。
- 2–3 個候選並排比較。
- 規則分類、高風險規則與版本差異摘要。
- 治理端規則組目錄取代單一下拉選單。

Gate：Scope filtering、comparison contract、large-list UI、keyboard and responsive tests。  
建議 Commit：`feat: add rule set catalog and comparison`

### Phase 3：保存模具規劃案

交付：

- MoldPlan、Context、Resolution、Requirement Models 與 Migration。
- Draft、Ready、Completed、Archived 狀態。
- 規劃案清單、詳細頁與重新開啟。
- Snapshot、Checksum、Audit、Lineage、Concurrency。

Gate：Migration、model constraint、immutability、concurrency、CRUD、archive、API pagination 與完整 regression。  
建議 Commit：`feat: persist governed mold plans`

### Phase 4：規劃要求與工程交接

交付：

- 必須、建議、高風險、CAE／CAD Evidence 與資料不足摘要。
- 建立 Design Review Handoff。
- Similarity／CAE／CAD Deep Link。
- Design Review 顯示來源 Mold Plan。

Gate：End-to-end lineage、profile snapshot consistency、handoff authorization、historical reproducibility。  
建議 Commit：`feat: connect mold plans to engineering workflows`

### Phase 5：人工改選、Assistant 與 MCP

交付：

- `rules:override` 權限與情境式理由對話框。
- Assistant Context 與 deterministic explanation。
- MCP read-only tools 與 `mold_plan` Deep Link。
- Plugin UI／Sites 第二種開啟體驗。

Gate：RBAC、Audit redaction、MCP schema、prompt injection boundary、deep-link contract、Sites UAT。  
建議 Commit：`feat: expose governed mold planning integrations`

### Phase 6：Release Hardening

交付：

- 效能、Accessibility、安全、備份恢復、文件與 Demo Script。
- 單一 Docker Image／Compose Project。
- 外網 Sites、Web Tunnel 與 Secure MCP Tunnel 驗證。
- Golden Demo Scenarios。

Gate：完整 backend／frontend／MCP／Sites regression、external smoke、Git clean。  
建議 Commit：`chore: harden mold planning demo release`

## 17. 測試矩陣

### 17.1 Resolver

1. 精確四維條件選中最具體 Profile。
2. 三維條件優先於二維條件。
3. Specificity 相同時使用 Priority。
4. 同 Specificity／Priority 回傳 Ambiguous 並阻擋。
5. Exclude 條件正確排除。
6. 未發布、已停止發布、過期、不同 Scope／Classification 不得成為候選。
7. 無候選時明確失敗。
8. Default 只在沒有更具體候選時使用。
9. 人工改選只能選 Eligible Candidate 並要求理由。

### 17.2 規劃資料

1. Context 只能使用 Active Canonical Code。
2. Inactive Code 不出現在新表單，但歷史規劃可讀。
3. Mold Revision／CAD 關聯必須一致。
4. 完成後歷史 Resolution 不被新 Profile 發布改寫。
5. Row Version 衝突回傳 409。
6. Archive 不刪除 Audit、Requirement 或 Handoff。

### 17.3 UI

1. 工程師無須知道 Profile Key 即可完成規劃。
2. 六個 Resolver 維度皆可操作且顯示來源。
3. 推薦、Default、Not Found、Ambiguous、Override 五種狀態可辨識。
4. 比較表於 Desktop 與 Mobile 可用。
5. 必填錯誤聚焦第一個問題欄位。
6. 中文與英文不跑版。
7. 助理預設隱藏狀態不影響工作區寬度。

### 17.4 E2E／外網

1. 從 Sites 開啟模具規劃。
2. 使用 Demo Mold 建立 Context。
3. 預覽並接受推薦規則組。
4. 保存規劃案。
5. 建立 Design Review。
6. 從 Design Review 返回相同 Mold Plan。
7. ChatGPT MCP 查詢選中理由並開啟正確 Deep Link。
8. 確認只存在單一 Mold AI Docker Image 與 Compose Project。

## 18. 驗收標準

- `ACC-MPL-001`：新使用者能在不理解 Profile Key 的情況下，五分鐘內完成一筆 Demo 模具規劃。
- `ACC-MPL-002`：100% 已保存規劃案可追溯至 Mold Revision、Context、Rule Profile、Rule Version、Resolver Snapshot 與 Actor。
- `ACC-MPL-003`：同一固定 Context 與固定資料版本重跑可得到相同選中 Profile 與 Checksum。
- `ACC-MPL-004`：Ambiguous 與 Not Found 不會靜默產生規劃完成狀態。
- `ACC-MPL-005`：人工改選沒有權限或理由時，UI 與 API 均拒絕。
- `ACC-MPL-006`：發布新 Profile 後，既有 Mold Plan 與 Design Review 仍可重現。
- `ACC-MPL-007`：完整測試、Production Build、Sites Smoke、MCP Contract 與 Git Clean Gate 全部通過。

## 19. 風險與對策

| 風險 | 影響 | 對策 |
|---|---|---|
| 將模具規劃誤做成另一個規則編輯器 | 工程與治理再次混淆 | Route、權限與頁面責任明確分離 |
| 使用「匹配度」造成 AI 機率誤解 | 使用者錯誤信任 | 顯示 Specificity、Priority 與明確符合維度 |
| Context 自由文字污染 Resolver | 解析不一致 | 全部 Mapping 至 Canonical Code |
| 前端重新實作排序 | 與後端結果不一致 | 所有解析與比較由 Server Contract 提供 |
| 人工改選繞過治理 | 不正確規則被使用 | Eligible-only、權限、理由、確認、Audit |
| 新版規則改寫歷史規劃 | 無法重現 | 保存精確 Profile／Rule Version 與 Snapshot |
| 一次開發範圍過大 | UI 與模型同時失控 | 依 Phase 0–6 分段，每階段測試與 Git Gate |

## 20. 建議先行決策

開始開發前建議採用以下預設，避免阻塞 Phase 0–2：

1. 工程端名稱採「模具規劃」，治理端維持「模具規定」。
2. Rule Profile 的 UI 名稱採「審查規則組」。
3. 第一階段以 Mold Revision 為必要規劃對象，CAD 為選填。
4. 第一階段只使用既有六個 Resolver 維度，不立即增加模穴數或品質等級到 Resolver。
5. Phase 1 先做不保存的解析預覽；Phase 3 再新增 MoldPlan 資料模型。
6. 候選比較最多三個，以維持桌面與平板可讀性。
7. 人工改選延後至 Phase 5，先確保自動解析與衝突說明正確。
8. 模具規劃不取代 Design Review；它負責決定標準與準備證據，Design Review 負責執行確定性判定。

## 21. Definition of Done

本規劃全部完成的定義：

- 工程端與治理端責任已分離。
- 使用者不需直接使用 Profile 下拉選單即可完成規劃。
- Context、Resolver、Candidate、Selection、Requirement 與 Handoff 全部可追溯。
- 自動推薦、Default、Not Found、Ambiguous 與人工改選皆有明確介面。
- 規劃結果可保存、重新開啟、封存並交接至 Design Review。
- Published Rule 與歷史 Mold Plan 維持不可變與可重現。
- 繁中／英文、Accessibility、RBAC、Audit、Lineage、MCP 與 Sites 外網 Demo 驗收通過。
- 每一 Phase 均在測試通過後建立獨立 Git Commit，最終工作目錄為 clean。
