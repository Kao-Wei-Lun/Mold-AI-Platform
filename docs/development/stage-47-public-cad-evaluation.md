# Stage 47：公開 CAD 評估與幾何重排

## 已交付

- [詳細修改規劃](../planning/public-cad-similarity-evaluation-plan.md)，先提交再修改系統。
- 離線 corpus manifest 驗證、SHA-256、路徑/檔案大小限制、family/checksum split 洩漏檢查。
- controlled identity 與 human geometry 分開評估，Recall@K、MRR、provisional nDCG、
  judged coverage、完整標記 no-match 的 false acceptance、離線排名時間。
- 12 個公開 MFCAD STEP 的固定來源清單與安全下載指令（總 STEP 約 0.81 MB）。
- `block-distance@1.0`：CPU 分項幾何重排；不改 32D 特徵與 Qdrant index。
- API/Worker 使用輸入快照固定評分政策；保留歷史無快照工作的舊版政策。
- STL 三角形數不當工程拓樸；STEP/STP 可比。前端提供中英分項說明、回退提示與驗證警語。

## 一次性準備公開樣本

在 PowerShell 中：

```powershell
cd C:\project\Mold-AI-Platform\services\platform-api
.\.venv\Scripts\python.exe manage.py prepare_public_cad --root ../../.runtime/public-cad/mfcad-smoke-v1
```

只從 `raw.githubusercontent.com/hducg/MFCAD/<固定提交>/` 下載清單中檔案與 LICENSE。
每檔最多 2 MiB、30 秒 network timeout、不跟隨 redirect；校驗通過後才建立檔案。
既有檔案 checksum 一致可重跑；不一致直接失敗，不覆寫使用者修改。
根目錄保留 `LICENSE.MFCAD.txt`；任何未來允許的再散布亦須保留上游聲明。
這不是 CAD UI 自動匯入，不寫入 PostgreSQL、Qdrant，也不將來源放入對外 Demo。

## 執行新舊評分比較

```powershell
.\.venv\Scripts\python.exe manage.py evaluate_public_cad ../../.runtime/public-cad/mfcad-smoke-v1/manifest.json --root ../../.runtime/public-cad/mfcad-smoke-v1 --split development --policy cosine-v2 --output ../../.runtime/public-cad/mfcad-smoke-v1/cosine-report.json
.\.venv\Scripts\python.exe manage.py evaluate_public_cad ../../.runtime/public-cad/mfcad-smoke-v1/manifest.json --root ../../.runtime/public-cad/mfcad-smoke-v1 --split development --policy block-distance@1.0 --output ../../.runtime/public-cad/mfcad-smoke-v1/block-report.json
```

`--output` 只建立新報表；重跑請使用新檔名，或省略參數輸出至終端。
預設 sample_count=1024、seed=20260907、top_k=5。可調整到 128–4096 點與 1–50 筆結果。
線上 descriptor 預設為 4096 點；若要量測相同取樣預算，指定 `--sample-count 4096`。
STEP 解析在 subprocess 執行，沿用 240 秒上限；每檔最多 200 MiB，preview 最多一百萬面。
本工具不是不受信任 CAD 的完整 OS 沙箱；只對已確認來源的離線資料使用。
解析失敗：輸出 failures、標記 incomplete、非零退出，不從分母偷偷刪除失敗案例。

## 2026-09-07 本機實測

上游 revision：`ef6d58a40164d5192666821ce98d0cc90e379fac`。
Corpus canonical manifest SHA-256：
`dcef564cdaf787ddbc1107538d85756f813a99546407247ae716011e780ece2a`。

| 指標 | cosine-v2 | block-distance@1.0 |
| --- | --- | --- |
| 公開 STEP 解析成功 | 12/12 | 12/12 |
| 旋轉＋平移後找回原件的 query | 12/12 | 12/12 |
| Controlled Recall@5 / MRR | 1.0 / 1.0 | 1.0 / 1.0 |
| Judged coverage@5 | 0.20 | 0.20 |
| 離線 ranking p50 | 約 0.44 ms | 約 1.09 ms |
| 離線 ranking p95 | 約 0.69 ms | 約 1.41 ms |
| 全部解析＋兩次描述子總時間 | 約 19.0 s | 約 18.8 s |
| 人工跨模型 query | 0 | 0 |
| 搜尋品質 gate | not_evaluated | not_evaluated |

這裡的時間只適用本機 12 候選、1024 點離線評分，不包含 Qdrant/HTTP/Worker 排隊，
也不是效能 SLA。原件之外的候選未判讀，所以 coverage 為 1/5，不能宣稱 Precision@5=100%。
兩個演算法都能找回自己，不能由此宣稱新演算法的跨模型排名更準。
MFCAD 為公開加工特徵模型，不是公司歷史模具，不能驗證製程沿用。

合成幾何反例另在 `test_cad_shape_scoring.py` 防止既有錯誤：cube/cylinder cosine 約 .993
而 block 約 .617；cube/plate 約 .872→.396。新分數仍未校準，不能解讀為相似機率。

## 如何擴充成真正的跨模型評估

1. 另外建立 corpus 目錄與 manifest，不修改已凍結的下載樣本。
2. 收錄授權可用的不同幾何家族；每個 model 保留 URL、checksum、family、split、unit。
3. 將同來源/變形/版本/相關家族放在同一 split；不要把副本當獨立的 holdout。
4. `human_geometry` query 必須有 reviewer、reason 與人工 grades：0 不相關、1 弱相關、
   2 相似、3 高度相似。unknown 省略，不用 0 代替。
5. query 本身從 human 候選池排除；其他正例必須是同 split 的另一個 model_id。
6. no-match query 必須設 `expected_no_match=true`，同 split 所有其他候選均被人工標 0。
   只有同時傳入 `--threshold` 才計算 false acceptance；不要在 holdout 上調整 threshold。
7. `quality_gate` 不會自動轉 PASS；需要獨立 reviewer 核准及較完整的召回/拒答驗收。

人工 query 的 JSON 範例（示意，不是已完成的判讀）：

```json
{
  "id": "human-query-001",
  "model_id": "housing-query",
  "split": "holdout",
  "kind": "human_geometry",
  "reviewer": "填入實際判讀者",
  "reason": "記錄相似與不同的結構依據",
  "judgments": {"housing-reference": 3, "flat-plate": 0}
}
```

## 操作與回退

新建搜尋使用 `SIMILARITY_GEOMETRY_POLICY=block-distance@1.0`。回退可在部署 env 設為
`cosine-v2`，重建/重啟 api 與 workers 的環境；不刪除特徵、不重建索引。
既有搜尋結果是歷史紀錄，不會因程式更新自動重算；使用者需重新送出搜尋才能測新版。
原始檔/完整報表在 `.runtime`，Git 只存版本化腳本、lock、測試與本結果摘要。

初次程式交付未部署；使用者後續要求外網 Demo 後，已於 2026-09-07 完成既有
`mold-ai-platform-sites-demo` 部署更新。只重建共用 app image，更新 api、worker、
worker-cad、web 與 mcp-gateway；保留 DB、Redis、Qdrant、volume 及原有 tunnel。
Sites 私人入口程式未變更，因此不重新發布入口。不建立新 Docker 專案，不刪除其他專案。

部署後驗證：
- 外網首頁 HTTP 200，實際取得 `/assets/index-BTG9t_rI.js`，含新版幾何說明及驗證警語。
- 本機帳號登入模式與既有管理者仍就緒；未登入存取受保護 API 回傳 HTTP 401。
- API/DB/Redis/Qdrant/MCP healthy；兩個 workers 回應正常，沒有 stale jobs。
- 執行中 API 的 read route 為 v2，實際幾何比較為 `block-distance@1.0`，包含 7 個分項。
- Core Demo、Sites entry、Web tunnel、MCP deep link 均 ready。Assistant 的 deterministic
  fallback 仍是既有可選限制，不影響 CAD 相似搜尋，也未呼叫付費 LLM。
- 未更動使用者資料；公開 MFCAD 評估原件仍留在離線 corpus，未自動匯入線上資料庫。

使用者可沿用原有 Sites 私人入口或既有 HTTPS tunnel，登入原本帳號。
若保留舊頁籤請強制重新整理；重新送出搜尋才使用新評分，歷史結果不會被覆寫。

## 回歸驗證

`scripts/test.ps1`：後端 lint/format、Django check、migration drift、pytest、Web typecheck/
Vitest/build、Sites lint/Vitest/build、各 Compose 配置與共用 app image 檢查。
最終後端 330 passed、9 subtests passed、1 skipped（OpenAI live test，未產生 LLM API 費用）；
Web 163 tests、Sites 15 tests。前端較大 bundle 的警告仍存在，沒有隱藏或放寬門檻。

## 尚未完成的品質驗收

- 100–200 個多家族樣本與 20–30 個人工 query；本輪是 12 個公開冒煙樣本，不是該規模。
- ABC 模型個別授權確認與匯入；本輪未下載或再散布 ABC。
- 真實跨模型 Recall@5、誤判高分率、no-match 閾值校準。
- Qdrant 粗選候選召回率、CPU 自動雙向對位重排、工程製程適用性。

這些是明確保留的後續工作，不能以程式回歸通過代替。
