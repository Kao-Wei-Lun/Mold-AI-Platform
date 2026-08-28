import { flushPromises, mount } from "@vue/test-utils";

import type { CADModelResult } from "../api/cad";
import DesignReviewWorkspace from "./DesignReviewWorkspace.vue";

const query: CADModelResult = {
  cad_model_id: "cad-review",
  artifact_version_id: "version-review",
  cad_format: "step",
  unit_system: "mm",
  parser: { name: "cadquery", version: "2.8.0" },
  geometry_status: "succeeded",
  bounding_box: {
    min: { x: 0, y: 0, z: 0 },
    max: { x: 30, y: 10, z: 5 },
    size: { x: 30, y: 10, z: 5 },
  },
  volume: 6000,
  surface_area: 2200,
  face_count: 6,
  edge_count: 12,
  surface_type_histogram: { plane: 6 },
  quality_flags: [],
  preview: {
    artifact_version_id: "preview-review",
    original_filename: "review.preview.stl",
    media_type: "model/stl",
    format: "stl",
    size_bytes: 100,
    sha256: "preview-sha",
    download_url: "/review-preview",
  },
  similarity_index: null,
};

function jsonResponse(payload: object, status = 200): Response {
  return { ok: status < 400, status, json: async () => payload } as Response;
}

describe("DesignReviewWorkspace", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows deterministic evidence and records an audited waiver", async () => {
    const finding = {
      finding_id: "finding-rib",
      rule: {
        rule_version_id: "rule-version-rib",
        rule_id: "DEMO-RIB-RATIO-012",
        rule_version: "1.0",
        title: "Rib-to-wall thickness ratio",
        description: "Synthetic Demo rule.",
        evaluator: "context_ratio",
        condition: { operator: "lte", limit: 0.6, unit: "ratio", tolerance: 0 },
        severity: "high",
        risk_type: "sink_mark",
        recommendation: "Reduce rib thickness or obtain a waiver.",
        reference: {
          document: "Mold AI Demo Rule Catalog",
          revision: "1.0",
          classification: "synthetic_demo_not_engineering_guidance",
        },
      },
      result: "FAIL",
      actual_value: 0.75,
      limit_value: 0.6,
      unit: "ratio",
      severity: "high",
      risk_type: "sink_mark",
      geometry_location: { scope: "context:rib-measurement" },
      evidence_refs: ["context:rib-measurement"],
      quality_flags: ["USER_SUPPLIED_DEMO_MEASUREMENT"],
      message: "Measured 0.75 ratio; required ≤ 0.6 ratio.",
      decisions: [],
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse(
          {
            status: "accepted",
            review_id: "review-1",
            job_id: "job-review-1",
            idempotent_replay: false,
          },
          202,
        ),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          schema_version: "1.0",
          job_id: "job-review-1",
          capability: "mold.design_review@1.0.0",
          state: "succeeded",
          stage: "completed",
          progress: 100,
          attempt: 1,
          artifact_version_id: "version-review",
          correlation_id: "correlation-review",
          error: null,
          result: {
            review_id: "review-1",
            job_id: "job-review-1",
            review_status: "succeeded",
            artifact_version_id: "version-review",
            profile: {
              profile_key: "demo-general-design@1.0",
              version: "1.0",
              status: "approved_demo",
              ruleset_checksum: "checksum",
              rule_count: 13,
            },
            geometry_engine_version: "cadquery@2.8.0",
            input_snapshot: {},
            context: { nominal_wall_thickness_mm: 2, max_rib_thickness_mm: 1.5 },
            summary: {
              total: 13,
              decision: "FAIL",
              counts: {
                PASS: 11,
                FAIL: 1,
                NOT_APPLICABLE: 0,
                NOT_EVALUATED: 1,
                ERROR: 0,
              },
            },
            preview: query.preview,
            findings: [finding],
            limitations: ["Synthetic thresholds only."],
          },
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse(
          {
            schema_version: "1.0",
            finding_result: "FAIL",
            record: {
              decision_id: "decision-1",
              decision: "waived",
              reason: "Synthetic fixture exception.",
              decided_by: "demo-reviewer",
              approved_by: "demo-approver",
              created_at: "2026-08-26T00:00:00Z",
            },
          },
          201,
        ),
      );
    vi.stubGlobal("fetch", fetchMock);

    const wrapper = mount(DesignReviewWorkspace, {
      props: { query },
      global: { stubs: { CadPreview: true } },
    });
    const measurements = wrapper.findAll(".review-form input");
    await measurements[0].setValue("2");
    await measurements[1].setValue("1.5");
    await wrapper.get(".review-form").trigger("submit");
    await flushPromises();

    expect(wrapper.text()).toContain("Rib-to-wall thickness ratio");
    expect(wrapper.text()).toContain("0.75 ratio");
    expect(wrapper.text()).toContain("0.6 ratio");
    expect(wrapper.text()).toContain("context:rib-measurement");

    const decisionSelects = wrapper.findAll(".decision-form select");
    await decisionSelects[0].setValue("waived");
    await wrapper.get(".decision-form textarea").setValue("Synthetic fixture exception.");
    await decisionSelects[1].setValue("demo-lead-engineer");
    await wrapper.get(".decision-form").trigger("submit");
    await flushPromises();

    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(wrapper.text()).toContain("waived by demo-reviewer");
    const reviewRequest = JSON.parse(String(fetchMock.mock.calls[0][1]?.body));
    expect(reviewRequest.context).toEqual({
      nominal_wall_thickness_mm: 2,
      max_rib_thickness_mm: 1.5,
    });
    const decisionRequest = JSON.parse(String(fetchMock.mock.calls[2][1]?.body));
    expect(decisionRequest).toMatchObject({
      decision: "waived",
      approved_by: "demo-lead-engineer",
    });
  });

  it("requires processed CAD before review", () => {
    const wrapper = mount(DesignReviewWorkspace, { props: { query: null } });

    expect(wrapper.text()).toContain("Process a CAD artifact");
    expect(wrapper.find(".review-form").exists()).toBe(false);
  });
});
