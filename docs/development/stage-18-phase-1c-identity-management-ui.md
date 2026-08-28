# Stage 18 Phase 1C — Identity Management Workspace

Status: implemented on 2026-08-28  
Scope: controlled local Demo identity only

## Outcome

Phase 1C adds an authenticated Engineering Web workspace at `/governance/identity` for the
day-to-day administration of individual Demo accounts. It uses the Phase 1A server-side identity
policy and the Phase 1B session/CSRF client. The browser is an administration surface, not the
authorization authority: every mutation remains permission-checked, validated, and audited by the
Platform API.

This phase does not replace the owner-only access boundary of the separately hosted Sites console.
Sites continues to rely on the platform hosting boundary. The Engineering Web local session is used
only after a user reaches the application and must not be copied into or simulated by Sites.

## User workflow

An account with `identity:manage` sees **Governance → Accounts & access**. The workspace provides:

- account totals for active, platform administrator, and attention-required states;
- search by name, username, email, role, or scope, plus status filtering;
- creation of an individual account with an initial password, role, data scope, and audit reason;
- profile updates for display name, email, locale, and timezone using `row_version` optimistic
  concurrency control;
- explicit role-to-scope assignments and governed role revocation;
- account activation, suspension, disabling, and active-session revocation;
- confirmation for destructive access actions and a mandatory audit reason;
- English and Traditional Chinese presentation and responsive table/detail layouts.

The navigation item is hidden from users without `identity:manage`. Direct routing is also handled:
the workspace initially denies access while the browser restores its session, then loads governed
data automatically if the restored account is authorized. The API remains the definitive guard, so
changing the URL or calling an endpoint directly cannot grant access.

## API contract used by the workspace

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/admin/users` | List governed local accounts |
| `POST` | `/api/v1/admin/users` | Create an account and its initial assignment |
| `GET` | `/api/v1/admin/users/{account_id}` | Read the latest account detail |
| `PATCH` | `/api/v1/admin/users/{account_id}` | Update profile fields with `row_version` |
| `POST` | `/api/v1/admin/users/{account_id}/{action}` | Activate, suspend, disable, or revoke sessions |
| `GET` | `/api/v1/admin/identity-catalog` | Read active roles, permissions, and data scopes |
| `POST` | `/api/v1/admin/role-assignments` | Assign an active role in an explicit scope |
| `DELETE` | `/api/v1/admin/role-assignments/{assignment_id}` | Revoke an assignment with a reason |

Account responses now include active `role_assignments` with stable assignment IDs and role/scope
codes and names. This allows the UI to revoke a specific assignment without deriving identity from
labels or array positions.

All mutating browser requests use the session cookie plus the current CSRF token. Passwords are sent
only to the account-creation endpoint over the configured transport and are never persisted in
browser storage. Error messages use the server response envelope where available.

## Safety controls

- `identity:manage` is required by the Platform API for every administration endpoint.
- The UI does not show suspend or disable actions for the current administrator.
- The UI does not show revocation for the current administrator's own `platform_admin` assignment.
- The backend independently rejects self-revocation of `platform_admin`, even if the UI is bypassed.
- State and role mutations require a non-empty reason and emit immutable identity Audit events.
- Suspension and disabling revoke existing sessions; session revocation is also available directly.
- Account deletion is intentionally absent. Historical actors and audit references are preserved.
- Concurrent profile edits return `409` instead of silently overwriting a newer change.

## Tests and acceptance evidence

Automated tests cover:

- permission-denied rendering for a non-administrator;
- account and identity-catalog loading;
- late session restoration on a direct identity route;
- self-lockout action suppression;
- account creation, CSRF propagation, role/scope, and required audit reason;
- reason and confirmation requirements for suspension;
- app-shell navigation visibility and direct-route integration;
- server-side allow/deny policy, account creation/update/disable, role assignment/revocation,
  optimistic locking, session invalidation, and Audit events;
- schema migration drift, lint, type checking, frontend build, and the repository-wide regression
  suite through `scripts/test.ps1`.

## Known limits and next work

This is the minimum Demo administration workspace, not Enterprise IAM completion. The following stay
outside this phase:

- password change/reset and first-login password-change workflow;
- account invitation, expiry, sponsor, MFA, break-glass, and recovery workflows;
- active-session inventory by device rather than aggregate revocation;
- detailed per-account Audit timeline and access-review campaign UI;
- custom role authoring, policy simulation, approval workflow, and segregation-of-duties engine;
- OIDC/SAML federation, SCIM provisioning, group mapping, external identity reconciliation, and
  service-account lifecycle.

Phase 2 implements governed master-data models, APIs, and UI. It will reuse these individual actors,
roles, scopes, CSRF behavior, optimistic concurrency, and Audit conventions.
