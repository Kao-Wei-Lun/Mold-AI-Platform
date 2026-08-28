# Stage 17 Phase D — Engineering action feedback

Phase D implements the interaction-feedback portion of UI/UX Phase 3 without changing any
engineering API or data contract.

## Behavior

- A global, bounded notification region presents success and error feedback for user-triggered
  CAD, Similarity, Design Review, Knowledge, Process/Trial, CAE and HMI operations.
- Notifications are keyboard-dismissible, use `status` for successful operations and `alert` for
  errors, and disappear automatically after a short delay.
- At most four notifications are retained so repeated actions cannot cover the engineering
  workspace.
- Busy action buttons expose `aria-busy`, a consistent spinner and their existing descriptive
  progress copy.
- Technical action labels such as `Reload idempotently` are replaced with plain product language;
  backend idempotency behavior is unchanged.

## Safety boundary

Notifications report the result already returned by the current action. They do not infer an
engineering outcome, trigger a second API request, approve a finding, apply machine parameters or
replace the existing inline evidence and error states.

## Verification

- Notification tests cover status/error semantics and explicit dismissal.
- Existing workspace tests continue to verify request bodies, guarded actions and deterministic
  evidence.
- Type checking, all Web tests, the production build and repository-wide acceptance remain gates
  before release.
