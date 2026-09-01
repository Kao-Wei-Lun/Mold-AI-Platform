# Stage 36 — Phase 4 模具台帳工程履歷、Lineage 與 Audit

狀態：Completed  
完成日期：2026-09-01

## 目標

讓「模具台帳」成為 canonical 模具身分與完整工程歷史的入口。使用者可由模具或模具版本詳細頁查看下游工程活動、追蹤資料關係、檢視不可變稽核證據，並以穩定連結前往原始工作區。

## 完成範圍

### 後端契約

新增兩個同構、受 `registry:read` 與 Data Scope 保護的端點：

- `GET /api/v1/registry/molds/{mold_id}/engineering-history`
- `GET /api/v1/registry/revisions/{revision_id}/engineering-history`

回應 `schema_version 1.0`，包含：

- `subject`：canonical mold／revision context；
- `counts`：模具規劃、設計審查、相似搜尋、CAE、試模數量；
- `items`：標準化工程紀錄與原工作區 deep link；
- `page`：頁碼、頁面大小、總筆數與 `has_next`；
- `lineage.nodes`／`lineage.edges`：Project → Part → Mold → Revision → CAD／工程紀錄關係；
- `audit_events`：與該模具、版本、CAD 及工程紀錄相關的 append-only 事件。

CAE 與 Trial 除 classification 外，必須通過 `acl_scopes` 與帳號 Data Scope 的交集檢查。設計審查與相似搜尋則由 CAD → Revision → Mold → Project Scope 的關係限制。後端不會把未授權資料送到瀏覽器。

### Web UI

模具與版本詳細頁新增：

- 「工程履歷」：顯示紀錄類型、名稱、所屬版本、負責人、更新時間與狀態；
- 「Lineage」：以可讀表格呈現 canonical hierarchy 與關聯節點；
- 「稽核」：呈現事件、操作者、變更理由、時間與 evidence hash 摘要；
- 工程履歷列可導向模具規劃、設計審查、相似搜尋、CAE 或試模原始頁；
- `?tab=engineering-history|lineage|audit` 可直接開啟並支援重新整理；
- 目前 mold／revision context 會送入 Embedded Engineering Assistant。

既有 `/data/molds` 相容頁仍保留；新的跨 Domain 功能只在正式台帳詳細 Route 啟用完整頁籤。

## 安全與資料一致性

- 先以 canonical mold／revision 驗證 Scope，再查詢下游資料。
- CAE／Trial 同時驗證 classification 與 ACL Scope。
- Audit Event 僅依已授權 subject 與已授權關聯紀錄組合 target references。
- Lineage 節點由相同授權後資料生成，不另行取得跨 Scope 資料。
- Deep link 僅含穩定 record ID，不含憑證、API key、tunnel ID 或 return URL。

## 驗證結果

- Backend targeted registry suite：14 passed。
- Backend full pytest suite：passed（含 1 skipped）。
- Django `manage.py check`：0 issues。
- Migration drift：No changes detected。
- Web targeted component suite：6 passed。
- Web full suite：37 files、152 tests passed。
- Web TypeScript／production build：passed。
- Sites suite：2 files、15 tests passed。
- Sites production build：passed。

## 對應驗收條件

- `ACC-REG-003`：詳細 Route 與頁籤可重新整理。
- `ACC-REG-006`：由模具／版本查看規劃、審查、相似搜尋、CAE 與試模摘要及 deep link。
- `ACC-REG-007`：生命周期與工程關聯保留 Audit／Lineage。
- `ACC-REG-011`：Deep link 使用既有受控協定與內部 Route。

