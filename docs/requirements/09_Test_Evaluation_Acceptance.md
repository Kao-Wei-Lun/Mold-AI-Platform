# 09 — 測試、AI 評估、效能與驗收

## 1. 測試策略

採測試金字塔加 AI evaluation：unit → contract/schema → component → integration → end-to-end → performance/resilience → security/adversarial → domain acceptance。每項需求 ID 應對應測試 ID、資料集版本、執行環境與證據。

## 2. 測試資料分層

- **Fixtures**：小型可人工驗證 CAD、Rule、OCR、CAE，供 unit/CI。
- **Golden Dataset**：Domain Expert 標註的相似、違規、citation、trial outcome，版本固定。
- **Robustness Set**：損壞、缺值、不同單位、旋轉、噪聲、極端幾何、過大檔案。
- **Security Set**：prompt injection、惡意文件、IDOR、SSRF、over-permission、malware fixtures。
- **Scale Set**：10K/100K/1M metadata/vector 或授權 CAD subset，與功能資料分開。
- **Holdout Set**：禁止用於調參，只有 release gate 使用。

資料切分避免同一 Mold revision 或近重複 CAD 跨 train/test，防止洩漏。

## 3. 共通測試

- **TST-CON-001**：OpenAPI/JSON Schema/MCP tool/Event backward compatibility。
- **TST-CON-002**：Public、Mock Company、真實 Connector 對同一 canonical contract。
- **TST-LIN-001**：每個結果可追溯 input/parser/model/rule/index/job/human decision。
- **TST-IDM-001**：重送同一 idempotency key 不建立重複結果。
- **TST-FAIL-001**：DB/vector/queue/provider/worker 中斷時 typed failure、retry/fallback 正確。
- **TST-OBS-001**：request/job/tool/provider trace 連續，log 無 secret/sensitive payload。

## 4. CAD ingestion 測試

測試格式、單位、assembly/solid/shell、invalid topology、超大/損壞檔、hash duplicate、parser timeout。以人工或可信幾何工具比對 bbox、volume、surface area、face count、measurement tolerance。

初始 Demo 目標：

- Supported STEP/STL parse success ≥ 95%（在定義好的 Demo corpus）。
- Synthetic geometry 核心量測誤差在每條 Rule 定義 tolerance 內。
- 無法解析檔 100% 進 ERROR/NOT_EVALUATED，不產生假 PASS。

## 5. Similarity 評估

### 5.1 Label protocol

至少 2 位工程師依明確 rubric 標註 identical/strong/usable/weak/not relevant，記錄產品線、原因與 disagreement；建立 adjudication。

### 5.2 Metrics

- Recall@10/20、nDCG@10、MRR、Precision@K。
- Top-K 工程師可用率、pairwise preference。
- Parse/index coverage、missing feature、cold/warm latency。
- Slice：product、size、format、material、customer、new/old revision。

### 5.3 初始 Gate

- Demo Golden Set Recall@10 目標 ≥ 0.80，Recall@20 ≥ 0.90；若 dataset 太小，須附 confidence interval 與樣本數。
- 任何單一 slice 不得隱藏；公司 Pilot 門檻由 Domain Owner 重新核准。
- Score explanation 與實際 profile/feature 一致率 100%，不得由 LLM編造分項。

## 6. Design Review 評估

每條 Rule 建 positive/negative/boundary/not-applicable/not-evaluable fixtures。

- Precision、Recall、FPR、FNR、measurement error、location accuracy、not-evaluated rate。
- 重大規則以 Recall/FNR 優先；誤判成本不同不得只看 macro accuracy。
- Rule/profile version regression：新版本只影響預期案例。

Demo 初始 Gate：

- 10–30 條 Rule 各自 unit fixtures 100% 通過。
- Golden CAD 上整體 precision/recall 目標 ≥ 0.90；每條規則另報。
- PASS/FAIL/NOT_EVALUATED 狀態與 evidence 完整率 100%。

## 7. Process/Trial 評估

- Similar case Recall@K、root cause Top-3 recall、ranking agreement。
- Recommendation applicability、unsafe/out-of-bound rate、engineer acceptance、outcome improvement。
- Calibration/Brier 或 reliability（若輸出機率）。
- 缺少 material/machine/revision 等關鍵欄位時 abstention 是否正確。

Demo 不以 synthetic outcome 宣稱真實改善率；只驗證流程、來源與 guardrail。

## 8. CAE 評估

- Parser field/value/unit/location exactness。
- Run compatibility 判斷與 delta calculation。
- Rule finding precision/recall、hotspot location overlap。
- Narrative factual consistency/citation completeness。
- Solver/version/material/mesh 不一致時應拒絕不當比較。

## 9. Machine UI→Excel 評估

- Field detection precision/recall、numeric exact match、unit accuracy、critical field accuracy。
- Low-confidence routing、human correction rate、Excel schema/format validation。
- Slice：angle、blur、reflection、resolution、language、HMI profile。

Demo Gate：定義好的 HMI profiles 上 critical numeric exact match 目標 ≥ 95%；未達 confidence threshold 的欄位不得無提示匯出。

## 10. Knowledge/RAG 評估

- Retrieval Recall@K、citation precision、groundedness、unsupported claim rate、abstention。
- Authority/effective date、obsolete source、duplicate source handling。
- ACL leakage、cross-tenant retrieval 必須為 0。
- Prompt injection documents 不得改變 tool/system policy。

Demo Gate：每個 factual claim 有 evidence，citation precision 目標 ≥ 95%，unsupported critical claim = 0。

## 11. Assistant/MCP/UI Action 評估

- Tool selection、required argument completeness、schema validity、job polling flow。
- Context-aware query resolution；切換 project/selection 後不使用 stale context。
- Read/write approval、cancel、permission denial、provider fallback。
- UI Action protocol invalid type/expired target/wrong page/unauthorized target 均拒絕。
- 官方 ChatGPT preflight：Developer Mode、Workspace Policy、endpoint、OAuth、tool discovery、sample calls。

Gate：unsafe tool execution、approval bypass、cross-project context leakage、fabricated tool success 均為 0。

## 12. 效能測試

### 12.1 場景

- 10K/100K/1M vector candidate search，測 filter selectivity。
- CAD ingest/feature/index 單檔與批次。
- 3/10/50 concurrent users，interactive + long jobs 混合。
- Queue burst、GPU memory saturation、provider 429/latency。
- cold start、cache warm、index rebuild、connector incremental sync。

### 12.2 報告

記錄硬體、OS/driver、container version、dataset/index/profile、query mix、warmup、sample size、p50/p95/p99、throughput、error、resource。不得只報平均值。

Demo 目標見 02；Enterprise SLO 在 sizing/pilot 後確定。

## 13. Resilience/DR

- Kill worker during CAD/CAE job；確認 heartbeat/stale/retry/idempotency。
- Restart API/queue/DB/vector；確認已接受工作狀態與 typed degradation。
- Provider outage；核心 CAD/Rule 可用、Assistant 明確降級。
- Backup restore：DB/object/manifest/index rebuild，驗證 RTO/RPO。
- Index version rollback 與錯誤 Rule/Model kill switch。

## 14. 安全測試

- SAST/SCA/container/image/IaC/secret scan、SBOM、dependency license。
- AuthN/AuthZ、IDOR、tenant isolation、vector filter、signed URL、export scope。
- File parser fuzz/limits/malware/quarantine、zip bomb。
- API/MCP injection、prompt injection、tool escalation、SSRF、OAuth scope/audience/replay。
- Log/trace/audit secret/PII leakage。
- 外部 tunnel/gateway TLS、Rate limit、brute-force、kill switch。

Production 前需獨立安全評審／滲透測試；P0/P1 全數關閉。

## 15. UAT 劇本

### UAT-01 Similarity

工程師上傳新 CAD，Top 10 包含已知相似案；開啟第一名顯示分項、差異、版本、3D evidence；標記 relevance 後產生 feedback event。

### UAT-02 Design Review

執行指定 Rule Profile；顯示 Rib violation actual/limit/location/reference；Reviewer waiver 需理由與批准，重新執行仍保留原結果與 waiver。

### UAT-03 Process/Trial

輸入 defect/parameter，取得相似案例與受限建議；缺少 material 時系統要求補充或 abstain，不給精確參數。

### UAT-04 ChatGPT/MCP

在 ChatGPT Web 呼叫搜尋，取得 job ID、status、結果與 deep link；未授權 mold ID 回 permission denied 且無存在性資訊。

### UAT-05 LLM outage

關閉 provider；CAD Search/Review 正常，Assistant 顯示降級，無假成功。

## 16. Demo 驗收清單

- **ACC-D-001**：02 所有 MUST 需求有 pass/fail/waived 證據。
- **ACC-D-002**：全新 Windows host 依文件可重建並載入 seed data。
- **ACC-D-003**：專用 UI 與 MCP 對相同輸入得到相同 domain result/job ID。
- **ACC-D-004**：所有結果具 evidence/version/lineage；Demo/Public 標示完整。
- **ACC-D-005**：外部存取安全基線、秘密管理、權限隔離與停止機制驗證。
- **ACC-D-006**：已知限制與未完成 Enterprise 功能不被隱藏。

## 17. Enterprise Pilot 驗收

- **ACC-E-001**：SSO/group/ACL mapping 與 cross-tenant tests 全數通過。
- **ACC-E-002**：至少兩個 Company Connector initial + incremental + reconciliation。
- **ACC-E-003**：Golden/Holdout 指標達 Domain Owner 核准門檻。
- **ACC-E-004**：Shadow/pilot 無重大 workflow regression，具使用者與業務 KPI。
- **ACC-E-005**：SLO、backup/restore、DR、security、audit/SIEM、runbook/on-call 完成。
- **ACC-E-006**：Model/Rule/Capability lifecycle 與 rollback 實際演練。

## 18. 追溯矩陣範本

| Requirement | Design/Component | Test | Dataset | Evidence | Owner | Status |
|---|---|---|---|---|---|---|
| D-SIM-003 | Similarity Result Schema/UI | T-SIM-EXPL-01 | demo-golden-v1 | link | Search Owner | Planned |
| D-REV-002 | Rule Engine | T-REV-STATE-01 | rule-fixtures-v1 | link | Rule Owner | Planned |
| D-MCP-003 | MCP Gateway/Job API | T-MCP-ASYNC-01 | seed-v1 | link | Platform Owner | Planned |
| E-IAM-005 | Policy/Vector Filter | T-SEC-ACL-07 | acl-fixture-v1 | link | Security | Planned |

Release 不能只有「模型準確率」；Contract、安全、Lineage、營運與人工流程皆為 Gate。
