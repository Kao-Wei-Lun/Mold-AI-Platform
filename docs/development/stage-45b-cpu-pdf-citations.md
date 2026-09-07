# Stage 45B — CPU PDF citation viewer

Status: Implemented and verified

## Outcome

Knowledge search can open an authorized PDF source at the cited page. When the
versioned citation contract contains a valid top-left point bbox, the Web UI
draws a semi-transparent yellow overlay. If a reliable bbox is unavailable or
invalid, the viewer deliberately falls back to page-level navigation without a
highlight.

## Security and governance contract

- PDF.js requests only the same-origin artifact download endpoint.
- The middleware session or Demo bearer identity remains mandatory.
- Every search API response receives a new signed source ticket. The ticket is
  not persisted, expires after 300 seconds by default, and binds the artifact,
  actor and authorized data scopes.
- Artifact download rechecks the request's allowed classifications.
- Single RFC byte ranges are supported for PDF.js; invalid or multiple ranges
  return HTTP 416 with `Content-Range`.
- The response keeps `nosniff`, sandbox CSP and inline-only behavior for
  knowledge sources and CAD previews.
- Citation payloads expose governed title and anchor data, never server storage
  paths.

## UI behavior

- PDF citations show an **Open cited PDF page** action beside download and
  governed-record navigation.
- The viewer supports previous/next page navigation and reports whether the
  evidence is an exact highlight or page-level citation.
- PDF.js is loaded only when the viewer opens; normal engineering pages do not
  pay the parser bundle cost.
- The worker is packaged with the Web build and does not use a third-party CDN.

## Verification

- Backend tests cover citation format metadata, signed ticket issuance,
  tampered-ticket rejection and byte-range responses.
- Frontend tests cover coordinate validation, percentage projection, invalid
  bbox fallback and PDF-only viewer availability.
- Production Web build confirms the PDF.js worker and lazy PDF module are
  emitted as local assets.
