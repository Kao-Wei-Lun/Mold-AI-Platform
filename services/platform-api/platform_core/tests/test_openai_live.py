import os

import pytest

from platform_core.assistant_providers import AssistantEvidenceEnvelope, get_assistant_provider


def test_openai_responses_live_public_demo_contract() -> None:
    """Opt-in and potentially billable; never runs in the default automated suite."""
    if os.getenv("RUN_OPENAI_LIVE_TESTS") != "1":
        pytest.skip("Set RUN_OPENAI_LIVE_TESTS=1 to run the potentially billable live check.")
    if os.getenv("LLM_PROVIDER", "").strip().lower() not in {"openai", "openai-responses"}:
        pytest.fail("Set LLM_PROVIDER=openai explicitly before the live check.")

    limitation = "Synthetic public Demo evidence only; engineer review is required."
    envelope = AssistantEvidenceEnvelope(
        schema_version="1.0",
        intent="explain_similarity",
        locale="zh-TW",
        context_refs={"similarity_search_id": "00000000-0000-0000-0000-000000000001"},
        facts=(
            {
                "fact_id": "fact:live:overall",
                "type": "computed_result",
                "value": "Similarity score 92.8%.",
                "evidence_refs": ["similarity-search:synthetic-live"],
            },
        ),
        evidence=(
            {
                "evidence_ref": "similarity-search:synthetic-live",
                "evidence_type": "synthetic_live_test",
                "classification": "public_demo",
                "content": f"Similarity score 92.8%. {limitation}",
            },
        ),
        required_limitations=(limitation,),
    )

    provider = get_assistant_provider()
    assert provider.health().llm_available, provider.health().reason
    generated = provider.generate(envelope)

    assert generated.status == "succeeded", generated.reason
    assert generated.answer is not None
    assert generated.answer["evidence_refs"] == ["similarity-search:synthetic-live"]
    assert limitation in generated.answer["uncertainties"]
    assert generated.usage["total_tokens"] is not None
