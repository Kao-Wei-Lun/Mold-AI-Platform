# Stage 33 Phase 1 — 模具台帳清單、搜尋與資訊架構

日期：2026-09-01

狀態：Implemented and Verified

對應需求：[`17_Mold_Registry_Workspace_Improvement_Plan.md`](../requirements/17_Mold_Registry_Workspace_Improvement_Plan.md) Phase 1

## 1. 階段目標

本階段將既有以四個平面頁籤與永久新增表單為主的台帳，改為以「尋找模具」為主要任務的 Discovery Workspace。

核心原則：

- 預設顯示模具，不要求使用者先從專案頁籤開始；
- 搜尋與篩選由 Server 在授權 Scope 內執行；
- 清單只取得目前分頁，不把所有台帳資料送到瀏覽器；
- 表格適合快速比對，階層視圖適合理解 Project → Part → Mold → Revision；
- 搜尋、篩選、排序、頁碼與視圖模式可由 URL 重現；
- 新增功能仍保留，但只在使用者要求時開啟 Drawer。

## 2. 已完成內容

### 2.1 台帳頁首與總覽

- 頁面標題改為「模具台帳」。
- 新增副標題「管理模具身份、版本與完整工程履歷」。
- 主要動作整合為「新增資料」與「重新整理台帳」。
- 新增六項 Server-side 統計：
  - 使用中專案；
  - 使用中模具；
  - 正式版本；
  - 草稿版本；
  - 正式版本缺少 CAD；
  - 待建立零件關聯。
- 統計卡片可套用相關篩選，不只是顯示數字。

### 2.2 模具優先清單

表格顯示：

- 模具代碼與名稱；
- Project／Part；
- 模具類型；
- 穴數；
- 目前正式版本；
- CAD 工件數；
- 模具狀態；
- 最後更新時間；
- 通往既有完整資料頁的查看動作。

手機版將每一列轉為摘要卡片，主要欄位與查看動作不依賴水平捲動。

### 2.3 受治理搜尋與篩選

後端 List API 已擴充下列 allowlisted query：

- `q`；
- `status`；
- `project_id`；
- `part_id`，包含 `unassigned`；
- `mold_type`；
- `product_type`；
- `material_code`；
- `revision_status`；
- `has_cad`；
- `view`；
- `sort`；
- `page`；
- `page_size`。

搜尋核准範圍涵蓋 Project code/name、Part number/name、Mold code/name、Revision code 與外部 Revision ID。所有 QuerySet 都先套用帳號授權 Scope，未授權資料不會送到前端。

### 2.4 排序、分頁與 URL State

- 預設排序改為 `updated_at desc`。
- Server 保持 `page_size` 最大 100 的既有保護，UI 預設 25。
- URL 保存 `q`、各篩選、排序、頁碼與 `view=tree`。
- 重新整理與瀏覽器上一頁／下一頁可重新載入相同 Discovery State。
- Server 仍使用排序 allowlist，未知排序欄位回傳 Typed 400 Error。

### 2.5 表格／階層視圖

- 表格視圖為 Desktop 預設。
- 階層視圖依目前授權且符合條件的分頁結果組成：
  - Project；
  - Product／Part 或未關聯群組；
  - Mold；
  - Revision 與 CAD 數量。
- `view=tree` 時 Server 才回傳該頁模具的 Revision children，避免表格模式傳輸不需要的明細。
- Draft Revision 仍保留既有發布入口與 Audit reason 行為。

### 2.6 新增資料 Drawer

- 新增表單不再永久占用清單右側。
- 具 `registry:manage` 權限者可按「新增資料」開啟 Drawer。
- Drawer 保留 Project、Part、Mold、Revision 四類建立能力。
- 唯讀帳號不會看到新增入口；API 仍會再次驗證 `registry:manage`。
- 建立成功後關閉 Drawer、重新載入總覽與清單，並顯示 Toast。

### 2.7 API Payload 擴充

Mold List Payload 新增：

- `current_revision_id`；
- `current_revision_code`；
- `artifact_count`；
- Tree 模式下的 `revisions`。

新增：

```text
GET /api/v1/registry/overview
```

Overview 與 List 都執行 `registry:read`、Data Scope 與 Classification 邊界。

## 3. Traceability

| Requirement | Implementation | Verification |
|---|---|---|
| Phase 1 頁首、副標題與主要動作 | Registry hero + action group | Vue component test、production build |
| 模具預設清單 | Server-paged Mold table | Vue component test、API test |
| 搜尋、篩選、排序、分頁 | Registry query contract + allowlist | Django registry test、Enterprise pagination regression |
| 表格／階層切換 | `view=table/tree` + conditional Revision payload | Vue interaction test、Django tree payload test |
| URL query state | `history.replaceState` + `popstate` restore | Vue URL state test |
| 權限範圍 | `_require` + authorized QuerySet | Viewer permission test、full backend regression |
| 響應式列表 | Desktop table + mobile cards | CSS production build、component structure test |
| 新增入口不干擾瀏覽 | Permission-gated Drawer | Vue creation and read-only tests |

## 4. 驗證結果

```text
Backend registry tests: 10 passed, including a 10,000-row / p95 budget gate
Backend full regression: 228 passed
Frontend registry component: 4 passed
Frontend full regression: 37 files / 148 tests passed
Vue / TypeScript production build: passed
Python Ruff: passed
git diff --check: passed
```

外網 Sites 強制 HTTPS；Django 測試容器明確設定 `DJANGO_SECURE_SSL_REDIRECT=false`，避免 Test Client 的 HTTP Request 被部署安全設定轉址。正式外網設定未因此降低。

## 5. 相容性與未完成邊界

- 既有 Project、Part、Mold、Revision Create／Patch Endpoint 保持相容。
- 既有 `/data/molds/{id}` 詳細頁仍作為本階段「查看」目的地。
- 穩定的 Registry 專屬 Project／Part／Mold／Revision Routes 與完整工程履歷屬 Phase 2。
- 編輯、建立新版、停用、封存與影響預覽的完整 Drawer／Modal 流程屬 Phase 3。
- 跨 Domain Engineering History、Lineage 與 Audit 整合屬 Phase 4。
- 大量匯入與資料品質修正屬 Phase 5。
- 最終單一 Image、外網 Sites、MCP Deep Link 與發布 Gate 屬 Phase 6。

## 6. Phase 1 Git Gate

- 必須通過專項與完整回歸；
- 必須通過 TypeScript production build 與 Ruff；
- 文件與需求 Traceability 必須同步；
- Git diff 不得有 whitespace error；
- 通過後建立獨立 Commit：`feat: improve mold registry discovery`。
