# Stage 27 — Phase 4A Structured Domain Imports

## Delivery sequence

| Adapter | Formats | Status |
|---|---|---|
| Engineering Reference Data | CSV, XLSX, JSON | Complete |
| Project / Part / Mold / Revision Registry | CSV, XLSX | In progress |
| Mold Rule Profiles | CSV, XLSX, JSON | Planned |
| Trial / Process | CSV, XLSX, JSON | Planned |

Each adapter uses the Phase 3 source artifact, mapping, Dry Run, atomic commit, record result, audit, lineage identity, and reconciliation contracts. Domain adapters do not introduce alternate upload or commit paths.

## Engineering Reference Data adapter

The `master_data` adapter supports all governed reference kinds, including Mold Type, Molding Process, Rule Category, Dataset, Product Type, Material, Machine, Defect, Location, and Unit.

- CSV, XLSX, and JSON normalize to the same canonical record shape.
- The versioned CSV template is available from `/api/v1/import-templates/master_data`.
- Required fields are `kind`, `code`, and `name_en`; `name_zh_tw` is optional and falls back to the English name during commit.
- Kind values must exist in the governed `MasterDataItem.Kind` registry.
- Duplicate identities within one batch and records already present in the target scope are reported during Dry Run.
- Dry Run creates no `MasterDataItem` rows.
- Commit creates immutable canonical codes and records row outcomes plus reconciliation evidence.

Automated adapter tests cover all three formats, versioned template download, invalid canonical kinds, row-level blocking issues, and zero domain writes before commit.
