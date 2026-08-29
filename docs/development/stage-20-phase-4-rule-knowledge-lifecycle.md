# Stage 20 — Phase 4 Governed Rule and Knowledge Lifecycle

## Outcome

Phase 4 replaces in-place governance assumptions with versioned, auditable publishing workflows.
Published engineering results continue to reference their exact `RuleProfile`, `RuleVersion`,
`KnowledgeDocument` and `ArtifactVersion`; historical evidence is never rewritten.

## Rule lifecycle

- `RuleProfile` is versioned by `(profile_key, version)`.
- Workflow: `draft → validated → in_review → approved → published → retired`.
- A new version is created by cloning a published source profile and its immutable rule versions.
- Deterministic validation rejects empty rule sets, unregistered evaluators and unsupported operators.
- Rule authors may clone, validate and submit; reviewers/approvers approve and publish.
- The profile author cannot approve the same profile version.
- Publishing retires the previously published version with the same profile key.
- Design Review always resolves the newest published profile; historical ReviewRun foreign keys remain
  unchanged.
- RuleVersion engineering content is immutable after creation.
- Every lifecycle mutation writes an AuditEvent with actor, reason and target reference.

## Knowledge lifecycle

- Knowledge versions are identified by `(document_key, version_number)` and may point to the exact
  superseded document.
- New Web uploads enter `draft`; direct internal fixtures default to `published` for backward-compatible
  deterministic tests.
- Workflow: `draft → in_review → approved → published → retired`.
- Only indexed, injection-scan-clear documents can be published.
- Quarantined, suspicious, unauthorized, non-effective, draft and retired documents are excluded from
  new retrieval candidates.
- Publishing a new version retires the previously published version with the same document key.
- Citations continue to point to the immutable ArtifactVersion and chunk locator.
- Author/approver separation and row-version concurrency checks apply to lifecycle actions.

## Permissions

- `rules:read`, `rules:author`, `rules:approve`
- `knowledge:read`, `knowledge:author`, `knowledge:approve`

Local Demo roles receive the minimum permissions required by their responsibility. Platform Admin has
all Phase 4 permissions. Enterprise group mapping remains adapter-driven and deferred to Phase 7.

## UI

- Mold Rules displays the workflow status and a controlled clone/validate/submit/approve/publish/retire
  panel when the signed-in account is authorized.
- Knowledge displays ingestion and publication status independently and exposes only valid next actions.
- Both workspaces require a reason and show typed server errors without bypassing separation of duties.

## Verification gate

- Legal and illegal state transitions.
- Author self-approval denial.
- Deterministic rule validation and immutable rule versions.
- Published-version replacement without rewriting historical references.
- Knowledge injection quarantine and indexed-before-publish guard.
- Search exclusion for non-published documents.
- Existing Design Review, Knowledge/RAG, MCP, citation and download regressions.
- Vue component tests, type check and production build.
