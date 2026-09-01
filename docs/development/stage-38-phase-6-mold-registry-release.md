# Stage 38 — Phase 6 模具台帳外網 Demo 發布

狀態：Completed  
完成日期：2026-09-01

## 目標

完成模具台帳改善計畫的最後發布階段，將 Phase 1–5 的發現、詳細資料、生命週期、工程履歷、匯入與資料品質能力整合到現有外網 Demo，並以完整測試、外網 smoke、效能基準與單一應用映像作為發布條件。

## 發布內容

- Demo 版本更新為 `0.15.0-demo`。
- Engineering Web、Platform API、MCP Gateway 與兩種 Worker Runtime 共用單一 `mold-ai-platform-app:0.15.0-demo` 應用映像。
- Mold AI 僅保留一個 Compose Project：`mold-ai-platform-sites-demo`。
- 保留 PostgreSQL、Redis、Qdrant 與既有使用者資料卷；更新應用服務時不重建管理員帳號。
- 延續 owner-only Sites 固定入口，由 Portal 導向目前的 HTTPS Quick Tunnel。
- 延續 Secure MCP Tunnel 與 13-tool contract，MCP Deep Link 開啟相同外網 Web Context。

## 外網操作流程

1. 開啟固定的 owner-only Sites Demo 入口。
2. 若 Portal 尚未保存目前的 Quick Tunnel URL，貼上啟動指令顯示的 HTTPS URL；同一個瀏覽器工作階段會保存此值。
3. 按「開啟 Mold AI Platform」並以個人 Demo 帳號登入。
4. 由「模具台帳」搜尋模具代碼，開啟模具、版本、CAD、工程履歷、Lineage 或 Audit。
5. ChatGPT App 中的 Mold AI Platform MCP 可用 Deep Link 開啟相同工程 Context。

Quick Tunnel URL 可能在 tunnel container 重建時改變；固定 Sites 入口不變。URL、token、API key 與 tunnel ID 不寫入 Git 或驗收證據。

## 驗證結果

- 完整 Backend lint、format、Django check、migration drift：passed。
- Backend full suite：245 passed、1 skipped、9 subtests passed。
- Engineering Web：37 test files、154 tests passed；TypeScript 與 production build passed。
- Sites：2 test files、15 tests passed；lint 與 production build passed。
- Compose release／sites config 與 unified-image contract：passed。
- 外網 Web／API identity、local account boundary、MCP service identity、Deep Link、Plugin UI、HSTS、CSP smoke：passed。
- 效能基準包含 Registry list 與 data-quality 端點，皆要求零 request error；Registry p95 gate 為 1,500 ms。
- 3 個並行讀取 session 與 5 個 queue jobs baseline：passed。
- 舊版 Mold AI application image 已移除；其他非本專案 Docker 專案不受影響。

## 對應驗收條件

- `ACC-REG-001` 至 `ACC-REG-009`：由 Registry backend／frontend／ingestion suites 與效能基準覆蓋。
- `ACC-REG-010`：中英文、responsive、keyboard／ARIA 與視覺狀態由 Web tests 與人工 UI UAT 覆蓋。
- `ACC-REG-011`：外網 Sites、MCP Deep Link、安全標頭與本機帳號邊界通過。
- `ACC-REG-012`：每階段均有獨立 Commit，最終 release commit 後工作目錄 clean。

## 已知邊界

- OpenAI LLM Provider 尚未啟用時，Assistant 使用安全且可重現的 deterministic fallback；不影響模具台帳核心功能。
- Quick Tunnel 適合私人 Demo，不是企業正式網路拓撲；Enterprise 應改用正式網域、OAuth／SSO、WAF、rate limiting 與 HA 部署。
- 自動測試驗證所有受治理 mutation；實際外網瀏覽器中的視覺與操作 UAT 仍應由 Demo 使用者以其個人帳號確認。
