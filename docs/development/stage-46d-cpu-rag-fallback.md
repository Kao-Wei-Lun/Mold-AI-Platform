# Stage 46D — CPU RAG fallback relevance hardening

Status: implemented and activated on the CPU v2 read route.

## Problem found during live acceptance

The hybrid index returned the correct short-shot passages, but the model-free reranker scored the
expanded query as one flat token set. Synonym expansion therefore diluted the overlap of a concise
Traditional Chinese question and caused a safe but unnecessary abstention below the approved
`0.32` threshold.

## Delivered behavior

- Query expansion remains part of dense and sparse candidate retrieval.
- The final model-free relevance gate evaluates the original question and each governed synonym
  independently, then uses the strongest supported lexical score.
- The fallback reranker ignores artificial whole-sentence CJK terms and compares deterministic CJK
  bigrams. The persisted dense/sparse retrieval tokenizer remains unchanged, so existing v2 vectors
  do not need to be rebuilt.
- The approved abstention threshold is unchanged. Unrelated questions still abstain.
- Retrieval provenance records
  `query_policy=original-plus-expansion-max@1.0.0` and
  `governed-lexical-reranker@1.1.0`.

This keeps the Demo useful without a GPU, external LLM API, or downloaded embedding/reranker model,
while preserving ACL filters, citations and conservative abstention.
