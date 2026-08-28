# 外網 Sites、個人帳號、MCP 與 ChatGPT Plugin UI 需求規格書

版本：1.0  
日期：2026-08-28  
狀態：Demo 實作基線  
適用範圍：Mold AI Platform 單機 Windows + Docker 外網私人 Demo

## 1. 目的與產品決策

本文件定義兩種彼此互補、但共用同一套 Capability API 與資料治理的使用體驗：

1. **完整工程 Web 體驗**：使用者由私人 OpenAI Sites 入口進入 Windows 主機上的 Engineering Web，使用 Mold AI 本機帳號登入，執行 CAD、Similarity、Design Review、Knowledge、Process/Trial、CAE、HMI 與資料管理工作。
2. **ChatGPT 內的第二種體驗**：使用者在 ChatGPT 對話中呼叫 MCP 工具取得受治理的結構化結果；需要完整視覺工作區時，ChatGPT 顯示一個 Plugin UI 按鈕，經使用者明確點擊後，以官方外部開啟能力前往 Sites deep link，再由 Engineering Web 驗證個人帳號與權限。

MCP 是能力介面，不取代完整 Web。Sites 是穩定入口與 Workspace Tunnel dispatcher，不保存平台密碼或服務 API key。Quick Tunnel 是可替換的短期傳輸層，不是永久網址。

## 2. 已查證的 OpenAI 能力邊界

截至 2026-08-28，實作只依賴以下官方文件已確認能力：

- MCP tool 可透過 `_meta.ui.resourceUri` 關聯一個 UI resource；resource 使用 `text/html;profile=mcp-app`。UI 是漸進增強，工具在沒有 UI 的 Client 仍須可用。[Build a ChatGPT UI](https://developers.openai.com/plugins/build/chatgpt-ui)
- ChatGPT Plugin UI 可在使用者互動後呼叫 `window.openai.openExternal({ href, redirectUrl })` 開啟經允許的外部網址；新 UI 應優先採共用 MCP Apps bridge，並對 ChatGPT 專屬能力做 feature detection。[Plugin UI reference](https://developers.openai.com/plugins/reference)
- 外部跳轉網域須列入 resource 的 `_meta["openai/widgetCSP"].redirect_domains`。不得由模型自由指定任意網域。

本規格不把 ChatGPT 帳號方案、Workspace Policy、Sites 可見性、Secure MCP Tunnel 可用性或 UI 呈現位置視為永久保證；部署後仍須做帳號層 UAT。

## 3. 系統範圍

### 3.1 本階段 MUST

- `EXT-AUTH-001`：外網 Engineering Web 必須使用 Mold AI 個人帳號及伺服器端 session，不得再用共享 Demo Bearer token 代表人員。
- `EXT-AUTH-002`：session cookie 必須為 HttpOnly、Secure、SameSite=Lax；所有 session mutation 必須通過 CSRF。
- `EXT-AUTH-003`：未登入的 deep link 必須保留安全的 target 與識別碼；登入後仍開啟原指定內容。
- `SVC-AUTH-001`：MCP Gateway 必須使用獨立、至少 32 bytes 隨機服務憑證呼叫 Platform API。
- `SVC-AUTH-002`：服務主體只授予 `public-demo:read` 與 `public-demo:write`，不得取得 `identity:manage`、規則核准或其他管理權限。
- `SVC-AUTH-003`：服務憑證不得出現在 Sites storage、URL、MCP tool output、Plugin UI payload、log、audit detail 或 preflight response。
- `SITES-001`：Sites 只保存當次瀏覽器 session 的 Quick Tunnel HTTPS origin，不保存 Mold AI 密碼、session cookie、Demo token 或服務憑證。
- `SITES-002`：Sites 必須以公開的 `/api/v1/security/preflight` 驗證 endpoint contract、`external-demo` 環境、local auth 與 Quick Tunnel readiness。
- `DL-001`：deep link 僅可攜帶版本、受控 target 與對應識別碼；禁止 token、API key、任意 return URL、permission 或 script。
- `PLUGIN-UI-001`：MCP 必須提供一個 decoupled Web launcher tool，既有 9 個 domain tools 不依賴 UI 仍可正常使用。
- `PLUGIN-UI-002`：launcher 必須由 server-side DeepLinkBuilder 建立網址；模型不得直接傳入 `href`。
- `PLUGIN-UI-003`：UI 按鈕只允許跳轉到設定的 Sites origin 與 `/open` path，並以 `openExternal` 開啟；缺少該 API 時提供安全 anchor fallback。
- `PLUGIN-UI-004`：UI resource URI 必須版本化；CSP redirect allowlist 只包含部署的 Sites origin。
- `AUD-001`：服務主體請求使用獨立 actor id，拒絕事件保留 request id、path、scope 與 client type，但不得記錄密鑰。
- `OPS-001`：啟動、狀態與 smoke scripts 必須能驗證 local auth、local admin、MCP service boundary、HTTPS、HSTS、CSP 與 deep link readiness。

### 3.2 本階段不包含

- Enterprise SSO、SCIM、OAuth 2.1 delegated MCP identity。
- 固定網域、正式 Cloudflare Tunnel、HA、WAF 或多主機部署。
- ChatGPT 代表使用者取得其 Mold AI 個人權限；目前 MCP 只能存取 public synthetic Demo data。
- 自動建立或保存預設管理員密碼。

## 4. 信任邊界與資料流

```text
ChatGPT user
  | MCP tools                      | explicit button click
  v                                v
Secure MCP Tunnel            Plugin UI (sandbox)
  | service credential             | openExternal: stable Sites origin only
  v                                v
MCP Gateway                Private OpenAI Sites portal
  | X-Mold-AI-Client + Bearer       | stores current Quick Tunnel origin only
  v                                v
Platform API <---------- Engineering Web via HTTPS Quick Tunnel
  ^                                |
  | server-side session + CSRF      | Mold AI username/password
  +--------------------------------+
```

### 4.1 人員身分

- Engineering Web 的授權決策以 Django session 對應的 local account、role、permission 與 data scope 為準。
- Sites 的 owner-only 身分只保護入口，不替代 Mold AI 平台授權。
- 登入錯誤不得指出帳號是否存在；鎖定、停用與登出沿用 IAM SRS。

### 4.2 MCP 服務身分

- Header 必須同時包含 `X-Mold-AI-Client: mcp-gateway` 與正確 Bearer credential。
- 少任一項、token 錯誤、placeholder 或 scope 不足皆 fail closed。
- 此 credential 只存在 Windows 私有 `.env.sites-demo` 與 Docker service environment。
- MCP tool output 必須保留 public-demo data scope 與 lineage，且不得宣稱個人帳號授權已驗證。

## 5. Deep link contract

入口格式：

```text
https://<stable-sites-origin>/open?deep_link_version=1.0&target=<target>&<typed-ref>=<uuid>
```

支援 target：`home`、`job`、`similarity`、`design_review`、`knowledge`、`process_trial`、`cae`、`hmi`。每一 target 的 required/optional refs 由 server 與 Sites 共用等價 allowlist 驗證。

禁止欄位：`token`、`api_key`、`tunnel_id`、`workspace_url`、`return_url`、`javascript`、`permission`。識別碼只定位內容，不授權存取；Engineering Web 必須重新向 API 讀取並執行權限檢查。

## 6. Plugin UI contract

### 6.1 Tool

- 名稱：`open_mold_ai_web`
- 輸入：受控 `target` 及各 target 的 typed refs；不接受 URL。
- 輸出：標題、摘要、target、`links.ui` 與 contract version。
- metadata：`_meta.ui.resourceUri` 指向版本化 resource；保留相容的 `openai/outputTemplate` metadata。

### 6.2 Resource

- URI：`ui://mold-ai/open-web-v1.html`
- MIME：`text/html;profile=mcp-app`
- 只使用 `textContent` 顯示 tool output，不以 `innerHTML` 插入模型或伺服器文字。
- 先透過 MCP Apps tool-result notification 接收 structured content；ChatGPT 環境可讀取 feature-detected `window.openai.toolOutput`。
- 點擊前再次驗證 HTTPS origin、path 與 forbidden parameters。
- `openExternal` 不可用時，才顯示 `rel="noopener noreferrer"` 的 `_blank` anchor。

## 7. 設定與 Secret contract

| 變數 | 用途 | 瀏覽器可見 | 必填 |
|---|---|---:|---:|
| `DEMO_AUTH_MODE=local` | 啟用個人帳號 session | 可見模式，不含秘密 | 是 |
| `MCP_PLATFORM_SERVICE_TOKEN` | Compose 注入 API 與 MCP Gateway | 否 | 是 |
| `PLATFORM_SERVICE_TOKEN_SCOPES` | 服務主體最小 scope | preflight 可顯示 scope | 是 |
| `PLATFORM_SERVICE_ACTOR_ID` | 稽核 actor | audit 可見 | 是 |
| `PUBLIC_WEB_ENTRY_BASE_URL` | 穩定 Sites origin / redirect allowlist | 是 | 是 |
| `SECURE_MCP_TUNNEL_ID` | Secure MCP Tunnel 關聯 | 僅 readiness boolean | 外部 MCP 必填 |

舊 `DEMO_API_TOKEN` 只保留給 `required` compatibility mode；Sites local 模式不得使用它。

## 8. 錯誤、安全與威脅情境

- 竊取 Sites sessionStorage：最多取得當次 Quick Tunnel public origin，不能取得平台 credential。
- 猜測 Quick Tunnel URL：未登入 API 回傳 `AUTH_SESSION_REQUIRED`；登入端點仍受 rate limit/lockout 與 CSRF contract 保護。
- 偽造 `X-Mold-AI-Client`：沒有服務密鑰仍被拒絕。
- 服務密鑰外洩：立即 rotation，舊 credential 失效；audit 依 actor/client/request id 調查。
- Prompt injection 提供惡意 URL：launcher 不接受 href，server 只建立 allowlisted Sites deep link，UI 再做一次 origin/path 驗證。
- Plugin UI 不受 Client 支援：tool 仍回傳文字摘要及 `links.ui`，不影響 domain result。
- Quick Tunnel 重啟：Sites 重新輸入一次新 origin；stable Sites deep link 與 ChatGPT MCP connection 不需因 Web Tunnel 網址變更而重建。

## 9. 測試與驗收

### 9.1 自動測試

- `TST-EXT-001`：local mode 匿名存取 protected API 得到 401。
- `TST-SVC-001`：正確 client header + service token 可讀寫 public-demo endpoint。
- `TST-SVC-002`：缺 header、錯 token、弱 token、缺 scope皆拒絕且 audit 不洩密。
- `TST-SITES-001`：Sites 不再定義 TOKEN storage key，workspace URL 無 token fragment。
- `TST-SITES-002`：preflight contract 不正確或 local admin 未建立時顯示不可用。
- `TST-UI-001`：launcher 不接受任意 URL，生成網址符合 DeepLinkBuilder。
- `TST-UI-002`：resource MIME、resource URI、CSP redirect origin 與 tool metadata 正確。
- `TST-UI-003`：MCP preflight 工具數、resource readiness 與 deep-link readiness 正確。
- 全部 backend、Engineering Web、Sites 測試必須通過後才可 commit。

### 9.2 帳號層 UAT

1. 在 Windows 啟動更新後 Sites Demo，建立或確認一個 `platform_admin` local account。
2. 由外部網路開啟 Sites，僅輸入當次 Quick Tunnel origin。
3. 開啟 Engineering Web，確認先顯示 Mold AI 登入，再以個人帳號進入原 deep-link 頁面。
4. 在 ChatGPT 重新整理 Mold AI Platform connector，確認可見 10 個 tool。
5. 呼叫任一 domain tool，再呼叫 Web launcher；按下按鈕，確認由預設瀏覽器開啟相同 Sites deep link。
6. 以無權限、停用帳號與已登出 session 驗證拒絕情境。

ChatGPT UI 的實際卡片外觀與 `openExternal` 執行須在使用者 OpenAI 帳號/Workspace 完成外部 UAT；自動測試不得把該外部政策結果偽裝成已通過。

## 10. 效能與營運指標

- Sites preflight p95：外網正常時小於 3 秒；timeout 15 秒並提供可行錯誤訊息。
- local login API p95：同機正常負載小於 1 秒（不含使用者網路）。
- Plugin launcher tool p95：小於 500 ms，且不得呼叫 Platform API。
- deep link 產生與驗證：確定性，100% 拒絕未知欄位與非 canonical UUID。
- secret rotation 後，舊 service credential 下一次請求立即失效。

## 11. 發佈、回復與 Definition of Done

### 發佈順序

1. 備份 `.env.sites-demo` 與資料 volume（不納入 Git）。
2. 產生 `MCP_PLATFORM_SERVICE_TOKEN`，將 API 切為 `local`，重建 API/Web/MCP。
3. 建立/確認 platform admin，執行 external smoke。
4. 部署 Sites 更新，確認不再要求 Demo token。
5. 啟動 Secure MCP Tunnel，在 ChatGPT 重新整理 connector。
6. 完成 9.2 UAT 並保存不含秘密的結果。

### 回復

若 local account 發佈失敗，可暫時回到上一 Git commit 與 `required` compatibility mode；不得同時讓 local session 與舊共享 token 被 Sites UI 交付。資料 migration 不應因本階段回復而刪除。

### 完成定義

- 本文件、環境範例、操作文件與程式一致。
- Phase 1D 與 Phase 1E 各自通過完整測試並各有一筆可追溯 Git commit。
- Git worktree clean。
- 自動驗證與帳號層外部 UAT 結果分開記錄；未執行外部 UAT 時必須明確標示 pending。
