# Stage 34 Phase 2 — 模具台帳穩定詳細頁與完整履歷框架

日期：2026-09-01

狀態：Implemented and Verified

對應需求：[`17_Mold_Registry_Workspace_Improvement_Plan.md`](../requirements/17_Mold_Registry_Workspace_Improvement_Plan.md) Phase 2

## 1. 階段目標

將 Phase 1 的模具清單連接到可直接開啟、重新整理及分享的 Project／Part／Mold／Revision 詳細頁，並建立後續工程履歷整合所需的一致頁籤結構。

## 2. 固定網址

```text
/governance/mold-registry/projects/{project_id}
/governance/mold-registry/parts/{part_id}
/governance/mold-registry/molds/{mold_id}
/governance/mold-registry/revisions/{revision_id}
```

- 路由解析器只接受上述四種 Entity 與完整 ID；不完整或未知路徑進入安全的 Not Found 畫面。
- `?tab=overview|versions|cad|engineering-history` 可直接重現頁籤。
- 舊 `/data/molds/...` 路徑與元件仍保留，避免既有書籤及資料庫入口失效。
- Phase 1 表格與階層檢視的「查看」已改連正式台帳網址。

## 3. 詳細頁體驗

四種詳細頁共用下列導覽：

- **總覽**：Canonical identity、Scope／Classification、Project／Part 關係、目前正式版本、CAD 數量與最近版本。
- **版本**：Project 的 Part、Part 的 Mold、Mold 的 Revision，以及 Revision 本身的生命週期身份。
- **CAD 與圖檔**：以 Revision 為邊界顯示 Artifact 數量；進入 Revision 後列出完整 CAD Artifact 治理摘要並連回 3D／版本資料頁。
- **工程履歷**：Phase 2 提供具 Entity Context 的明確空狀態；Phase 4 才接入跨 Domain 真實紀錄，不使用推測或假資料填充。

所有詳細頁具備：

- Loading、Retry、Empty 與受治理 API Error 狀態；
- 返回模具台帳入口；
- 既有 `registry:manage` 編輯入口相容；
- 以 Server-side、Scope-filtered API 取得資料；
- Project 關聯集合使用分頁 List API，不將所有資料嵌入單一無限成長 Payload。

## 4. API 與安全邊界

Phase 2 沿用既有詳細 API：

```text
GET /api/v1/registry/projects/{id}
GET /api/v1/registry/parts/{id}
GET /api/v1/registry/molds/{id}
GET /api/v1/registry/revisions/{id}
```

- 每個 Endpoint 先驗證 `registry:read`。
- 查詢先套用帳號 Data Scope；不可見資料與不存在資料都回傳安全的 404。
- Project 關聯資料透過既有 `project_id` Filter 取得；Part／Mold／Revision Detail 保持既有 Contract。
- Mutation、生命週期、409 Conflict 與 Audit 強化屬 Phase 3。

## 5. Traceability

| Requirement | Implementation | Verification |
|---|---|---|
| 四種 stable routes | Prefix route validation + Registry detail component | Routing unit test |
| 重新整理與分享 | URL-derived Entity／Tab state | Component stable-route test |
| Overview／Versions／CAD／History | Common `DetailTabs` contract | Vue component test |
| 關聯資料 | Existing detail and filtered list APIs | Django contract test |
| 404／403 | Scope-filtered detail endpoints | Django security regression |
| 舊路徑相容 | `registryMode=false` compatibility | Existing History tests |
| 空／載入／錯誤 | Existing workspace states + contextual history empty state | Component tests and build |

## 6. 驗證結果

```text
Backend registry detail contract: 9 passed
Frontend registry/routing/history focused suite: 4 files / 23 tests passed
Vue / TypeScript production build: passed
Frontend full regression: 37 files / 149 tests passed
Backend full regression: 241 passed, 1 skipped, 9 subtests passed
Python Ruff: passed
Sites frontend: lint, 15 tests and production build passed
git diff --check: passed
```

## 7. 未完成邊界

- 結構化新增／編輯 Drawer、建立下一版、發布／取代／停用／重新啟用／封存與 Impact Preview：Phase 3。
- Mold Plan、Design Review、Similarity、CAE、Trial、Lineage、Audit 與 Assistant Context：Phase 4。
- 台帳匯入、Mapping Backlog 與 Data Quality Dashboard：Phase 5。
- 外網 Sites／MCP、單一 Application Image 與最終 UAT：Phase 6。
