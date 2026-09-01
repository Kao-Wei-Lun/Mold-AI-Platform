# Stage 39 — 模具台帳工程履歷相容性修正

狀態：Completed  
完成日期：2026-09-01

## 問題

部分含有設計審查或相似度搜尋的模具在詳細頁載入工程履歷時回傳 HTTP 500。工程履歷組裝器誤用不存在的 `Job.created_by` 欄位；Production 500 回應為 HTML，前端又直接呼叫 `response.json()`，因此使用者看到 `Unexpected token '<'`。

## 修正

- 工程履歷改從 immutable Job input snapshot 的 `requested_by` 取得建立者。
- 舊 Job snapshot 沒有 requester 時使用 `system` 相容值，不修改既有歷史資料，也不需要 migration。
- 新的 Design Review、Similarity Search、分析重跑與 Mold Planning handoff 都將 request actor 寫入 snapshot。
- Registry API client 檢查回應 Content-Type，HTML 或無效 JSON 轉為具型別的 `REGISTRY_RESPONSE_INVALID`。
- Web UI 顯示可理解且可翻譯的重試訊息，不再暴露 JSON parser 技術錯誤。

## 回歸覆蓋

- 含新 requester 與舊版無 requester Design Review 的模具工程履歷均回傳 200。
- requester 與 `system` fallback 均符合 Registry contract。
- HTML 500 不會再呈現 `Unexpected token`。
- 問題資料 `DEMO-MOLD-016` 的外網 engineering-history 端點納入部署後 smoke 驗證。

## 發布

- Demo 版本：`0.15.1-demo`
- 保持單一 `mold-ai-platform-sites-demo` Compose Project。
- Engineering Web、API、MCP Gateway 與 Workers 共用單一版本化 application image。

## 驗證結果

- Backend full suite：246 passed、1 skipped、9 subtests passed。
- Engineering Web：37 test files、155 tests passed；TypeScript 與 production build passed。
- Sites：2 test files、15 tests passed；lint 與 production build passed。
- Django system check、migration drift、Ruff 與 formatting：passed。
- 外網 Sites smoke、安全標頭、本機帳號與 MCP service identity：passed。
- `DEMO-MOLD-016` 外網工程履歷：HTTP 200，2 筆 Design Review、1 筆 Similarity Search、8 個 Lineage nodes。
