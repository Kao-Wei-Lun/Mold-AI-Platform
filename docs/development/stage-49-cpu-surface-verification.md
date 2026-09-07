# Stage 49：CPU 雙向表面驗證

規劃：[CPU 幾何驗證開發文件](../planning/cpu-geometric-verification-plan.md)。

## 階段 1：獨立核心（2026-09-07）

- 新增 `cad_surface_verification.py`，不改既有向量與手動偏差工具。
- 固定面積取樣、RMS radius 正規化、24 個 proper rotation 初始姿態、
  3 個候選姿態的雙向 correspondence ICP；每姿態最多 30 次迭代。
- 所有評估點皆計入雙向 mean、P95、覆蓋率、F-score；保留最佳雙向平均距離解。
- 使用保守、尚未人工校準的 score factor；normalized transform 不送入原始座標 viewer。
- 支援開放網格，不宣稱 signed surface distance；面數、點數、finite、面積與期限檢查。
- Python deadline 為 cooperative，不是可中斷所有 C extension 的 sandbox。

測試：`test_cad_surface_verification.py`、`test_cad_shape_scoring.py`、
`test_cad_registration.py` 共 **22 passed**，11.46 秒（包含測試環境開銷，非 SLA）。
新增 7 個控制：剛體／尺度、兩個負例、subset 雙向、remesh、非法輸入／deadline、開放網格。
Ruff lint/format 通過。這是合成回歸，不是人工跨模具品質驗收。

階段 1 不改線上搜尋；階段 2 才接工作快照、API 契約及 UI。

## 階段 2：搜尋整合與介面

- 新建 v2 搜尋固定 `surface_verification_policy=cpu-surface-verification@1.0`。
  Worker 不讀當下開關決定歷史工作政策；舊 snapshot 缺欄位仍用舊排序。
- 預設啟用，`SIMILARITY_SURFACE_VERIFICATION_ENABLED=0` 可使之後的新搜尋回到
  基準排序；API、general Worker、CAD Worker 都由 Compose 傳入同一開關。
- 先經既有候選／classification／工程篩選後才讀預覽。
- 每次最多驗證基準排序前 10 個候選，cooperative 時間預算 30 秒，
  每份 preview 上限 64 MiB、mesh 上限一百萬面；保留既有 Celery 270/300 秒限制。
- 讀取 bytes 核對 ArtifactVersion SHA-256；查詢取樣只做一次。
  process-local 點雲與成對結果各最多 64 筆，key 含實際內容 SHA 與固定演算法版本。
  仍先讀取／檢查來源，再使用快取；沒有將使用者權限或 URL 放入快取。
- 新增 `baseline_overall_score`、`ranking_basis`、`geometric_verification`。
  `computed` 的 overall 為基準分乘不大於 1 的 score factor；不是增加一個能拉高分的 lane。
- 未能計算／超預算為 `reference_only`，API 為向後相容保留原基準 overall 數字，
  但 `score_policy=reference-only-unverified`，且排序放在 computed 後；
  Web 不顯示該數字為最終分數，改顯示「僅供參考」。API limitations 同樣明示這個語意。
- 前端中英文顯示雙向覆蓋、F-score、mean/P95、容差、調整前基準分與實驗警語。
  原 geometry／engineering breakdown 明確標成調整前基準證據。
- 既有手動 3D deviation／ROI 不改座標與演算法，避免把 normalized transform
  誤用在原始 CAD；使用者仍可另做手動比對，兩種數值不應混稱毫米公差。

### 階段 2 專項驗證

- API／重排 13 passed：真實取樣負例重排、快取、preview checksum、大小限制、
  缺 preview 分級、deadline、候選預算、提交時設定固定、歷史工作不改政策。
- 前端與 preview race 共 15 passed；typecheck 通過。
  computed／unavailable 的中英文分別驗證；未驗證不顯示假距離或高分。
- `scripts/test.ps1` exit 0：後端 **342 passed、1 skipped、9 subtests passed**，
  Web **39 files / 173 tests**，Sites **15 tests**；lint、format、typecheck、migration drift、
  production builds、Compose 共用 app image 與 PowerShell 語法檢查皆通過。
- skipped 為可選付費 OpenAI live 測試；本輪未呼叫 LLM API。
- 已存在的前端 >600 kB bundle 與 vinext route classification 警告仍保留，未放寬檢查。
- 1536 點的合成數值檢查：4×2×1 box 自比 factor=1；對 radius=1/height=4 cylinder
  factor=0.09080208、雙向覆蓋=0.28125/0.30403646。兩組計算共約 0.611 秒，
  不含 I/O、queue 或向量召回，亦非真實 CAD 品質證明或外網 SLA。
- 外網發布狀態在部署後另補記。

## 尚未交付與限制

- Phase 3 多尺度局部特徵／STEP 結構、工程尺寸模式尚未實作。
- Phase 4 人工標註 corpus、正式 precision／no-match 門檻尚未校準。
- Phase 5 跨 Worker 持久快取、全量召回與真實 cold/warm latency benchmark 尚未完成。
- 雙向 Chamfer 型平均與 sampled P95 仍可能忽略非常小但工程上重要的孔／肋差異；
  不是精確曲面距離、製程沿用建議或全域最佳對位保證。
- 未經人工品質驗收，不能宣稱改善實際模具查詢準確率若干百分比。
