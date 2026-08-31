# Stage 32 - Applicability editing experience

## Outcome

The Mold Rules workspace now explains applicability in engineering language and gives authorized
rule authors a visible way to edit it without weakening version governance.

The Traditional Chinese label is **適用範圍與選用條件**. It answers two questions:

1. Which mold, product, material, molding process, or location can use this rule set?
2. Does a matching condition include the rule set as a candidate or exclude it from selection?

## Safe editing flow

Published, approved, in-review, validated, and retired versions remain immutable. Their condition
controls are disabled and the page identifies the version as read-only. A user with
`rules:author` can select **Create editable draft**, confirm the proposed next version and change
summary, and create a clone of the selected version. The UI then selects the new draft and keeps
the user on the applicability tab.

Only a draft exposes Add, Remove, and editable Condition type, Condition value, and Selection
behavior controls. Changes do not affect rule resolution until the author saves the draft and it
passes the existing validation, review, approval, and publication lifecycle.

## User-interface requirements

- Explain Include and Exclude before showing the rows.
- Show an explicit `Editable draft` or `Read-only version` state.
- Disable all row controls outside an authorized draft.
- Provide a direct clone-to-draft action beside the read-only explanation.
- Suggest the next unused numeric minor version while allowing the author to change it.
- Keep every control labelled and align fields at the bottom of each row.
- Collapse the draft form and condition rows for tablet and mobile widths.
- Preserve optimistic locking, audit reason, source profile ID, and version lineage.

## Contract and audit behavior

The UI uses the existing `POST /api/v1/rule-profiles` contract with `action=clone`,
`source_profile_id`, `version`, `change_summary`, and `reason`. No new endpoint or in-place update
path is introduced. The resulting draft retains the source version's rules and applicability and
receives its own profile ID, row version, checksum, and audit events.

## Verification

- Component coverage verifies the published controls are disabled.
- Component coverage verifies an authorized author can open the inline clone form.
- The clone request must contain the selected source profile ID and proposed version.
- After creation, the cloned draft must be selected, editable, and expose Save draft.
- The complete Engineering Web test, type-check, and production build gates must pass.
- External Demo smoke checks and the single-image Docker invariant must pass before release.
