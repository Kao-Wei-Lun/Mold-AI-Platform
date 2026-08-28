# Stage 17 Phase A — Multi-route Engineering Workspace

Phase A changes the Web from one long page that mounted every capability into focused workflow
routes. It does not change engineering calculations, evidence contracts, permissions or deep-link
identifier validation.

## Canonical routes

| Route | Workspace |
|---|---|
| `/` | Guided Demo and readiness summary |
| `/engineering/cad` | CAD and Artifact preparation |
| `/engineering/similarity` | Similarity ranking and explanation |
| `/engineering/design-review` | Deterministic Design Review |
| `/engineering/process-trial` | Process and Trial evidence |
| `/engineering/cae` | CAE/Moldflow comparison |
| `/engineering/hmi` | Machine HMI review and Excel export |
| `/knowledge` | Governed Knowledge/RAG |
| `/governance/rules` | Approved Mold Rule catalog |
| `/status` | Platform and access readiness |

Nginx already routes unknown non-asset paths to `index.html`, so refresh and direct navigation work
without exposing new backend ports. The small History API router resolves only allowlisted paths and
supports browser back/forward. No new routing dependency was required.

## Context and deep links

- A selected CAD model remains in the App Shell while the user moves to Similarity or Design Review.
- The top bar exposes current route, Demo data scope and abbreviated selected ArtifactVersion.
- Existing Stage 13 links remain compatible. A validated `target=similarity`, `design_review`,
  `knowledge`, `process_trial`, `cae`, `hmi` or `job` query is mapped to its canonical route before
  the referenced record is loaded.
- Navigation clears a stale deep-link query instead of carrying identifiers into an unrelated page.
- The UI still reloads records from the API and never trusts URL claims or permissions.

## Guided Demo

Home presents the seven supported engineering steps, a clear first action and compact core-service
status. Opening a step mounts only that workspace. This reduces initial cognitive load, background
requests and accidental cross-workflow actions.

## Mold Rule governance catalog

The new page retrieves the approved RuleProfile and displays:

- profile key/version/status, owner and approver;
- enabled rule count and ruleset checksum;
- Rule ID/version, title, description and evaluator;
- threshold/operator/unit/tolerance;
- severity, risk type and governed source reference;
- client-side search and severity filtering.

The page is deliberately read-only. Current rules are immutable evidence inputs. Adding a normal
Edit button before implementing draft/version/approval would allow an operator to silently change a
threshold used by historical or concurrent reviews.

## Required rule-authoring follow-up

A future write-enabled administration phase should add these contracts before UI editing:

1. `draft` RuleProfile revisions separate from the active approved profile.
2. Author, reviewer and approver roles; the author cannot self-approve in enterprise mode.
3. Typed validation for evaluator, operator, unit, tolerance, applicability and reference.
4. Human-readable before/after diff and mandatory change reason.
5. Golden CAD regression against expected review outcomes before approval.
6. Approval creates immutable RuleVersions and a new ruleset checksum.
7. Scheduled activation/effective dates; running jobs retain their input profile snapshot.
8. Rollback activates a previously approved profile rather than deleting history.
9. Audit Events for create, submit, reject, approve, activate and rollback.
10. Public Demo remains read-only; write controls require a separate privileged environment.

## Verification

- Web typecheck passed.
- Sixteen Web test files and 53 tests passed in the focused Phase A run.
- Production Vite build passed; the route-based shell added no runtime dependency.
- Direct local route rendering returned HTTP 200.
- Full repository regression and running Sites Demo smoke are required before the phase commit.

## Next UX phases

- Phase B: CAD upload stepper, persistent recent-work context and global Job Center.
- Phase C: Similarity three-pane comparison and synchronized evidence drawer.
- Phase D: Design Review finding/evidence workflow and future governed Rule authoring.
- Phase E: Knowledge source viewer, Process/Trial, CAE and HMI task-focused refinement.
- Phase F: accessibility audit, responsive workflow testing and frontend performance baseline.
