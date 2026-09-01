# Stage 37 — Phase 5 模具台帳匯入與資料品質工作流

狀態：Completed  
完成日期：2026-09-01

## 目標

把既有受治理的 CSV／XLSX Ingestion Engine 整合到模具台帳，並提供可操作的資料品質儀表板。台帳不另建平行匯入器，所有批次仍共用 Upload → Security Screening → Mapping → Dry Run → Atomic Commit → Reconciliation 流程。

## 完成範圍

### Registry Data Quality API

新增：

- `GET /api/v1/registry/data-quality`

端點要求 `registry:read`，並於 Server 依帳號 Data Scope 過濾。回應包含：

- `summary`：總問題、Critical、Warning、Info 與 Mapping Required 數量；
- `items`：問題代碼、嚴重度、標題、說明、entity identity 與 correction action path；
- `recent_imports`：同一授權 Scope 中最近 10 筆 Registry import batches。

目前確定性品質檢查包括：

- Released Revision 無 governed CAD；
- Active Mold 尚未歸屬 Product／Part；
- Draft Revision 缺少 change summary；
- CAD quality status 為 pending／rejected；
- Registry import batch 停留在 mapping required、validation failed 或 failed。

所有問題都提供安全的修正入口；系統不提供破壞 Lineage 的 hard delete。

### Web UI

模具台帳頁新增：

- `批次匯入`：導向 `/data/imports?domain=registry`；
- `資料品質`：可展開品質摘要、問題與近期匯入批次；
- 問題可直接開啟對應 Revision CAD、Mold、CAD artifact 或 import batch；
- 近期批次可檢視 Mapping、Dry Run、Commit 與 Reconciliation 證據；
- 桌面與窄螢幕均維持可讀、可操作版面。

匯入中心新增 Route defaults：使用 `domain=registry` 進入時，自動預選「Project, part, mold and revision registry」。Registry Commit 結果改用正式 stable routes：

- Project：`/governance/mold-registry/projects/{id}`；
- Mold Revision：`/governance/mold-registry/revisions/{id}`。

### 既有匯入能力（沿用並驗證）

- JSON／CSV／XLSX 來源與 immutable source artifact；
- MIME、公式、封存檔與檔案大小安全檢查；
- 可儲存欄位 Mapping；
- Read-only Dry Run 與逐列 blocking issue；
- 經驗證批次才可 Atomic Commit；
- Idempotency key；
- Record results、Job、Audit 與 source lineage；
- Reconciliation report。

## 安全與隔離

- Data Quality API 先限制 Project／Mold／Revision／Artifact 的 Project Scope。
- Import batch 僅查詢帳號已授權的 `BulkImportBatch.scope`。
- 未授權 Scope 的失敗批次不會出現在 issue 或 recent imports。
- Web UI 顯示權限不是安全邊界；所有 API 仍獨立驗證權限。

## 驗證結果

- Backend targeted Registry suite：15 passed。
- Backend full pytest suite：passed（含 1 skipped）。
- Ruff：passed。
- Django system check：0 issues。
- Migration drift：No changes detected。
- Web targeted Registry／Ingestion suites：2 files、10 tests passed。
- Web full suite：37 files、154 tests passed。
- Web TypeScript／production build：passed。
- Sites suite：2 files、15 tests passed。

## 對應驗收條件

- `ACC-REG-003`：品質與 correction routes 可重載。
- `ACC-REG-009`：匯入失敗不部分寫入，Commit 可追溯至批次。
- `ACC-REG-011`：匯入結果使用正式 Web stable routes。
- `ACC-REG-012`：完成測試後建立獨立 Phase Git commit。

