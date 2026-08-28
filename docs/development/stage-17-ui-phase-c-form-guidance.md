# Stage 17 Phase C — Guided engineering forms

Phase C applies the first two phases of the UI/UX implementation plan to the route-based
Engineering Web. It reduces invalid free-form input and gives users accessible, local guidance
before a request reaches an engineering API. API, evidence, permission and data contracts are
unchanged.

## Phase 1 baseline

- CAD dataset, product type and material inputs use controlled options.
- Similarity dataset, product type and material filters use controlled options.
- Process/Trial location uses a controlled list of supported fixture locations.
- Design Review displays numeric ranges and uses a controlled Demo approver list.
- Knowledge document titles use native required and minimum-length constraints.
- English and Traditional Chinese application copy covers the new options and guidance.

Phase 1 was verified independently and committed before Phase 2 started.

## Phase 2 behavior

`FormField.vue` provides one accessible field contract for labels, required markers, helper text
and errors. It generates a unique input ID and exposes `aria-describedby` and `aria-invalid` values
to the slotted native control. Errors use a live alert and required markers also have screen-reader
text.

The shared component is used by CAD, Similarity, Design Review, Knowledge, Process/Trial, CAE,
HMI, Demo access and Assistant forms. Required-field summaries identify how many inputs remain,
while field errors explain the correction at the point of entry. Numeric controls expose the
supported Demo ranges in both native constraints and helper text.

`WorkspaceEmptyState.vue` provides a consistent explanation and primary next action. Similarity
and Design Review route users to CAD preparation when no query exists. Process/Trial explains the
governed synthetic catalog and can load it directly when no cases exist.

## Safety and scope

- Controlled options reflect the current public/synthetic Demo data contract; they do not create
  new Company master data.
- Browser validation is usability guidance, not a replacement for server-side validation.
- Empty-state actions use existing approved routes and fixture endpoints.
- The implementation does not upload, approve, waive, search or write machine values without the
  user's explicit form action.
- Governed evidence remains in its authored language under the Phase B translation boundary.

## Verification

- Common-component tests cover required, helper, error and action semantics.
- Workspace tests cover CAD preparation CTAs, governed fixture loading and incomplete Knowledge
  upload validation.
- Static translation-key coverage must report zero missing application-owned strings.
- Type checking, all Web unit tests, the production build, repository-wide tests and the running
  Demo smoke/acceptance gates are required before the Phase 2 commit.

## Deferred to Phase 3

Toast notifications, progress spinners, action-copy normalization, navigation icon refinement and
engineering-table readability remain separate Phase 3 work so the form contract can be verified
and reverted independently.
