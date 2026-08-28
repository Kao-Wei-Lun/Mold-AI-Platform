# Stage 17 Phase B — English / Traditional Chinese UI

Phase B adds an application-wide language preference to the Engineering Web without changing API,
engineering evidence, permission or data contracts.

## Behaviour

- The top context bar exposes an `EN / 中文` segmented control on every route.
- The initial locale uses the saved browser preference; otherwise a `zh*` browser locale selects
  Traditional Chinese and all other locales select English.
- The preference is stored only in browser `localStorage` under `mold-ai.locale`.
- Switching language updates `<html lang>`, the document title, navigation, forms, empty/error
  states, accessibility labels and Assistant `ui_locale` immediately without a reload.
- The preference contains no credentials, Artifact IDs, Job IDs or engineering data.

## Translation boundary

Application-owned labels and deterministic fallback messages are translated. Governed source
records returned by the API remain in their authored language unless the data contract supplies an
approved localized field. This applies to rule text, engineering evidence, case descriptions,
citations, limitations and model/provider output. The UI must not present an unofficial translation
as original engineering evidence.

English is the key and fallback language. An unknown source string is rendered unchanged instead
of being dropped or replaced with invented text. The current implementation is dependency-free and
centralizes Traditional Chinese copy in `apps/web/src/i18n.ts`.

## Verification

- Unit coverage verifies interpolation, unknown-source fallback, persistence and `<html lang>`.
- App coverage verifies switching the live shell in both directions.
- Assistant coverage verifies that the active UI locale is sent to the backend.
- Existing workspace tests continue to use English by setting the locale explicitly where needed.
- Production build, Docker route smoke and the repository Demo acceptance gate remain required
  before the phase commit.

## Follow-up

- Add governed localized data fields when Company rules and source documents require bilingual
  publication.
- Add locale-aware number/date formatting after the Canonical Data Contract defines display rules.
- Include both locales in the future keyboard, zoom and visual-regression matrix.
