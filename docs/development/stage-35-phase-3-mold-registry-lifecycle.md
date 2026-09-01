# Stage 35 Phase 3 — 模具台帳新增、編輯與生命週期

日期：2026-09-01

狀態：Implemented and Verified

對應需求：[`17_Mold_Registry_Workspace_Improvement_Plan.md`](../requirements/17_Mold_Registry_Workspace_Improvement_Plan.md) Phase 3

## 1. 階段目標

讓模具台帳不只是瀏覽資料，而能在權限、狀態、版本衝突、影響預覽與稽核邊界內完成受治理的新增、編輯與生命週期操作。

## 2. 使用者流程

### 2.1 新增與編輯

- Phase 1 的「新增資料」Drawer 繼續建立 Project、Part、Mold 與第一個 Draft Revision。
- Project／Part／Mold／Draft Revision 詳細頁新增「編輯基本資料」入口。
- 正式台帳詳細頁使用可聚焦、可按 Escape 關閉並能回復焦點的 `DetailDrawer`。
- Canonical code、父層歸屬、Scope、來源身份與 Released Revision 內容不允許原地改寫。
- 每次變更必須填寫理由並攜帶 `row_version`。

### 2.2 建立下一版本

Mold 詳細頁提供「建立下一版本」：

- Server 以目前 Released Revision 為來源，沒有 Released 時使用最近版本；
- A → B、數字遞增或複合代碼加 `.1` 的建議由 Server 決定；
- 使用者可輸入符合公司規則的替代代碼；
- 新版本固定以 Draft 建立；
- `source_revision_id` 保存來源 Lineage；
- 不複製 CAD binary；
- 建立成功後直接開啟新 Revision 的固定網址。

### 2.3 發布與封存 Revision

```text
Draft --release--> Released
Released --new release--> Superseded
Draft/Superseded --archive--> Archived
Released --archive--> Archived（僅 Mold 已停用或封存）
```

- Release 會在同一 Transaction 內將舊 Released Revision 改為 Superseded。
- Demo 允許沒有 CAD 時發布，但回傳 `RELEASED_WITHOUT_CAD` 警告。
- Released／Superseded／Archived 的變更摘要不可原地改寫。
- 目前 Active Mold 的 Released Revision 不可直接封存。

### 2.4 停用、重新啟用與封存 Mold

```text
Active --retire--> Retired
Retired --reactivate--> Active
Active/Retired --archive--> Archived
Archived --X--> no daily reactivation
```

- 停用後不再允許建立新 Revision，既有歷史仍可讀。
- 重新啟用只適用 Retired Mold。
- 封存後沒有一般日常復原捷徑，也不提供 Hard Delete。
- 前端只顯示目前狀態允許的動作；API 仍再次驗證。

## 3. Impact Preview

Mold 停用／重新啟用／封存前呼叫：

```text
GET /api/v1/registry/molds/{id}/impact-preview
```

顯示：

- Draft／Released Revision；
- CAD Artifact；
- Mold Plan；
- Design Review；
- Similarity Search；
- CAE Study；
- Trial Case。

統計先套用 Mold 所在的授權 Scope。確認操作時，實際影響摘要也寫入 Audit Event。

## 4. 受控 API

```text
POST /api/v1/registry/molds/{id}/revisions
POST /api/v1/registry/molds/{id}/actions
POST /api/v1/registry/revisions/{id}/actions
```

Mutation Contract：

```json
{
  "action": "retire | reactivate | archive | release",
  "row_version": 1,
  "reason": "required governed reason"
}
```

錯誤：

- `VERSION_CONFLICT`／`CONCURRENT_MODIFICATION`：重新載入後再比較與儲存；
- `INVALID_LIFECYCLE_TRANSITION`：回傳目前狀態與允許動作；
- `RELEASED_REVISION_IMMUTABLE`：要求建立下一版本；
- `REVISION_CODE_CONFLICT`：代碼已存在；
- 400 Field Validation、403 Permission、404 Safe Not Found 保持一致。

## 5. Audit

新增或使用下列 Append-only Event：

- `registry.revision.created.v1`；
- `registry.revision.release.v1`；
- `registry.revision.archive.v1`；
- `registry.mold.retire.v1`；
- `registry.mold.reactivate.v1`；
- `registry.mold.archive.v1`；
- 既有 Project／Part／Mold／Revision Updated Event。

Event 至少保存 Actor、Target、Reason、前後狀態、Impact、被取代版本與警告摘要。

## 6. 驗證結果

```text
Backend registry lifecycle suite: 13 passed
Frontend registry mutation focused suite: 2 files / 9 tests passed
Frontend full regression: 37 files / 151 tests passed
Backend full regression: 243 passed, 1 skipped, 9 subtests passed
Vue / TypeScript production build: passed
Python Ruff and formatting: passed
Django system and migration drift checks: passed
```

## 7. 未完成邊界

- 真實跨 Domain Engineering History、Lineage、Audit timeline 與 Assistant Context：Phase 4。
- Registry 匯入、Mapping Backlog 與 Data Quality Dashboard：Phase 5。
- 外網 Sites／MCP、單一 Image 與發布 UAT：Phase 6。
