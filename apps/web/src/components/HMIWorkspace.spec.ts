import { flushPromises, mount } from "@vue/test-utils";

import HMIWorkspace from "./HMIWorkspace.vue";

function jsonResponse(payload: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
  } as Response;
}

function extraction(reviewStatus: "needs_review" | "ready_for_export") {
  return {
    schema_version: "1.0",
    extraction_id: "extraction-1",
    image_artifact_version_id: "image-version-1",
    image_sha256: "abc123",
    image_download_url: "/api/v1/artifact-versions/image-version-1/download",
    profile: "demo-generic-injection@1.0",
    extractor_version: "seven-segment-profile@1.0.0",
    status: "succeeded",
    image_dimensions: { width: 800, height: 500 },
    preprocessing: {},
    fields: [
      {
        field_id: "field-1",
        parameter_code: "injection_pressure_mpa",
        display_label: "Injection Pressure",
        raw_text: "120.0 MPa",
        value: 120,
        unit: "MPa",
        confidence: 1,
        source_region: { x: 0.55, y: 0.16, w: 0.35, h: 0.1, coordinate_space: "normalized" },
        validation_status: "valid",
        review_status: "not_required",
        reviewer_correction: null,
        effective_value: 120,
        effective_unit: "MPa",
      },
      {
        field_id: "field-2",
        parameter_code: "holding_pressure_mpa",
        display_label: "Holding Pressure",
        raw_text: "55.0 MPa",
        value: 55,
        unit: "MPa",
        confidence: 0.7643,
        source_region: { x: 0.55, y: 0.52, w: 0.35, h: 0.1, coordinate_space: "normalized" },
        validation_status: "valid",
        review_status: reviewStatus === "needs_review" ? "needs_review" : "confirmed",
        reviewer_correction:
          reviewStatus === "ready_for_export"
            ? { value: null, unit: "", reviewed_by: "demo-engineer" }
            : null,
        effective_value: 55,
        effective_unit: "MPa",
      },
    ],
    review_status: reviewStatus,
    export_status: reviewStatus === "ready_for_export" ? "ready" : "blocked_pending_review",
    exports: [],
    lineage_ref: "hmi-extraction:extraction-1",
    created_at: "2026-08-26T00:00:00Z",
    limitations: ["Fixed synthetic profile only.", "No image content is sent to cloud vision."],
  };
}

function button(wrapper: ReturnType<typeof mount>, label: string) {
  const found = wrapper.findAll("button").find((item) => item.text().includes(label));
  if (!found) throw new Error(`Button not found: ${label}`);
  return found;
}

describe("HMIWorkspace", () => {
  beforeEach(() => {
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: vi.fn(() => "blob:demo-hmi"),
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: vi.fn(),
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("requires human review before enabling a versioned XLSX export", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/hmi/demo-fixture")) {
        return {
          ok: true,
          status: 200,
          blob: async () => new Blob(["png"], { type: "image/png" }),
        } as Response;
      }
      if (url.endsWith("/hmi-extractions") && init?.method === "POST") {
        expect(init.body).toBeInstanceOf(FormData);
        return jsonResponse(extraction("needs_review"), 201);
      }
      if (url.endsWith("/hmi-extractions/extraction-1/review")) {
        const sent = JSON.parse(String(init?.body));
        expect(sent.reviewed_by).toBe("demo-engineer");
        expect(sent.fields).toEqual([{ field_id: "field-2", action: "confirm" }]);
        return jsonResponse(extraction("ready_for_export"));
      }
      if (url.endsWith("/hmi-extractions/extraction-1/exports")) {
        return jsonResponse(
          {
            export_id: "export-1",
            artifact_version_id: "xlsx-1",
            template_version: "reviewed-parameters@1.0.0",
            download_url: "/api/v1/artifact-versions/xlsx-1/download",
          },
          201,
        );
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const wrapper = mount(HMIWorkspace);
    await button(wrapper, "Load low-confidence").trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("demo-hmi-low-confidence.png");

    await button(wrapper, "Extract four").trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("1 field requires review");
    expect(wrapper.text()).toContain("76.4%");
    expect(button(wrapper, "Generate XLSX").attributes("disabled")).toBeDefined();

    await button(wrapper, "Confirm OCR").trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("Ready for export");
    expect(button(wrapper, "Generate XLSX").attributes("disabled")).toBeUndefined();

    await button(wrapper, "Generate XLSX").trigger("click");
    await flushPromises();
    const link = wrapper.get(".download-link");
    expect(link.text()).toContain("reviewed-parameters@1.0.0");
    expect(link.attributes("href")).toBe("/api/v1/artifact-versions/xlsx-1/download");
  });

  it("surfaces extraction errors without inventing results", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        if (String(input).includes("/hmi/demo-fixture")) {
          return {
            ok: true,
            status: 200,
            blob: async () => new Blob(["png"], { type: "image/png" }),
          } as Response;
        }
        return jsonResponse({ error: { code: "OCR_INVALID_IMAGE", message: "Unreadable image" } }, 400);
      }),
    );
    const wrapper = mount(HMIWorkspace);
    await button(wrapper, "Load low-confidence").trigger("click");
    await flushPromises();
    await button(wrapper, "Extract four").trigger("click");
    await flushPromises();
    expect(wrapper.get("[role='alert']").text()).toBe("Unreadable image");
    expect(wrapper.find(".hmi-table").exists()).toBe(false);
  });
});
