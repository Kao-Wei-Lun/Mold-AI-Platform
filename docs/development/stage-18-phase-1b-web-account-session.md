# Stage 18 Phase 1B — Engineering Web Account Session

## Scope

This phase connects the Stage 18 Phase 1A local identity foundation to the Vue Engineering Web.
The existing access component now supports three explicit deployment modes without mixing their
credentials or identity semantics.

Implemented:

- `disabled`: preserves open local-development behavior;
- `required`: preserves the legacy controlled Demo bearer-token flow;
- `local`: restores an existing individual session or presents username/password sign-in;
- current account name and normalized role summary in the compact access boundary;
- sign-out through the server session endpoint;
- credentialed API requests and automatic CSRF header attachment for unsafe methods;
- CSRF refresh before login and again after Django rotates the CSRF secret at login;
- credentials are submitted to the server only and are never stored in browser storage;
- English and Traditional Chinese account-session copy;
- responsive local-account form and accessible autocomplete, labels, busy and error states.

The private Sites entry remains its existing owner-only access boundary. This phase does not add a
second app-owned authentication system to Sites and does not treat Sites or Secure Tunnel identity
as a Mold AI human account. Enterprise and MCP delegated identity remain separate future adapters.

## Request behavior

All Engineering Web API calls use `credentials: include`. Unsafe methods add `X-CSRFToken` only
when a local-session CSRF value has been established. Safe GET/HEAD/OPTIONS requests do not receive
the header. Legacy bearer credentials continue to use session-only browser storage and do not gain
identity administration permissions.

The current-account endpoint is safe to call before login. It returns an anonymous contract when no
valid session exists, allowing the UI to restore a session without producing a false expired-session
warning.

## Verification

Automated coverage verifies:

- bearer flow compatibility;
- disabled local-development behavior;
- anonymous local-account state;
- CSRF acquisition, local sign-in, post-login CSRF rotation and sign-out;
- account and role presentation;
- no bearer-token browser storage is used for local account credentials;
- unsafe API requests receive CSRF while safe requests do not;
- credentialed fetch is used consistently;
- unauthorized events clear both legacy and account presentation state;
- TypeScript, component tests, production build and full project regression.
