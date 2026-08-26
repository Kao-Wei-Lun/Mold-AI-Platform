import { flushPromises, mount } from "@vue/test-utils";

import AccessPanel from "./AccessPanel.vue";

function response(payload: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
  } as Response;
}

function preflight(required: boolean) {
  return {
    schema_version: "1.0",
    environment: required ? "release" : "development",
    auth: {
      mode: required ? "required" : "disabled",
      required,
      token_configured: required,
      scopes: ["public-demo:read", "public-demo:write"],
    },
    request_security: { is_secure: required, trusted_proxy_headers: required },
    mcp: {
      public_https_configured: false,
      secure_tunnel_configured: required,
      recommended_demo_path: "secure_mcp_tunnel",
      oauth_implemented: false,
    },
    checks: { auth_mode_valid: true, debug_disabled: required },
    external_mode: required,
    production_ready: required,
    limitations: [],
  };
}

describe("AccessPanel", () => {
  beforeEach(() => window.sessionStorage.clear());

  afterEach(() => {
    vi.restoreAllMocks();
    window.sessionStorage.clear();
  });

  it("unlocks the workspace only after the server accepts the entered token", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/security/preflight")) return response(preflight(true));
      if (url.endsWith("/system/info")) {
        expect(new Headers(init?.headers).get("Authorization")).toBe("Bearer stage10-secret");
        return response({ name: "Mold AI Platform" });
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    const wrapper = mount(AccessPanel);
    await flushPromises();

    expect(wrapper.text()).toContain("Access locked");
    await wrapper.get("input[type='password']").setValue("stage10-secret");
    await wrapper.get("form").trigger("submit");
    await flushPromises();

    expect(wrapper.text()).toContain("Access ready");
    expect(wrapper.emitted("ready")?.at(-1)).toEqual([true]);
    expect(window.sessionStorage.getItem("mold-ai.demo-access-token")).toBe("stage10-secret");
  });

  it("automatically enables the local workspace while showing pending release checks", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(preflight(false))));
    const wrapper = mount(AccessPanel);
    await flushPromises();

    expect(wrapper.text()).toContain("Local authentication disabled");
    expect(wrapper.text()).toContain("1 checks pending");
    expect(wrapper.emitted("ready")?.at(-1)).toEqual([true]);
  });

  it("clears the session when any API call reports unauthorized", async () => {
    window.sessionStorage.setItem("mold-ai.demo-access-token", "stored-token");
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        if (String(input).endsWith("/security/preflight")) return response(preflight(true));
        return response({ name: "Mold AI Platform" });
      }),
    );
    const wrapper = mount(AccessPanel);
    await flushPromises();
    window.dispatchEvent(new CustomEvent("mold-ai:unauthorized"));
    await flushPromises();

    expect(wrapper.text()).toContain("session expired or was rejected");
    expect(window.sessionStorage.getItem("mold-ai.demo-access-token")).toBeNull();
    expect(wrapper.emitted("ready")?.at(-1)).toEqual([false]);
  });
});
