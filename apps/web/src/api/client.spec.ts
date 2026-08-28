import {
  apiFetch,
  clearDemoAccessToken,
  clearCsrfToken,
  consumeDemoAccessBootstrap,
  downloadProtectedArtifact,
  setCsrfToken,
  setDemoAccessToken,
} from "./client";

function response(status = 200, headers: Record<string, string> = {}): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers(headers),
    blob: async () => new Blob(["artifact"]),
  } as Response;
}

describe("authenticated API client", () => {
  beforeEach(() => {
    clearDemoAccessToken();
    clearCsrfToken();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    clearDemoAccessToken();
    clearCsrfToken();
  });

  it("adds the session-only Demo bearer token without overriding an explicit header", async () => {
    setDemoAccessToken("demo-secret-token");
    const fetchMock = vi.fn().mockResolvedValue(response());
    vi.stubGlobal("fetch", fetchMock);

    await apiFetch("/api/v1/system/info");
    const firstHeaders = new Headers(fetchMock.mock.calls[0][1]?.headers);
    expect(firstHeaders.get("Authorization")).toBe("Bearer demo-secret-token");

    await apiFetch("/api/v1/system/info", { headers: { Authorization: "Bearer explicit-token" } });
    const secondHeaders = new Headers(fetchMock.mock.calls[1][1]?.headers);
    expect(secondHeaders.get("Authorization")).toBe("Bearer explicit-token");
  });

  it("consumes a Sites bootstrap token from the URL fragment and immediately scrubs it", () => {
    window.history.replaceState(null, "", "/#mold-ai-bootstrap=token=sites-secret");

    expect(consumeDemoAccessBootstrap()).toBe(true);
    expect(window.sessionStorage.getItem("mold-ai.demo-access-token")).toBe("sites-secret");
    expect(window.location.hash).toBe("");
  });

  it("signals the UI when the server rejects the current session", async () => {
    const listener = vi.fn();
    window.addEventListener("mold-ai:unauthorized", listener);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(401)));

    await apiFetch("/api/v1/system/info");

    expect(listener).toHaveBeenCalledOnce();
    window.removeEventListener("mold-ai:unauthorized", listener);
  });

  it("uses credentialed requests and adds CSRF only to unsafe methods", async () => {
    setCsrfToken("csrf-session-token");
    const fetchMock = vi.fn().mockResolvedValue(response());
    vi.stubGlobal("fetch", fetchMock);

    await apiFetch("/api/v1/system/info");
    await apiFetch("/api/v1/assistant/messages", { method: "POST" });

    expect(fetchMock.mock.calls[0][1]?.credentials).toBe("include");
    expect(new Headers(fetchMock.mock.calls[0][1]?.headers).has("X-CSRFToken")).toBe(false);
    expect(fetchMock.mock.calls[1][1]?.credentials).toBe("include");
    expect(new Headers(fetchMock.mock.calls[1][1]?.headers).get("X-CSRFToken")).toBe(
      "csrf-session-token",
    );
  });

  it("downloads protected artifacts through the authenticated request path", async () => {
    setDemoAccessToken("download-token");
    const fetchMock = vi.fn().mockResolvedValue(
      response(200, { "Content-Disposition": 'attachment; filename="reviewed.xlsx"' }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    const createObjectURL = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:protected");
    const revokeObjectURL = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);

    await downloadProtectedArtifact("/api/v1/artifact-versions/xlsx-1/download", "fallback.xlsx");

    const headers = new Headers(fetchMock.mock.calls[0][1]?.headers);
    expect(headers.get("Authorization")).toBe("Bearer download-token");
    expect(createObjectURL).toHaveBeenCalledOnce();
    expect(click).toHaveBeenCalledOnce();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:protected");
  });
});
