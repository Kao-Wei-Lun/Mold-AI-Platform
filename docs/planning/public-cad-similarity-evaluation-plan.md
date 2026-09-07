# 公開 CAD 相似搜尋評估與改善規劃

日期：2026-09-07。基準提交：55a727d。範圍：CPU、公開 CAD、無公司資料、無 LLM/GPU 費用。

## 1. 目標與驗收邊界

目前需要證明的是「搜尋幾何相似的 CAD」，不是「歷史模具可以直接沿用」。
公開模型缺少材料、澆口、冷卻、試模與成本時，不填入假資料，不將未知當相同。
分數是演算法相關度，不是相同機率、信心百分比或工程設計核准。
程式回歸通過、公開模型解析通過、幾何品質驗收是三個不同結果，必須分開報告。

## 2. 現況與問題

- `cad_similarity_v2.py` 使用既有 32 維 CPU 描述子，包括主軸比例、慣性、實體填充度、
  D2 分布、低階 Zernike 與法向分布；Qdrant 用來粗選候選。
- `cad_manufacturing.py` 將整個向量內積直接作為 geometry，易受常數與不同量綱區塊影響。
- 缺值目前降低 evidence coverage，但不能修復幾何排序；overall 不應被稱為信心分數。
- 同格式 STL 的三角形數不是可靠的工程拓樸證據，重新網格化不應被當作設計改變。
- 現有合成基準有助回歸，不能代替公開 CAD、獨立判讀與保留測試集。
- 不需為評分變更重建 V2 描述子或刪除資料；應獨立記錄 ranking policy。

## 3. 資料來源與授權

| 來源 | 用途 | 本輪處理 |
| --- | --- | --- |
| MFCAD | 公開 STEP、加工特徵範例、解析/檢索冒煙測試 | 固定上游提交的小型樣本，保留 SHA-256、來源及 MIT 聲明 |
| ABC | 多樣幾何、STEP/STL 跨格式、較大保留集 | 支援相同 manifest 匯入；未完成模型授權核對前不下載全庫或對外展示 |
| 公開模型的旋轉/平移副本 | 同物件變換不變性 | 明確標記 controlled_identity，不算獨立模型 |
| 自建基本幾何 | 明顯形狀反例、單元測試 | synthetic_control，不聲稱來自公開工業模型 |

來源核對：
- https://github.com/hducg/MFCAD （STEP 位置與特徵標記）
- https://github.com/hducg/MFCAD/blob/master/LICENSE （上游 MIT 聲明，需保留）
- https://deep-geometry.github.io/abc-dataset/ （作者保留模型著作權，指向 Onshape 條款）
- https://github.com/AutodeskAILab/Fusion360GalleryDataset/blob/master/LICENSE.md
  （非商業研究限制，因此不是本輪預設 Demo 語料）

公開可下載不等於任意重新發布。本輪原始 CAD 留在 gitignored `.runtime`，不加入 Git、
不自動匯入線上使用者資料庫、不自動公開 Web 下載。Git 保留腳本、清單、摘要與測試。

## 4. 評估資料契約

Corpus manifest 使用 `schema_version=1.0`，含 corpus_id、來源、上游 revision、license、
models、queries。每個 model 必須有 id、relative path、sha256、source_url、family_id、
split (`development` / `holdout`)、unit (`mm` / `unknown` 等來源已知單位)。
檔案不得逃出資料根目錄，拒絕絕對路徑、父目錄穿越、checksum 不符與重複 id。
同一 family 不得跨 development/holdout；變形版本繼承原始 family。

Query 必須有 id、model_id、split、kind、judgments。
- `controlled_identity`：來源相同的受控剛體變換，只能證明同物件檢索。
- `human_geometry`：人工判讀的幾何相關度 0/1/2/3，保留 reviewer、reason。
- judgment 不得由本次搜尋分數自動產生；未判讀不是負例。
- query 可標記 `expected_no_match`，必須具備完整候選判讀才能計算拒答品質。
- 訓練/調參不使用 holdout；同物件的查詢及正例可共存於同一 split 的檢索庫。

單位未知不推斷為 mm。shape-only 不使用尺寸、材料與製造欄位，不補假值。
Benchmark 不呼叫 LLM，也不把任何 CAD 上傳外部 API。

## 5. 評估方法與報表

提供離線 management command，讀取 manifest、驗證本機檔案、解析 STEP/STL，
使用與線上相同的描述子及幾何評分函式，不修改業務 DB/Qdrant。
報表輸出到 stdout，可由使用者自行保存；包含 manifest checksum、演算法版本、
extractor 版本、sample count、seed、split、解析失敗與查詢明細。

指標定義：
- Recall@K = 已標記正例在前 K 中數量 / 該查詢已標記正例總量。
- MRR = 第一個已標記正例排名倒數，未找到為 0。
- nDCG@K 使用 gain = 2^grade - 1；未判讀項不當已確認負例，另報 judged coverage。
- no-match false acceptance 僅在指定 threshold 且完整判讀的 no-match query 計算。
- 查詢時間報 p50/p95，解析/描述子時間分開，記錄模型及候選量。
- controlled 與 human、development 與 holdout 分開統計，不混為一個準確度。
- report 必須標示尚未有 human holdout、不能宣稱 real-world validated 的情況。

第一輪收斂目標是 100–200 個模型與 20–30 個人工查詢，非本輪立即下載承諾。
本輪先交付小樣本公開冒煙測試及可擴充評估工具。沒有人工標籤時，品質 gate 為
`not_evaluated`，不是 PASS。之後人工作業完成才討論 Recall@5 目標（暫定 >=0.8）、
錯誤高分與效能預算；不得為了通過而用最終測試集反覆調閾值。

## 6. 幾何評分修改

新增獨立版本的 block-distance 幾何評分：比例/慣性、solidity/convexity、D2、
Zernike、法向分布各自比較，避免整體 cosine 掩蓋局部差異。輸出 block scores、
可用權重覆蓋率、ranking policy。缺少 block 不補相似值。
保留 cosine 做 coarse retrieval 和基線；API 回傳的 geometry 是重排結果，說明其意義。
舊資料缺少結構化 block 時顯式回退，回傳 policy/reason，不混成新評分結果。
保持 32D 索引不變；本輪改善的是 reranking，粗選召回上限仍須後續量測。
不將低階 descriptor 當完整局部形狀辨識；CPU 3D 對位仍為後續證據，不冒稱已自動重排。

STL face/edge count 不參與 topology；STEP/stp 正規化為同表示類別。沒有可比較證據
顯示 N/A 及原因。既有製造近似值仍須標示 approximate，不轉成確定的模具可用性。

## 7. UI 與相容性

- 保留查詢、預覽、3D 差異與現有路由，不大改表單。
- 顯示「幾何排序未經人工公開資料驗收」及「分數不是工程適用機率」的中英說明。
- 說明 geometry 與 evidence-adjusted overall 的差異，不再稱 overall confidence。
- 新欄位為 additive；歷史搜尋仍可以顯示，缺欄位不報錯。
- geometry block 詳細資訊可用於後續解釋，不要求用戶理解演算法參數。

## 8. 分階段交付與 Git gate

| 階段 | 交付 | 測試／提交條件 |
| --- | --- | --- |
| P0 | 本詳細規劃及文件索引 | 僅文件提交，先於任何程式修改 |
| P1 | manifest 驗證、離線 evaluator、指標與版本化報表 | 路徑/checksum/洩漏/標籤/指標/空結果測試通過後提交 |
| P2 | block 評分、線上整合、表示類型保護、UI 中英說明 | 同模型變換、明顯反例、N/A、API/前端回歸通過後提交 |
| P3 | 可重現公開小樣本準備工具、實測報告、操作文件 | 執行公開樣本測試，完整 regression、build、Compose 檢查後提交 |

每階段文件追加實際結果。測試失敗先修正再提交。Git 為本機 commit；不自動 force push，
不改寫歷史，不清除使用者資料。原有單一 Docker Compose 專案及共用 app image 架構不變。
本輪不變更 Sites hosting、tunnel 或秘密；若部署新 image，僅重建既有 app services，
不刪 volume，不增加第二個專案。

## 9. 後续品質工作（不冒稱本輪已完成）

1. 授權核對後擴充 ABC 與多家族公開語料，避免只對加工方塊有效。
2. 人工標記與第二人抽查、標籤分歧紀錄、凍結 holdout；公開模型也需要人類相關度判斷。
3. 獨立量測 Qdrant coarse Recall@N 與 reranking，必要時擴大/多路召回。
4. 資源有界的自動雙向對位重排、局部孔/肋/槽特徵；校準 no-match 閾值。
5. 工程適用性必須等授權工程 metadata/歷史案例到位再驗收。

## 10. 執行紀錄

- P0：規劃建立，待文件提交。
- P1–P3：待實作與測試；公開資料搜尋品質尚未驗收。
