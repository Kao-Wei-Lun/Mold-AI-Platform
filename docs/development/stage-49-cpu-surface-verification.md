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
