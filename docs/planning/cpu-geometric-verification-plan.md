# CAD 相似搜尋：CPU 精細幾何驗證開發規劃

日期：2026-09-07。狀態：開發基準；先提交本文件，再分階段實作與測試。

## 1. 目的與範圍

解決外輪廓統計相近、實際孔洞／肋骨／局部配置不同的 CAD 仍得到高分問題。
保留現有 Qdrant 粗召回、32D 特徵、資料治理、非同步工作與歷史搜尋。
加入 CPU 幾何驗證；不要求 GPU、不呼叫 LLM、不刪除或重建既有資料。
分数是演算法指標，不是相似機率、工程核准或可沿用製程的承諾。

相關文件：[公開 CAD 評估](public-cad-similarity-evaluation-plan.md)、
[Stage 47](../development/stage-47-public-cad-evaluation.md)、
[預覽非同步保護](../development/stage-48-preview-request-ownership.md)。

## 2. 現況與已確認缺口

- `cad_similarity_v2.py`：4096 面積加權點、比例／慣性／solidity／convexity、
  8-bin D2、8 個低階 Zernike power、8-bin 法向直方圖，共 32D。
- `cad_shape_scoring.py`：7 分項 Hellinger／L1 距離與固定權重，指數轉成分數。
- 幾何內缺失分項重新正規化；overall 已有工程證據完整度折減，不能說 N/A 全算滿分。
- `similarity.py`：Qdrant 粗召回上限 200，預設取 top_k*5、至少 20；
  分項重排後截斷 top_k，尚未自動進行 mesh 對位。
- `cad_registration.py`：現有手動偏差工具有 PCA/ICP；僅候選到查詢單向距離，
  ICP 受舊總分 >=0.8 限制，不能直接視為搜尋驗證器。
- 12 個公開 MFCAD 冒煙樣本只證明 rigid transform 後可找回自己；
  人工跨模型品質、無匹配門檻與大規模召回尚未驗收。

## 3. 功能需求與驗收映射

| ID | 需求 | 驗收 |
| --- | --- | --- |
| GV-01 | 固定版本、seed、點數、容差、模式及資源界限 | 回應 manifest 完整且可重現 |
| GV-02 | 只使用授權候選及受治理 STL preview，不接受任意 URL | 沿用現有候選 ACL；缺失／損毀可辨識 |
| GV-03 | 多個 proper rotation 初始姿態再精細對位 | det(rotation)>0；不鏡像、不非等比拉伸 |
| GV-04 | 雙向距離、雙向覆蓋率、F-score、P95 | subset 對完整模型不能只靠單向重疊取得高分 |
| GV-05 | 未驗證／逾時／不支援與已計算分開 | 不能把失敗標 verified 或傳回虛構零距離 |
| GV-06 | 精細證據參與最終排序 | 舊粗分高但表面不合者降分；保留原始分數 |
| GV-07 | 固定提交時政策與向後相容 | Worker 不受提交後設定變更影響；歷史不重算 |
| GV-08 | 新增中英 UI 證據及限制 | 顯示覆蓋、尺度模式、誤差與非校準警語 |
| GV-09 | 對相同內容與設定重用計算 | 快取鍵含双向有序 checksum、版本、模式、參數 |
| GV-10 | 不同搜尋意圖分開 | 外形可等比縮放；工程尺寸比對保留已知同單位尺度 |
| GV-11 | 局部結構與品質訊號 | 多尺度／高曲率證據獨立，不污染面積加權整體指標 |
| GV-12 | 允許無可靠匹配 | 人工資料校準門檻後啟用；未校準不能宣称可靠拒絕 |

## 4. 目標流程

1. 檢查已處理、已索引、來源品質与授權範圍。
2. Qdrant 以現有向量粗召回；工程篩選保持不變。
3. 用既有分項排序決定精細驗證候選預算，不把該排序視為答案。
4. 讀取有限大小 mesh、固定 seed 面積加權取樣；查詢點僅取一次。
5. 多方向 PCA proper rotations，按雙向目標選幾個初始姿態做 ICP。
6. 對位後用所有評估點計算雙向指標，不只計 ICP 內點。
7. 保守融合：新分數不能被局部低誤差或不相關 metadata 推成高形狀相似。
8. 最終結果保留基準分、精細證據、狀態、版本及限制。

## 5. CPU 核心設計

### 5.1 輸入與前處理

- 僅有限、非空、有面積的三角網格；點數、面數、preview bytes 與迭代有上限。
- 不自動補洞／修復以免創造不存在的工程表面；開放 mesh 可以做 unsigned 比較。
- 預設外形模式：各點雲中心化，使用旋轉不變尺度等比正規化。
- 尺寸模式：單位已知且統一後才能比較；未知／異單位不能暗中當成 mm。
- 正規化比例、中心與 transform 必須可追溯；normalized transform 不能直接送給
  期待原始 CAD 座標的 viewer。自動排序與既有手動偏差 heatmap 先維持分離。

### 5.2 對位與距離

- 嘗試主軸 permutation 與符號組合，僅接受正行列式旋轉。
- 依雙向距離選多個起始姿態，再以 bounded ICP 精化；不能用粗分 >=0.8 才允許精化。
- 保留最佳雙向解；無收斂與不確定對稱性不可等同已找到全域最佳解。
- 比較的是取樣表面近似，不是精確 CAD 曲面 Hausdorff。
- 指標：query→candidate 与 candidate→query mean/P95；雙向平均距離；
  各方向容差內比例；F-score；最小方向覆蓋率；未匹配比例。
- 容差以明確正規化尺度比例或工程單位表示；先用版本固定的實驗值，
  不把任意固定 mm 門檻套到所有模型。
- 兩個模型獨立取樣会有 sampling noise；測試 remesh、seed 與多尺度敏感度。

### 5.3 分數與狀態

- `computed`：完成指標計算；不代表人工確認相似或全域最佳對位。
- `unavailable`：preview 不存在／損毀／超上限；`budget_exceeded`：預算不足。
- `not_requested`：舊工作或停用精細政策；保留舊排序语义。
- 首版為保守 heuristic：基準 overall 乘以不大於 1 的表面吻合 factor；
  factor 依雙向覆蓋与平均／尾端距離，而不是重新放大粗分。
- 未完成驗證者不能當成已驗證：另標 reference-only，分數欄保留基準而非冒充最終驗證分。
- 同一清單需明確區分已計算結果与待驗證候選；預算外候選不能用粗分擠過精細結果。
- 基準工程各 lane 保留原值；展示形狀證據和工程證據，不重複宣称 probability。

## 6. API/Data Contract（新增欄位，保留舊契約）

候選新增 `geometric_verification`：

```json
{
  "status": "computed",
  "algorithm": "cpu-surface-verification@1.0",
  "mode": "normalized_shape",
  "score_factor": 0.63,
  "query_coverage": 0.82,
  "candidate_coverage": 0.65,
  "f_score": 0.725,
  "mean_distance": 0.028,
  "p95_distance": 0.09,
  "distance_unit": "normalized_rms_radius",
  "tolerance": 0.08,
  "sample_count": 1536,
  "calibration_status": "not_calibrated"
}
```

數字僅示意，非實測結果。無法計算時只給狀態、版本與安全 error_code，不杜撰 metrics。
新增基準 overall 供追溯；保留 existing `geometry_ranking` 與 breakdown。
工作 input_snapshot 固定精細政策；舊 snapshot 缺欄位按舊版執行。
manifest 應包含所有影響結果的參數；調整任何參數需新版算法或固定設定 hash。

## 7. 候選預算、快取與部署

- 首版精比對上限 10 個候選；取樣 1536 點、單方向 KDTree workers=1；
  每姿態 ICP 有迭代上限。參數是初始開發值，需效能實測，不是 SLA。
- Worker 執行，不在 HTTP request 裡處理大型 CAD；單候選失敗不破壞整份搜尋。
- 逐項檢查 elapsed budget；完整 hard timeout 需 process isolation／Celery limits，
  不能聲稱 Python deadline 能中断所有 C extension。
- 精細結果快取只儲存無 URL／無使用者資訊的數值；命中前仍須授權。
- key 須使用實際內容 checksum、算法版本与所有參數；不要只用 artifact 名稱。
- 首版可用 bounded process-local cache；跨 Worker persistent cache 是另階段工作。
- 不變更 extractor 32D，不需要全庫 reindex；只新建搜尋套新政策。
- 可切回 disabled 基準政策；既有搜尋／操作紀錄不可覆蓋。
- 外網發布沿用現有 Docker 專案與私人入口，不新增公開權限。

## 8. 測試與品質驗收

### 程式回歸（自動）

- 同模型、旋轉／平移／等比縮放（外形模式）應維持高吻合。
- cube/cylinder、plate/厚實體、subset/完整結構不能得到相同高吻合。
- 重採樣／重網格不等同設計改變；誤差容許依取樣噪聲制定。
- 零面積、NaN/Inf、空模型、檔案過大、缺 preview、deadline 皆明確降級。
- 交換 query/candidate，雙向 metric 應保持一致或在對位數值容差內。
- 缺 cache／cache 壞資料不能繞過來源檢查或污染不同模型。
- 新工作固定政策、舊工作保持基準、過期 frontend response 不覆蓋目前選取。
- 未驗證不標高度相似；中英 UI 与舊 API 結果相容。

### 真實搜尋品質（不能用單元測試代替）

1. 100–200 個具授權來源的公開多家族模型與 20–30 個人工 query。
2. 人工分級：0 不相關、1 弱相關、2 相似、3 高度相似；未知不能標 0。
3. 加入外輪廓像但孔／肋不同的 hard negatives，以及確定無匹配 query。
4. 家族、版本、變形副本放同一 split；test 不用來調分數或門檻。
5. 比較基準與新方法的 Recall@K、Precision@5、nDCG、誤判高分率、
   no-match false acceptance；報告人工覆蓋率、失敗率與各分群結果。
6. 量測粗候選 Recall；真相似未進候選池，精細算法也救不回。
7. 量測 cold/warm p50/p95、timeout 率、記憶體及隊列等待，報明硬體與 corpus。

真實資料未準備完成前，標記 `not_calibrated`；不承諾已降低實際模具誤判多少百分比。

## 9. 分階段實作與 Git 門檻

| 階段 | 交付 | 提交前測試 | 狀態 |
| --- | --- | --- | --- |
| 0 | 本規劃與契約 | 檢視對應程式／需求、diff check | 已先提交 |
| 1 | CPU 多方向雙向比對核心、合成控制與資源邊界 | 核心新測試、既有幾何回歸、lint | 已完成；22 項測試通過 |
| 2 | 工作政策快照、搜尋重排、故障分級、結果契約與中英 UI | API/Worker、UI、完整 test.ps1 | 已完成；完整回歸通過 |
| 3 | 多尺度局部證據、STEP 結構特徵、尺寸模式 | 避免網格密度偏差、單位與結構反例 | 已完成；詳見 Stage 50 |
| 4 | 擴充公開 corpus、人工標註工具、分數校準／無匹配 | 獨立 holdout 品質報告 | 工具已實作；100 份公開 CAD 已準備，人工多家族 holdout 驗收尚待完成 |
| 5 | Persistent cache、召回／延遲調優、外網 UAT | cold/warm 實測、私人入口與版本校驗 | 程式與測試完成；實際量測／發布證據見 Stage 50 |

每階段先測試通过再提交 Git；測試失敗不提交為完成。開發紀錄分開列程式完成、
品質驗收、外網部署狀態。不把本輪先完成 1–2 階段描述成全部 1–5 都完成。

## 10. 演算法參考

- [Open3D ICP](https://www.open3d.org/docs/latest/tutorial/pipelines/icp_registration.html)：
  局部對位需要初始解，fitness 与 inlier RMSE 意義不同。
- [Open3D metrics](https://www.open3d.org/docs/release/python_api/open3d.t.geometry.PointCloud.html)：
  雙向 Chamfer、Hausdorff 与 F-score 定義。實作可以重用現有 NumPy/SciPy，
  不因參考此文件就要求新增 Open3D 依賴。
