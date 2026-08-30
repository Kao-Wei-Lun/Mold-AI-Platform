# Stage 27 — Phase 4A Structured Domain Imports

## Delivery sequence

| Adapter | Formats | Status |
|---|---|---|
| Engineering Reference Data | CSV, XLSX, JSON | Complete |
| Project / Part / Mold / Revision Registry | CSV, XLSX | Complete |
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

## Project / Part / Mold / Revision Registry adapter

The `registry` adapter treats every source row as a governed hierarchy ending in one mold revision. Project and mold identity are mandatory; part identity is optional. Existing nodes are preserved and a replay reports the revision as skipped instead of creating duplicates.

- CSV and XLSX use the same canonical hierarchy fields and versioned template.
- Dry Run checks required hierarchy fields, duplicate revision identities, positive cavity count, and active Mold Type, Product Type, and Material references.
- No Project, Part, Mold, or Revision is written before Commit.
- Atomic Commit creates the hierarchy in dependency order and returns a row-level `mold_revision` result.
- Reconciliation balances source rows against created or existing revision outcomes.
