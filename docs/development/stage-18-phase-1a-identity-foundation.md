# Stage 18 Phase 1A — Local Identity Foundation

## Scope

This phase establishes the server-side identity boundary required before governed data CRUD is
opened. It intentionally keeps the existing controlled Demo bearer mode compatible while adding a
separate `local` mode for individual human accounts.

Implemented:

- stable UUID-backed `AccountProfile` linked to Django's password and session implementation;
- versioned local account status and profile metadata;
- governed `AccessRole`, `DataScope`, and time-bounded `RoleAssignment` records;
- ten seeded system roles and the `public-demo` data scope;
- session login/logout/current-account endpoints with explicit CSRF enforcement;
- password validation, generic login failure responses, bounded login failure rate limiting;
- account list/create/update, activate/suspend/disable, session revocation, role catalog and role
  assignment APIs guarded by `identity:manage`;
- append-only identity and access audit events without passwords or token values;
- one-time `bootstrap_local_admin` command that never accepts a password command-line argument;
- legacy bearer mode remains an entry credential and cannot call identity administration APIs.

Not implemented in this phase:

- the Engineering Web login/account interface (Phase 1B);
- Enterprise OIDC/SAML/SCIM and MCP delegated OAuth identity;
- per-domain permissions finer than the existing Demo read/write boundary;
- company/project/customer ABAC beyond the initial `public-demo` scope;
- the Data Management Center and master-data CRUD.

## Authentication modes

| `DEMO_AUTH_MODE` | Behavior |
|---|---|
| `disabled` | Existing local development behavior; engineering APIs are open. |
| `required` | Existing controlled Demo bearer token behavior. |
| `local` | Individual Django session accounts are required for engineering APIs. |

The shared bearer token is not treated as a human identity. Identity administration always requires
an authenticated account with the `identity:manage` permission.

## First local administrator

Run migrations, then create the first administrator once:

```powershell
docker compose exec api python manage.py migrate
docker compose exec api python manage.py bootstrap_local_admin `
  --username mold-admin `
  --email your-email@example.com `
  --display-name "Mold AI Administrator"
```

The command prompts for the password without echoing it. After one active Platform Admin exists,
the bootstrap command refuses every subsequent attempt. Additional accounts must be created through
the authenticated administration API/UI.

Enable the mode in the untracked `.env` only after the account exists:

```text
DEMO_AUTH_MODE=local
```

Then recreate the API service so it reads the updated environment. Do not add passwords or session
secrets to `.env`, Git, Docker images, URLs, or support logs.

## API surface

```text
GET  /api/v1/auth/csrf
POST /api/v1/auth/login
POST /api/v1/auth/logout
GET  /api/v1/auth/me

GET/POST  /api/v1/admin/users
GET/PATCH /api/v1/admin/users/{account_id}
POST      /api/v1/admin/users/{account_id}/{activate|suspend|disable|revoke-sessions}
GET       /api/v1/admin/identity-catalog
POST      /api/v1/admin/role-assignments
DELETE    /api/v1/admin/role-assignments/{assignment_id}
```

Unsafe local-session requests require the CSRF cookie and matching `X-CSRFToken` header. Account
updates require `row_version`; stale updates return `409 CONCURRENT_MODIFICATION`.

## Verification

The Phase 1A automated tests cover:

- CSRF rejection and successful local session login;
- stable actor/profile identity, roles, permissions and data scopes;
- Viewer read allowance and write denial;
- login rate limiting and password redaction;
- Platform Admin account creation/update/disable and audit events;
- non-admin administration denial;
- suspended-account session revocation;
- one-time administrator bootstrap and password hashing;
- migration drift, all existing backend/frontend tests, production builds and Compose validation.
