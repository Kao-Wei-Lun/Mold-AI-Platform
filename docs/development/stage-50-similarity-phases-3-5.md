# Stage 50：幾何搜尋第 3–5 階段

依據：[CPU 幾何比對開發規劃](../planning/cpu-geometric-verification-plan.md)。

## Phase 3：局部結構與實際尺寸

- 新搜尋採 `cpu-surface-verification@2.0`；`@1.0` snapshot 仍可執行原先的全域比較。
- `comparison_mode`：`normalized_shape`（預設，允許等比縮放）、
  `engineering_size`（只旋轉／平移，先換算 mm；候選不能独立正規化大小）。
- `tolerance_mm`：0.001–10 mm，預設 0.5；不是 CAD 精密量測承諾。
  未知單位 query 在提交前回 400，未知單位候選在精比對時列 reference-only。
- 多容差曲線：0.5×、1×、2×；局部 2³／4³ 空間區域比較，至少 12 點才報局部覆蓋。
  較差四分之一區域覆蓋作保守折減；只用面積加權點，不以三角面數當設計特徵。
- STEP subprocess 新增 B-Rep 曲面相鄰類型、各曲面面積、正規化圓柱半徑及圓柱中心間距。
  這是結構證據，不是完整孔洞／肋骨／滑塊語意分類器；曲面分割方式仍可能影響統計。
- 新增 CADModel.brep_structure JSON（migration 0024）；不變更舊向量 checksum。
  舊 STEP 必須用既有重新處理流程才能補結構；不自动重算／覆盖历史搜尋。
- API 回傳 local_evidence、tolerance_curve、brep_structure，UI 中英顯示模式、容差與局部證據。
- cache key 增加模式、單位、容差與結構內容，避免跨模式或補資料後誤用舊結果。
- 自動驗證 transform 仍為內部正規化座標；不直接套入原始幾何 heatmap。

## Phase 4：評估與人工品質門檻

人工標註是獨立驗收條件，開發者不能把自動分数轉成「人工已確認」標籤。
會提供樣本準備、標註模板、標註合併驗證、開發集閾值擬合與 holdout 報告工具。
公開生成加工塊不等同公司歷史模具；未驗收資料不能啟用正式的無匹配判定。

### 已實作的資料與工具

- `prepare_public_cad --extended`：固定 MFCAD revision、100 個檔案 SHA-256、上游 MIT LICENSE。
  來源為 [MFCAD](https://github.com/hducg/MFCAD)，不需 GPU、LLM 或公司資料。
- 實際資料在 `.runtime/public-cad/mfcad-extended-v1/`，不進 Git 或業務資料庫。
  100 個模型仍保守歸為同一 generated-block 家族、全為 development；
  **尚未滿足多家族獨立 holdout**，不能靠把同源檔案隨機切半來宣稱完成。
- `cad_review template` 建立 25 個 query 的 JSON 人工標註表；等級留 null。
  0=無關、1=弱相關、2=相似、3=高度相似；每對需理由、每 query 需 reviewer。
- `cad_review merge` 驗證 manifest hash、ID、split、標註與理由；未判讀不當成負例。
  只有全部候選明確標 0，才可標 expected_no_match。
- `evaluate_public_cad --policy cpu-surface-verification@2.0 --sample-count 1536`
  產生逐對表面因子、排名、Precision@K、Recall@K、nDCG、判讀覆蓋與 offline cosine coarse recall。
  比對故障留 failures、報告 incomplete 並非零退出，不能從母數中悄悄刪掉。
  `--query-limit` 可先冒煙測試；這不是完整品質報告。
- `cad_review fit` 僅接受 development ≥20 個人工 query、≥30 正例及 ≥30 負例；
  正例為 2/3、負例為 0，1/null 不偷當負例。以誤接受率 ≤5% 選固定表面因子門檻。
- `cad_review validate` 重新核對 development 擬合，要求獨立 holdout ≥10 個 query、
  同樣正負對數門檻、family/hash 不重疊、召回 ≥80%、誤接受 ≤5%、≥3 個完整 no-match query。
  不准用 holdout 重調門檻；失敗不產生可啟用 bundle。
- 管理員另行透過 `SIMILARITY_CALIBRATION_BUNDLE` 指定驗收 bundle 才可 opt-in；
  預設空白，缺失／损壞／不合門檻皆 fail closed。路徑需為 API 可讀的本機／volume 檔案，不能 URL。
  新工作固定 bundle hash、門檻與 dataset 範圍；不變更既有搜尋。
- 無可靠匹配只針對回傳且完整驗證、符合校準 dataset/mode/algorithm 的候選；
  不宣稱搜尋了全資料庫，也不把 size mode 套入 shape mode 門檻。UI 中英文揭露。

### 人工驗收操作（尚待完成）

以下在 `services/platform-api` 執行，使用該目錄 `.venv/Scripts/python.exe manage.py`。
輸出採新增檔案、不覆蓋舊報告；詳參各命令 `--help`。

1. `prepare_public_cad --extended --root ../../.runtime/public-cad/mfcad-extended-v1`。
2. 工程師檢視來源與模型；補充不同家族、保留變體同組，凍結 development/holdout manifest。
3. `cad_review template MANIFEST --root ROOT --count 25 --output review.json`，人工填入分級／理由。
   應納入孔洞／肋不同的 hard negatives；不得由演算法分數產生人工標籤。
4. `cad_review merge MANIFEST --root ROOT --review review.json --output reviewed-manifest.json`。
5. 分別對 development/holdout 執行 `evaluate_public_cad reviewed-manifest.json --root ROOT
   --split development --policy cpu-surface-verification@2.0 --sample-count 1536 --output development.json`。
6. `cad_review fit development.json --output threshold-candidate.json`。
7. `cad_review validate threshold-candidate.json --development development.json --holdout holdout.json
   --reviewer ENGINEER --dataset DATASET_ID --output calibrated-bundle.json`。
8. 人工核准適用範圍後才設定 bundle 路徑、重建 API；否則維持實驗分數與未校準提示。

已實跑：100 份原始 STEP 成功解析，1 個 rigid-transform query 比對 100 候選，
identity Recall@5=1、exact cosine coarse Recall@25=1、精比對 48.23 秒（單 query、離線全候選）。
這不是線上 SLA 或跨模型準確率。人工 query=0、Precision@5=null，未啟用門檻。
已建立 `review-template.json`，25×99 對皆未標註。

## Phase 5：共享快取與效能／外網

保留授權與 checksum 檢查；將數值結果共用快取、候選召回診斷、cold/warm 時間與
驗證完成率納入報告；最後重建既有 Demo 的共用 image、保留資料與私人入口。

### 實作與運維契約

- `SurfaceVerificationCache`（migration 0025）：1024 個固定雜湊槽，7 天 TTL，
  每份 JSON 上限 32 KiB；同槽碰撞只是 cache miss／替換衍生數值，不會取到另一個 key 的值。
  固定槽使並行寫入也不會無限增長；不刪除工程資料、歷史搜尋、稽核或原始檔案。
- key 包含有序 query/candidate 實際 preview SHA、演算法、模式、單位、容差及 B-Rep 比對内容；
  entry 有 payload SHA 並檢查有限數值、狀態／版本／1536 點。只儲存數值證據與固定狀態常數，
  不含 URL、帳號或憑證。損毀、過期、DB 故障一律 miss，回到計算。
- 授權／工程條件篩選仍先執行；快取前仍讀 preview 並驗證 SHA。
  @1.0 的舊工作保留原本 process cache／排序，不使用新 shared cache。
- 新工作固定 `verification_limits`：粗選預設 100（20–200）、精選 20（1–50）、
  cooperative 預算 30 秒（1–60）。可用同名 `.env` 範本中的三個設定調整。
  top_k 只控制顯示結果，不再縮小粗選預算；舊 snapshot 缺欄位保留原預算。
- `diagnostics`：粗選數、符合條件數、computed／unavailable／budget_exceeded、
  process/shared hit、粗選／精比對／總耗時、可得的 queue_wait_seconds；
  前端「搜尋診斷」可展開查看，不把待驗證當高相似度。
- `benchmark_cad_similarity --dataset DATASET_ID --queries 5 --top-k 20 --repeats 3 --output REPORT.json`：
  限 2–1000 個 public_demo 已索引 v2 工件，單次 ≤20 query、≤5 repeats。
  比較同一 dataset/classification 下 Qdrant 與 exact cosine 的 tie-aware top-K overlap。
  這不是人工 relevance Recall；包含 identity，不宣稱全量工程篩選 Recall。
- Benchmark 每次使用獨立 cache namespace；每輪清掉 process cache，保留 shared cache。
  第一輪為 cold，後續必須 shared hit 才計入 warm；報 p50/p95、失敗率、Python traced peak。
  不修改業務紀錄、不寫向量索引；只新增／替換受限衍生 cache row，報告新增不覆蓋。
  Python traced peak 不包含所有 native CAD allocation，不冒充總 RSS。
- 回滾：將 surface verification 開關設為 0，只影響新工作；快取無需刪除。
  migration 0024/0025 皆 additive；舊 STEP 缺結構仍可表面比較，不強制重處理全庫。

### 發布界線

只更新既有 `mold-ai-platform-sites-demo` 內共用 app image 的 API、兩個 Worker、Web、MCP。
沿用現有資料 volumes、登入、Sites 入口及 tunnel。主機上其他既有 Docker 專案不在此次刪除範圍。
發布後檢查 migration、服務與外網資源 SHA；人工工程品質 UAT 和人工逐頁登入 UAT 分開列示。

## 驗證紀錄

各階段完成後補記實際測試與部署結果；不以計畫值宣稱驗收通過。

Phase 3：完整 `scripts/test.ps1` exit 0，後端 347 passed、1 skipped、9 subtests；
Web 173 tests、Sites 15 tests。另驗證新模式在前端送出 comparison_mode/tolerance_mm。
Ruff、TypeScript、migration drift、build 與 Compose 檢查通過。

Phase 4：完整 `scripts/test.ps1` exit 0，後端 354 passed、1 skipped、9 subtests；
Web 173 tests、Sites 15 tests。涵蓋未標註拒絕、獨立 holdout、門檻凍結、no-match、
缺失 bundle、跨 dataset 拒絕套用及逐對比對故障；所有 lint/build/Compose 檢查通過。
品質門檻仍未驗收，正式 bundle 未配置。

Phase 5 程式驗證：完整 `scripts/test.ps1` exit 0，後端 359 passed、1 skipped、9 subtests；
Web 173 tests、Sites 15 tests。另外搜尋診斷／未校準提示雙語 UI 專項 4 passed。
共享快取跨程序記憶體清除、hash 損毀、TTL、碰撞容量、DB 故障降級、不同模式與容差、
來源檢查不能被快取繞過、工作預算固定與公開資料 benchmark 不寫 Job 均通過。
