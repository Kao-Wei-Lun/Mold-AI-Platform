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
- Engineering Analysis exposes a dedicated Engineering Knowledge Search workspace at
  `/engineering/knowledge-search`. It contains only query, retrieval filters, evidence, citations,
  protected source download and a governed source-record handoff.
- Governance exposes a dedicated Knowledge Document Management workspace at
  `/governance/knowledge`. It contains document summary, filterable records, ingestion and publication
  status, lifecycle actions and links to immutable version/chunk/citation details.
- `/governance/knowledge?view=import` is a focused import task. Existing documents are not rendered
  below the upload form; successful ingestion hands the user to the imported document or the document
  management list.
- Ordinary workspace query state such as `view`, `tab`, `type` and pagination is not parsed as an MCP
  deep link. Deep-link validation starts only when its version, target or typed reference fields are
  present; forbidden credential-like fields remain rejected.
- The legacy `/knowledge` route redirects through route resolution to document management. MCP and
  ChatGPT knowledge-search deep links resolve to the Engineering Analysis search workspace.
- A workflow reason is requested only after submit, approve, publish or retire is chosen. The modal
  explains the exact status transition and retrieval impact before recording the reason in audit
  evidence.
- Knowledge displays ingestion and publication status independently and exposes only valid next actions.
- Rule and knowledge workspaces show typed server errors without bypassing separation of duties.

## Verification gate

- Legal and illegal state transitions.
- Author self-approval denial.
- Deterministic rule validation and immutable rule versions.
- Published-version replacement without rewriting historical references.
- Knowledge injection quarantine and indexed-before-publish guard.
- Search exclusion for non-published documents.
- Existing Design Review, Knowledge/RAG, MCP, citation and download regressions.
- Vue component tests, type check and production build.
