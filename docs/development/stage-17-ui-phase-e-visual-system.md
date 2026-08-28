# Stage 17 Phase E — Precision-manufacturing visual system

Phase E completes the planned UI/UX Phase 3 visual pass for the Engineering Web. It keeps the
existing route, API, evidence, permission and action contracts intact while making the product
feel like a focused engineering console rather than a collection of raw forms.

## Visual direction

- Deep navy navigation and blue primary actions retain the established Mold AI identity.
- A restrained teal engineering accent identifies trusted status, governed preparation and
  workflow guidance without implying that an engineering result is approved.
- Layered neutral surfaces, compact borders and low-elevation shadows create hierarchy while
  preserving the dense working-surface layout.
- Typography, radii, spacing, focus states and motion are centralized in shared CSS tokens.

## Interface changes

- Navigation initials are replaced by consistent line icons and a stronger active-route state.
- The page header, Assistant, forms, empty states, status bars and workflow containers share one
  surface and border system.
- Two-column engineering forms align fields from the top so labels remain level when only one
  field has helper or validation text.
- Guided Demo cards and result selectors expose clearer hover, selected and focus states.
- Rule, CAE and HMI tables use sticky headers, zebra rows and row highlighting.
- HMI coordinates are collapsed behind friendly `Region A/B/...` labels; exact source coordinates
  remain available as technical evidence.
- Responsive padding and card density are reduced for narrow screens.
- Motion is subtle and disabled automatically when the user prefers reduced motion.

## Accessibility and evidence boundary

- Functional icons are decorative and route labels remain the accessible navigation name.
- Color is never the only status signal; existing text labels, roles and evidence remain present.
- Focus rings and native control semantics are preserved.
- Visual emphasis does not alter deterministic scores, findings, confidence, lineage or approval
  state.

## Verification

- HMI coverage verifies the friendly region labels while retaining source-region records.
- Static translation-key coverage must remain complete.
- Type checking, all Web tests, production build, Docker smoke and repository acceptance are
  required before the phase is released.
