# Stage 15 — Curated CAD Demo Corpus and Golden Scenarios

- 狀態：Planned
- 優先級：P0
- 前置：Stage 2–4 CAD/Similarity/Review contracts
- 出口：全新環境可重複 seed 一套獨立、治理、可預測的 CAD Demo corpus

## 1. 問題定義

目前 CAD upload、parsing、index、Similarity 與 Design Review 均已實作，但 running demo主要由使用者
上傳與 smoke artifacts累積資料。這不足以保證每次展示都有：

- 明確的 query與候選。
- 穩定的第一名與可解釋差異。
- PASS、FAIL、NOT_EVALUATED review scenarios。
- 合法 provenance與可重現 generator/version。
- 不受過去 smoke run污染的乾淨結果。

Stage 15建立 `curated-cad-demo-v1`，使 Demo不依賴歷史 volume或臨時上傳。

## 2. Dataset scope

最低 corpus：

| Group | 建議數量 | 用途 |
|---|---:|---|
| Query molds | 2 | 主展示與替代 scenario |
| Strong similar | 4 | Top ranking與微小尺寸/拓撲差異 |
| Usable similar | 4 | 中等差異、可用參考案例 |
| Negative controls | 4 | 不同形狀/比例/拓撲，驗證 ranking |
| Rule boundary fixtures | 4–8 | PASS/FAIL/boundary/NOT_EVALUATED |
| Invalid/error fixtures | 2–4 | corrupted、open shell、unit uncertainty等安全示範 |

最小正常 corpus 建議 14–22 個 CAD artifacts；錯誤 fixtures 不進一般 Similarity candidate pool。
資料量用於流程與解釋性，不宣稱統計模型準確率。

## 3. Dataset separation

| Dataset ID | 用途 | User-visible |
|---|---|---:|
| `curated-cad-demo-v1` | 正式 Demo corpus | 是 |
| `automated-cad-smoke-v1` | 每次 smoke產生的暫時 artifacts | 否 |
| `manual-cad-upload-v1` | Demo使用者臨時上傳 | 是，但與 curated標示分開 |

- **CAD-DATA-001**：所有 CAD Artifact 必須有 dataset ID；沒有值不得進 curated index。
- **CAD-DATA-002**：預設 Demo catalog與 MCP只列出 curated/manual user-visible datasets。
- **CAD-DATA-003**：Automated smoke query/candidates不得影響 curated expected ranking。
- **CAD-DATA-004**：Reset可清除 manual/smoke operation data，但 curated source與manifest可重建。

## 4. Source and licensing policy

優先使用參數化 synthetic geometry，理由：

- 可保存 generator/version/parameters與measurement truth。
- 沒有公司資料與第三方授權不確定性。
- 可精準建立尺寸、aspect ratio、hole/boss/rib等差異。
- 可在 CI重建或用checksum驗證。

若加入 public CAD：

- 保存 dataset名稱、source URL、license、download date、original ID、是否允許再散布。
- 未確認 license不得commit binary；只能保存取得說明與hash。
- Public CAD與synthetic CAD在UI中分開標示。
- 不把公共 shape dataset的指標宣稱為公司模具 similarity準確率。

## 5. Corpus manifest contract

建議位置：

```text
fixtures/cad/curated-demo-v1/
├─ manifest.json
├─ sources/
├─ expected/
│  ├─ similarity.json
│  └─ design-review.json
└─ README.md
```

Manifest 1.0範例：

```json
{
  "schema_version": "1.0",
  "dataset_id": "curated-cad-demo-v1",
  "dataset_version": "2026.09.1",
  "generator": {
    "name": "mold-demo-fixture-generator",
    "version": "1.0.0"
  },
  "license": "project-generated-synthetic-demo",
  "items": [
    {
      "fixture_id": "housing-query-a",
      "filename": "housing-query-a.step",
      "sha256": "hex",
      "format": "step",
      "role": "query",
      "product_type": "connector_housing",
      "material_code": "PA6-GF30",
      "generator_parameters": {},
      "expected_geometry": {
        "unit": "mm",
        "bbox": [0, 0, 0, 80, 50, 25],
        "tolerances": {}
      },
      "expected_flags": []
    }
  ]
}
```

要求：

- **CAD-DATA-010**：Manifest與每個source file均有checksum。
- **CAD-DATA-011**：Seed前驗證schema、duplicate ID/filename/hash與file signature。
- **CAD-DATA-012**：Generator parameter與expected geometry使用canonical units。
- **CAD-DATA-013**：更新任何source/expected label必須增加dataset version，不覆寫歷史evidence。
- **CAD-DATA-014**：Seed result保存manifest hash、dataset version、parser/feature/index versions。

## 6. Golden similarity scenarios

至少定義兩個scenario：

### Scenario SIM-A — Connector housing

- Query：`housing-query-a`。
- Rank 1–2：尺寸相近、拓撲相近、material/product相同。
- Rank 3–5：geometry usable但material或局部feature不同。
- Negative：aspect ratio、volume或surface distribution明顯不同。
- Required explanation：Overall、Dimension、Geometry、Topology、Metadata、主要差異與limitations。

### Scenario SIM-B — Alternate query

- 不重用SIM-A第一名，避免ranking只為單一query調整。
- 包含missing metadata與unit uncertainty lane，驗證weight renormalization。
- 至少一個candidate因dataset filter被排除。

Expected label：

```json
{
  "query_fixture_id": "housing-query-a",
  "profile": "demo-general-similarity@1.0",
  "expected_top_group": ["housing-a-r2", "housing-a-r1"],
  "required_top_k_hits": 2,
  "negative_fixture_ids": ["plate-control-a"],
  "invariants": {
    "query_excluded": true,
    "score_order_deterministic": true,
    "explanation_matches_profile": true
  }
}
```

Golden set不是把exact浮點score永久寫死。除非profile與feature version固定，驗收以ranking group、必要
candidate、negative exclusion與explanation invariants為主；若需要exact score，必須連同版本snapshot。

## 7. Design Review scenarios

每類重要rule至少有：

- positive/PASS。
- negative/FAIL。
- boundary。
- not applicable或NOT_EVALUATED。

目前face-level rib/draft尚未由kernel自動量測，因此：

- Global geometry rules使用fixture truth自動驗證。
- Rib/draft使用明確`USER_SUPPLIED_DEMO_MEASUREMENT` scenario。
- UI與UAT不得把user-supplied measurement描述為CAD自動辨識。
- 未提供值時必須NOT_EVALUATED。

Expected review contract保存profile version、rule ID、expected state、evidence scope與tolerance。

## 8. Seed and reconciliation

新增管理命令：

```powershell
python manage.py seed_cad_demo
python manage.py seed_cad_demo --verify-only
```

行為：

1. 讀取並驗證manifest。
2. 依fixture ID與source hash判斷idempotent replay。
3. 建立Artifact/ArtifactVersion/CAD processing Job。
4. 透過正式CAD queue或明確synchronous seed mode處理。
5. 驗證parsed geometry與expected tolerance。
6. 建立FeatureSet並寫入Qdrant scoped index。
7. 等待或輪詢所有Job terminal state。
8. 執行Golden similarity與Review invariants。
9. 輸出created/existing/indexed/failed/reconciled counts。

Seed失敗必須non-zero exit；不得只印warning後讓Demo啟動宣稱ready。

`seed_demo_data`整合CAD seed後，Demo Status至少回傳：

```json
{
  "curated_cad": {
    "dataset_id": "curated-cad-demo-v1",
    "dataset_version": "2026.09.1",
    "expected": 18,
    "processed": 18,
    "indexed": 18,
    "reconciliation": "passed"
  }
}
```

## 9. Web behavior

- Dashboard顯示Curated CAD dataset version與ready count。
- CAD workspace提供「使用Curated Query」按鈕，但不默默預選。
- Catalog明確標示Curated、Manual Upload、Synthetic、Public、Automated Smoke。
- Golden scenario可用Guided Demo模式載入，仍顯示實際Job與結果，不使用前端hard-coded結果。
- 使用者可上傳自己的STEP/STL，但不改變curated expected ranking gate。
- Reset後Guided Demo仍可立即使用。

## 10. Test plan

### 10.1 Manifest and files

- JSON schema、duplicate、checksum、signature、missing file、unexpected file。
- Synthetic source可重建或checksum一致。
- License/provenance required fields。
- 路徑traversal與oversized file拒絕。

### 10.2 Seed

- Fresh seed、second idempotent seed、partial previous seed、failed CAD parse。
- DB成功/Qdrant失敗、retry後reconciliation。
- Automated smoke隔離。
- Dataset version upgrade建立新version，不覆寫old evidence。

### 10.3 Geometry and Review

- bbox/volume/area/count在tolerance內。
- PASS/FAIL/boundary/NOT_EVALUATED fixtures。
- Parser error不產生假PASS。
- User-supplied measurement provenance完整。

### 10.4 Similarity

- SIM-A/SIM-B top group invariants。
- Query self exclusion、dataset/material/product filters。
- Missing lane renormalization、unit uncertainty。
- Explanation與profile/feature/index version一致。

### 10.5 Running-stack UAT

- 全新volume seed。
- Web選取curated query→search→comparison→review。
- ChatGPT用已知artifact version啟動search並poll job。
- Stage 13 deep link回到相同result。

## 11. Acceptance criteria

- **ACC-CAD-DATA-001**：全新volume一次seed成功，第二次created=0且reconciliation passed。
- **ACC-CAD-DATA-002**：Curated正常artifacts全部processed/indexed；error fixtures維持expected typed failure。
- **ACC-CAD-DATA-003**：SIM-A與SIM-B Golden invariants連續三次一致。
- **ACC-CAD-DATA-004**：Review PASS/FAIL/NOT_EVALUATED/evidence與expected contract 100%一致。
- **ACC-CAD-DATA-005**：Smoke artifacts不出現在curated catalog與Golden candidates。
- **ACC-CAD-DATA-006**：每筆資料具有dataset/source/license-or-generator/hash/version/lineage。
- **ACC-CAD-DATA-007**：Web與ChatGPT完成同一search並取得相同persisted domain result。

## 12. Non-goals

- 不建立1K–10K public corpus作為v1.0 blocker。
- 不訓練learned embedding。
- 不宣稱工程師標註的公司relevance。
- 不實作native CAD vault或assembly reference resolution。
- 不假裝face-level rib/draft已自動量測。

## 13. Suggested implementation commits

```text
feat(fixtures): add governed CAD demo manifest and generator
feat(cad): add idempotent curated dataset seeding
test(cad): add golden similarity and review scenarios
feat(web): add explicit curated CAD guided flow
docs: add corpus provenance and operator guide
```
