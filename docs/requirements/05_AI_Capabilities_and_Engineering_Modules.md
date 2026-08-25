# 05 — AI Capability 與工程模組規格

## 1. Capability 共通契約

每個能力必須註冊：

- `capability_id`、semantic version、owner、status。
- input/output JSON Schema、supported media、最大尺寸。
- required permission、data classification、allowed providers。
- resource class（API/CPU/CAD/GPU/CAE/Excel）、timeout、retry policy。
- deterministic/nondeterministic、model/rule/index dependencies。
- validation suite、quality metrics、known limitations、fallback。
- evidence/lineage requirements、UI actions、MCP exposure policy。

- **CAP-001**：Domain engine 的結構化結果為 system of record；LLM narrative 為衍生表示。
- **CAP-002**：未知、無法解析、證據不足必須有明確狀態，不可默認為 PASS 或零風險。
- **CAP-003**：輸出需要 evidence refs、quality flags、version refs 與 calibrated confidence（適用時）。
- **CAP-004**：高風險建議必須列適用條件、限制、批准需求與禁止自動執行。
- **CAP-005**：每個 Capability 支援固定 Golden Set 的離線評估與 production telemetry。

## 2. CAD Similarity Search

### 2.1 Pipeline

```text
CAD/2D Input
→ validate/hash/version
→ parse B-Rep / mesh / drawing
→ geometry + topology + manufacturing features
→ optional point-cloud / multi-view embeddings
→ metadata normalization
→ security + applicability filter
→ ANN candidate retrieval
→ geometry/metadata reranking
→ detailed comparison
→ explainable Top K
```

### 2.2 Feature lanes

- Geometry statistics：bbox、volume、area、aspect ratio、thickness/draft distribution。
- Topology：face/edge/wire、surface types、adjacency、holes/pockets/ribs/bosses（能力成熟後）。
- 3D representation：B-Rep/mesh/point cloud descriptor/embedding。
- Multi-view visual：標準視角與 ISO render embeddings。
- 2D drawing：view/layout/text/dimension feature，與 3D lane 分開校準。
- Metadata：product、material、mold type、cavity、runner/gate/cooling、size、tonnage。

### 2.3 Scoring

初始 Profile 可使用加權組合，例如 geometry 30%、topology 20%、dimension 15%、visual 15%、material/product 10%、manufacturing 10%。這只是可配置基線；每個產品線須以標註資料學習或校準。

分數輸出須包含：Overall、sub-scores、weight version、feature availability、missing-lane treatment、major similarities/differences。缺少 feature 時不得默默以零分處理，必須依 Profile 規定重新正規化或標記不可比。

### 2.4 Search modes

- Whole-part search。
- Metadata-constrained search。
- Query by existing case / uploaded file。
- Local region search（Enterprise phase）：使用者圈選 Rib/Boss/Gate/Cooling region。
- Reverse evidence search：從 defect/CAE finding 找相似 geometry + case。

### 2.5 Metrics

- Recall@10、Recall@20、nDCG@10、MRR、工程師 Top-K acceptance。
- Query latency（candidate/rerank/detailed 分開）。
- Index coverage、freshness、parse success、feature missing rate。
- 不同產品／尺寸／格式／客戶 slice 的公平表現。

## 3. AI Design Review

### 3.1 決策原則

Rule Engine + Geometry Engine 做判定；LLM 只用於規則檢索輔助、風險解釋、報告文字與改善選項整理。

### 3.2 Rule lifecycle

Draft → Technical Review → Approved → Effective → Superseded/Retired。Rule 修改產生新版本，舊 Review 永遠指向舊版本。

### 3.3 Rule evaluator

每條規則包含 applicability、required measurements、formula/condition、unit/tolerance、severity、reference、evidence renderer。Evaluator 採受限 DSL 或註冊函式，具 unit test 與 CAD fixtures。

### 3.4 Result states

- PASS：可量測且符合。
- FAIL：可量測且違反。
- NOT_APPLICABLE：適用條件不符。
- NOT_EVALUATED：資料、幾何或 evaluator 不足。
- ERROR：執行失敗。

### 3.5 Example

Rib thickness ≤ 0.6 × nominal wall thickness：輸出 nominal wall、allowed rib、actual rib、unit、tolerance、Face/region、risk（sink mark）、rule/reference version。LLM 不計算 1.55 是否大於 1.2。

### 3.6 Metrics

以規則及產品 slice 計算 precision、recall、false positive、false negative、location accuracy、measurement error、not-evaluated rate。安全／重大品質規則優先控制 false negative。

## 4. Process / Trial Analysis

### 4.1 輸入與融合

- Material、machine、mold/part revision、process parameters。
- Defect type/severity/location/image、inspection method。
- Similar mold/case、CAE metrics、geometry features、歷史 corrective actions。

### 4.2 Output lanes

- Similar cases：案例、相似理由、採取行動與 outcome。
- Rule findings：超出核准 window、互斥條件或資料品質問題。
- Predictive ranking：可能 root causes，標示為關聯／模型推論而非因果事實。
- Recommendations：建議步驟、before/after range、約束、來源、expected effect、stop condition。

### 4.3 Guardrails

- 不提供未見於受控範圍的精確參數。
- 機台／材料／模具不相容時禁止套用歷史參數。
- 預設不寫入 MES/PLC；人工核准後也只輸出變更建議單。
- 所有建議有「為何」「依據」「不確定性」「如何驗證」。

### 4.4 Metrics

Top-k root-cause recall、recommendation acceptance、改善成功率、time-to-resolution、unsafe recommendation rate、abstention precision、資料完整度。

## 5. CAE / Moldflow

### 5.1 Integration priority

1. 官方／授權 API 或原始 result export。
2. 結構化 report export。
3. PDF/table extraction。
4. Screenshot OCR/vision fallback。

Connector 必須記錄實際可用層級，不能將 screenshot demo 寫成已完成 Solver API 整合。

### 5.2 Canonical metrics

依 Solver 能力映射 fill time、pressure、temperature、clamp force、weld line、air trap、cooling、warpage、shear/volumetric shrinkage 等。每個 metric 有單位、field/scalar/region、location、quality 與 parser version。

### 5.3 Analysis

- Rule：threshold、gradient、imbalance、hotspot、location conflict。
- Comparison：基準與候選 Run 的 compatible subset、delta 與 trade-off。
- ML：風險或 surrogate model，需限定 applicability domain。
- LLM：將結構化 finding 轉成工程摘要與查證問題。

### 5.4 Optimization

正式版才納入 closed-loop simulation orchestration；必須定義 objective（warpage/pressure/cycle 等）、hard constraints、parameter bounds、solver budget、convergence、feasibility 與人工批准。

## 6. Machine UI → Excel

### 6.1 兩種產品模式

- `machine_ui.extract_parameters`：資料正確優先，Demo 必做。
- `machine_ui.reconstruct_layout`：視覺 1:1 近似，獨立 Roadmap 與驗收，不與抽值準確率混用。

### 6.2 Pipeline

Image quality check → orientation/perspective correction → OCR → layout/component detection → HMI profile match → field mapping → unit/valid-range validation → human correction → Excel render。

### 6.3 Output

Parameter code、display label、raw OCR、normalized value、unit、confidence、bounding box、validation status、reviewer correction。低信心或超出範圍必須要求確認。

### 6.4 Metrics

Field detection F1、character/word error、numeric exact match、unit accuracy、critical field accuracy、human correction rate、per-profile coverage。1:1 模式另量測 layout similarity 與 component match。

## 7. Knowledge / RAG

### 7.1 Sources

Design guideline、customer specification、Moldflow/Trial/Maintenance report、quotation、SOP、meeting minutes、historical issue。每個來源有 authority、effective date、classification、ACL 與 owner。

### 7.2 Retrieval

- ACL/security filter before retrieval。
- Hybrid lexical + vector + metadata retrieval。
- Query decomposition：文件、Mold Case、Trial、CAE 多 lane。
- Rerank、deduplicate、authority/freshness weighting。
- Claim-level citation；無證據則 abstain。

### 7.3 Ingestion safety

解析器隔離、隱藏文字與 prompt injection scan、頁／段落 locator、PII/secret detection、obsolete/duplicate handling。文件中的指令一律視為資料，不得改變系統或工具政策。

### 7.4 Metrics

Retrieval Recall@K、citation precision、answer groundedness、unsupported claim rate、ACL leakage=0、freshness、abstention quality、latency。

## 8. Quotation AI

使用 Similarity Engine 找 reference cases，再以 cost feature/model 輸出估計區間、成本 driver、資料日期與 reference cases。必須區分 quote、actual cost、currency、inflation/exchange version。Demo 可展示規則／案例估算；正式預測需足夠歷史 actual cost 與審核。

## 9. Maintenance AI

先建立 Mold 履歷與 due-rule，再視 shot count、repair history、failure mode、operating condition 資料成熟度導入 survival/time-series model。輸出 time horizon、risk、confidence、drivers、recommended inspection；不得把缺資料的模具判為低風險。

## 10. Capability dependency map

| Capability | 必要底座 | LLM 必要性 | Demo |
|---|---|---:|---:|
| CAD Similarity | CAD parse、feature、vector、rank | 否 | 核心 |
| Design Review | Geometry、Rule、evidence | 否 | 核心 |
| Process/Trial | Canonical case、retrieval、rule/ML | 否 | 核心簡化 |
| CAE | Result connector、metric、rule | 否 | 範例 |
| Machine UI→Excel | Vision/OCR、schema、renderer | 否 | 次核心 |
| Knowledge/RAG | Ingestion、retrieval、citation | 回答生成可替換 | 核心簡化 |
| Assistant | Capability API、LLM Gateway | 是 | 核心入口 |
| Quotation | Similarity、cost ground truth | 否 | 後期 |
| Maintenance | History、shot count、failure data | 否 | 後期 |
