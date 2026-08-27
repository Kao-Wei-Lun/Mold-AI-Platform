# Mold AI Platform 需求規格書套件

版本：0.9 Draft Baseline  
日期：2026-08-25  
狀態：供 Demo 規劃、技術評審與企業需求訪談使用

## 1. 文件目的

本套件將已確認的 Mold AI Platform 方向整理成可執行的需求基線，明確區分：

- **Demo 版本**：單台 Windows + NVIDIA GPU + Docker + 外部 LLM API，以公開／合成資料展示端到端流程。
- **Enterprise 版本**：接入公司 CAD、PDM/PLM、MES、QMS、CAE、檔案伺服器與身分系統，具備正式權限、稽核、資料血緣、可用性及水平擴充能力。

核心產品決策是：

> 專用 Engineering Web UI 與 ChatGPT／其他 AI Client 的 MCP 入口並存，共用同一套 Canonical Data Model、Capability API、Job System 與治理機制。MCP 是 Adapter，不是平台本體；LLM 是自然語言介面與工具協調層，不是幾何、規則或製程判定的唯一依據。

## 2. 文件索引

1. [總體架構與範圍](01_Architecture_and_Scope.md)：產品邊界、雙入口架構、元件、關鍵決策與部署拓撲。
2. [Demo SRS](02_Demo_SRS.md)：Demo 使用者故事、功能／非功能需求、單機限制與展示腳本。
3. [Enterprise SRS](03_Enterprise_SRS.md)：正式版完整功能、組織整合、治理、可靠度與營運需求。
4. [Canonical Data Model 與 Data Contract](04_Canonical_Data_Model_and_Contracts.md)：主實體、版本、識別碼、事件、Lineage 與 Schema 規則。
5. [AI Capability 與工程模組](05_AI_Capabilities_and_Engineering_Modules.md)：CAD Similarity、Design Review、Process/Trial、CAE/Moldflow、Machine UI→Excel、Knowledge/RAG。
6. [Assistant、MCP、LLM 與 UI Action](06_Assistant_MCP_LLM_UIAction.md)：Embedded Engineering Assistant、MCP Gateway、Provider abstraction、UI Context、Action Protocol。
7. [安全、治理、Job 與部署](07_Security_Governance_Jobs_Deployment.md)：權限、稽核、Lineage、安全、Queue/Worker、可觀測性與 Windows Demo 部署。
8. [資料 Connector、遷移與 Roadmap](08_Data_Connectors_Migration_Roadmap.md)：Public→Company Connector 切換、資料成熟度與分階段落地。
9. [測試、評估與驗收](09_Test_Evaluation_Acceptance.md)：功能、效能、AI 指標、安全測試、驗收門檻與追溯矩陣。
10. [介面與 Schema 範例](10_API_and_Schema_Examples.md)：Capability、Job、MCP Tool、UI Action、Similarity 與 Review 的 JSON 範例。

目前 Stage 12 之後的可執行開發順序、工作拆解、Gate、風險與 Web UI 改良計畫，另見
[Demo v1.0 Completion Plan](../planning/demo-v1/00_README.md)。Planning 文件將本 SRS 的 MUST
requirements轉為Stage 13–17實作與驗收項目；若兩者衝突，以本需求套件與最新核准變更為準。

## 3. 規格閱讀規則

需求關鍵字採以下定義：

- **MUST／應**：Demo 或 Enterprise 對應版本的強制驗收條件。
- **SHOULD／宜**：若無技術或資料阻礙應實作；不實作須留下決策紀錄。
- **MAY／可**：選配或延伸能力。
- `D-xxx`：Demo 需求。
- `E-xxx`：Enterprise 需求。
- `CDM-xxx`：資料契約需求。
- `CAP-xxx`：AI Capability 共通需求。
- `SEC/JOB/OPS-xxx`：安全、工作與營運需求。
- `TST/ACC-xxx`：測試與驗收要求。

所有百分比、延遲與準確率門檻皆是 **初始工程目標**；導入公司資料後，必須以 Golden Dataset、硬體基準與業務風險重新校準，不得宣稱為未經驗證的產品保證。

## 4. 已確認設計決策

- 以 **Mold AI Platform** 為共用底座，各需求做成可版本化 Capability，不建立互不相容的單點工具。
- 以 **專用 Web UI 為主要工程工作台**；ChatGPT、其他支援 MCP 的 Client 為第二入口。
- Embedded Engineering Assistant 顯示為產品能力，不在 UI 將模型供應商寫死為 ChatGPT、Claude 或特定模型。
- CAD Similarity、Design Review、製程預測與 CAE 判定不依賴 LLM 才能成立；LLM 主要負責語意理解、工具選擇、整合與說明。
- 重型任務採非同步 Job + Queue + Worker；禁止讓 CAD/CAE/Embedding 長任務綁死同步 HTTP 連線。
- Demo 與 Enterprise 使用相同 Data Contract、Capability Contract 與 API；正式化主要替換 Connector、Storage、Identity、Model 與部署拓撲。
- 規則、模型、輸入檔、衍生物與結果均須版本化並保存 Lineage。
- 跨客戶、供應商與專案資料必須先通過權限過濾，再進行關鍵字或向量搜尋。

## 5. OpenAI／ChatGPT 能力聲明基線

以下只描述 2026-08-25 查證到的官方能力，不把帳號方案、Workspace Policy 或仍可能變動的 UI 流程寫成永久假設：

- OpenAI 官方目前將 Plugin 描述為可包含 Skills、MCP Server 與選用 UI；MCP Server 可提供工具、結構化結果及可選 UI resource。[Plugin architecture](https://developers.openai.com/plugins/concepts/plugins)
- MCP Production 端點宜為穩定 HTTPS 並使用 Streamable HTTP；存取私人資料或執行動作時須有授權機制。[MCP server](https://developers.openai.com/plugins/concepts/mcp-server)
- ChatGPT Developer Mode 可連接可公開到達的 HTTPS MCP 端點或官方 Secure MCP Tunnel；其可用性可能受帳號與 Workspace Policy 影響，因此 Demo 前必須完成「帳號能力預檢」。[Connect and test your plugin](https://developers.openai.com/plugins/deploy/connect-chatgpt)
- ChatGPT Web 可使用檔案、專案與 Plugins 進行工作，但本規格不假設 ChatGPT 會替第三方完整工程 Web UI 提供任意託管或遠端桌面能力。[ChatGPT on the web](https://learn.chatgpt.com/docs/web)
- Plugin/MCP 工具必須落實最小權限、明確同意、Server-side validation、不可逆操作人工確認及稽核紀錄。[Security & Privacy](https://developers.openai.com/plugins/guides/security-privacy)

開發前應再次執行官方文件與帳號能力檢查。若能力、名稱或操作流程改變，只調整 ChatGPT Adapter 與操作手冊，不改動核心 Capability Contract。

## 6. 尚待企業需求訪談確認

- 「100 萬筆」的單位是 Project、Mold、Part、Drawing 還是 File。
- 實際 3D/2D 格式、CAD Kernel 相容性、原生 CAD 授權與轉檔責任。
- 各產品線對「相似」的工程定義與可用 Ground Truth。
- Design Rule 來源、審核者、版本、生效日與例外核准流程。
- Moldflow 版本、授權、API 可用性及可取得的原始 Result。
- Trial、MES、Defect、Corrective Action、Quotation、Maintenance 與 Shot Count 的資料完整度。
- Machine UI→Excel 的目標是「欄位資料正確」或「畫面版面 1:1 重建」。
- 客戶／供應商／專案資料隔離政策及 LLM 可外送的資料分級。

## 7. 建議使用方式

第一次評審先讀 01、02、04、09；Demo 開發團隊再讀 05、06、07、10；資料與企業架構團隊以 03、04、07、08 為主。所有需求變更應更新需求 ID、變更紀錄與 09 的追溯矩陣。
