import { compareMoldPlanningCandidates, previewMoldPlanningResolution } from "./moldPlanning";

describe("mold planning API", () => {
  afterEach(() => vi.restoreAllMocks());

  it("posts canonical context to the preview endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ schema_version: "1.0", selection_mode: "automatic" }) });
    vi.stubGlobal("fetch", fetchMock);

    await previewMoldPlanningResolution({ mold_revision_id: "revision-1", context: { material: "ABS-GENERAL" } });

    expect(String(fetchMock.mock.calls[0][0])).toContain("/api/v1/mold-plans/resolution-preview");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ mold_revision_id: "revision-1", context: { material: "ABS-GENERAL" } });
  });

  it("posts only the selected candidate identifiers for governed comparison", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ schema_version: "1.0", items: [] }) });
    vi.stubGlobal("fetch", fetchMock);

    await compareMoldPlanningCandidates({ mold_revision_id: "revision-1", context: {}, profile_ids: ["profile-a", "profile-b"] });

    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body.profile_ids).toEqual(["profile-a", "profile-b"]);
    expect(String(fetchMock.mock.calls[0][0])).toContain("/candidates/compare");
  });
});
