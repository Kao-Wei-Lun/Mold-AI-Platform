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

function localPreflight() {
  return {
    ...preflight(true),
    auth: {
      mode: "local",
      required: true,
      token_configured: false,
      local_accounts_enabled: true,
      local_admin_configured: true,
      methods: ["session"],
      scopes: [],
    },
  };
}

const localAccount = {
  id: "account-1",
  username: "engineer",
  email: "engineer@example.test",
  display_name: "Demo Engineer",
  status: "active",
  locale: "zh-TW",
  timezone: "Asia/Taipei",
  row_version: 1,
  roles: ["mold_engineer"],
  permissions: ["public-demo:read", "public-demo:write"],
  data_scopes: ["public-demo"],
  last_login_at: null,
  created_at: "2026-08-28T00:00:00Z",
};

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

  it("signs in with an individual local account without storing credentials", async () => {
    let csrfCount = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/security/preflight")) return response(localPreflight());
      if (url.endsWith("/auth/me")) {
        return response({ authenticated: false, authentication_method: "none", account: null });
      }
      if (url.endsWith("/auth/csrf")) {
        csrfCount += 1;
        return response({ csrf_token: `csrf-${csrfCount}` });
      }
      if (url.endsWith("/auth/login")) {
        expect(new Headers(init?.headers).get("X-CSRFToken")).toBe("csrf-1");
        expect(JSON.parse(String(init?.body))).toEqual({
          username: "engineer",
          password: "private-password",
        });
        return response({ authenticated: true, account: localAccount });
      }
      if (url.endsWith("/auth/logout")) {
        expect(new Headers(init?.headers).get("X-CSRFToken")).toBe("csrf-2");
        return response(null, 204);
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    const wrapper = mount(AccessPanel, { props: { compact: true } });
    await flushPromises();

    expect(wrapper.text()).toContain("Individual account required");
    const inputs = wrapper.findAll("input");
    await inputs[0].setValue("engineer");
    await inputs[1].setValue("private-password");
    await wrapper.get("form").trigger("submit");
    await flushPromises();

    expect(wrapper.text()).toContain("Demo Engineer");
    expect(wrapper.text()).toContain("mold engineer");
    expect(window.sessionStorage.getItem("mold-ai.demo-access-token")).toBeNull();
    expect(wrapper.emitted("ready")?.at(-1)).toEqual([true]);

    await wrapper.get("button.secondary-button").trigger("click");
    await flushPromises();
    expect(wrapper.emitted("ready")?.at(-1)).toEqual([false]);
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
