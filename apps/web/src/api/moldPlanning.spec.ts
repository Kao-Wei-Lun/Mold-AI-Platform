import { previewMoldPlanningResolution } from "./moldPlanning";

describe("mold planning API", () => {
  afterEach(() => vi.restoreAllMocks());

  it("posts canonical context to the preview endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ schema_version: "1.0", selection_mode: "automatic" }) });
    vi.stubGlobal("fetch", fetchMock);

    await previewMoldPlanningResolution({ mold_revision_id: "revision-1", context: { material: "ABS-GENERAL" } });

    expect(String(fetchMock.mock.calls[0][0])).toContain("/api/v1/mold-plans/resolution-preview");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ mold_revision_id: "revision-1", context: { material: "ABS-GENERAL" } });
  });
});
