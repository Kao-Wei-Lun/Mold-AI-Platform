import { flushPromises, mount } from "@vue/test-utils";

import type { CADModelResult } from "./api/cad";
import App from "./App.vue";
import { setLocale } from "./i18n";

const readiness = {
  status: "ok",
  services: [
    { name: "database", status: "ok", detail: null },
    { name: "redis", status: "ok", detail: null },
    { name: "qdrant", status: "ok", detail: null },
  ],
};
const preflight = {
  schema_version: "1.0",
  environment: "development",
  production_ready: true,
  checks: {},
  auth: { required: false },
  mcp: { secure_tunnel_configured: true, oauth_implemented: false },
};
const adminAccount = {
  id: "account-admin",
  username: "admin",
  email: "admin@example.test",
  display_name: "Demo Administrator",
  status: "active",
  locale: "zh-TW",
  timezone: "Asia/Taipei",
  row_version: 1,
  roles: ["platform_admin"],
  permissions: ["public-demo:read", "public-demo:write", "identity:manage", "master-data:read", "master-data:manage"],
  data_scopes: ["public-demo"],
  role_assignments: [
    {
      id: "assignment-admin",
      role_code: "platform_admin",
      role_name: "Platform Admin",
      scope_code: "public-demo",
      scope_name: "Public Synthetic Demo",
      valid_from: null,
      valid_to: null,
    },
  ],
  last_login_at: "2026-08-28T04:00:00Z",
  created_at: "2026-08-28T00:00:00Z",
};
const activeCADResult: CADModelResult = {
  cad_model_id: "cad-persistent",
  artifact_version_id: "version-persistent",
  cad_format: "stl",
  unit_system: "mm",
  parser: { name: "trimesh", version: "4.12.2" },
  geometry_status: "succeeded",
  bounding_box: {
    min: { x: 0, y: 0, z: 0 },
    max: { x: 160, y: 160, z: 5 },
    size: { x: 160, y: 160, z: 5 },
  },
  volume: 117091.109,
  surface_area: 53218.77,
  face_count: 79558,
  edge_count: 119337,
  surface_type_histogram: { triangle: 79558 },
  quality_flags: ["UNIT_UNCERTAIN"],
  preview: {
    artifact_version_id: "preview-persistent",
    original_filename: "persistent.preview.stl",
    media_type: "model/stl",
    format: "stl",
    size_bytes: 3977984,
    sha256: "persistent-sha",
    download_url: "/preview-persistent",
  },
  similarity_index: null,
};

function jsonResponse(payload: unknown, status = 200): Response {
  return { ok: status >= 200 && status < 300, status, json: async () => payload } as Response;
}

function installApiMock(healthPayload: unknown = readiness): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn().mockImplementation((input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("security/preflight")) return Promise.resolve(jsonResponse(preflight));
    if (url.includes("health/ready")) return Promise.resolve(jsonResponse(healthPayload));
    if (url.includes("rule-profiles")) {
      return Promise.resolve(jsonResponse({ schema_version: "1.0", items: [] }));
    }
    return Promise.resolve(jsonResponse({}));
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("App", () => {
  beforeEach(() => {
    setLocale("en");
    window.history.replaceState(null, "", "/");
    vi.stubGlobal("scrollTo", vi.fn());
  });
  afterEach(() => vi.restoreAllMocks());

  it("renders a focused guided home instead of every engineering workspace", async () => {
    installApiMock();
    const wrapper = mount(App);
    await flushPromises();

    expect(wrapper.text()).toContain("Complete the seven-step guided Demo");
    expect(wrapper.text()).toContain("Core services");
    expect(wrapper.find(".cad-workspace").exists()).toBe(false);
    expect(wrapper.find(".similarity-workspace").exists()).toBe(false);
  });

  it("shows dependency status on the dedicated status route", async () => {
    window.history.replaceState(null, "", "/status");
    installApiMock();
    const wrapper = mount(App);
    await flushPromises();

    expect(wrapper.text()).toContain("Platform services");
    expect(wrapper.text()).toContain("database");
    expect(wrapper.findAll(".status-pill")).toHaveLength(3);
  });

  it("navigates to a dedicated governance route without a full reload", async () => {
    installApiMock();
    const wrapper = mount(App);
    await flushPromises();

    await wrapper.get('a[href="/governance/rules"]').trigger("click");
    await flushPromises();

    expect(window.location.pathname).toBe("/governance/rules");
    expect(wrapper.text()).toContain("Understand the rules that govern design review");
    expect(wrapper.find(".cad-workspace").exists()).toBe(false);
  });

  it("keeps the selected CAD result when navigating away and returning", async () => {
    window.history.replaceState(null, "", "/engineering/cad");
    installApiMock();
    const wrapper = mount(App, { global: { stubs: { CadPreview: true } } });
    await flushPromises();

    wrapper.findComponent({ name: "CadWorkspace" }).vm.$emit("ready", activeCADResult);
    await flushPromises();
    expect(wrapper.text()).toContain("160.00 x 160.00 x 5.00 mm");

    await wrapper.get('a[href="/engineering/similarity"]').trigger("click");
    await flushPromises();
    expect(wrapper.find(".cad-workspace").exists()).toBe(false);

    await wrapper.get('a[href="/engineering/cad"]').trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("160.00 x 160.00 x 5.00 mm");
    expect(wrapper.text()).toContain("79558 / 119337");
  });

  it("restores an administrator session before loading a direct identity route", async () => {
    window.history.replaceState(null, "", "/governance/identity");
    const localPreflight = {
      ...preflight,
      auth: {
        mode: "local",
        required: true,
        token_configured: false,
        local_accounts_enabled: true,
        local_admin_configured: true,
        scopes: ["public-demo"],
      },
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("security/preflight")) return jsonResponse(localPreflight);
        if (url.endsWith("/auth/me")) {
          return jsonResponse({ authenticated: true, account: adminAccount });
        }
        if (url.endsWith("/auth/csrf")) return jsonResponse({ csrf_token: "identity-csrf" });
        if (url.endsWith("/admin/users")) return jsonResponse({ results: [adminAccount] });
        if (url.endsWith("/admin/identity-catalog")) {
          return jsonResponse({
            roles: [
              {
                code: "platform_admin",
                name: "Platform Admin",
                description: "Identity management",
                permissions: adminAccount.permissions,
              },
            ],
            data_scopes: [
              {
                id: "scope-1",
                code: "public-demo",
                name: "Public Synthetic Demo",
                classification: "public_demo",
              },
            ],
          });
        }
        if (url.includes("health/ready")) return jsonResponse(readiness);
        return jsonResponse({});
      }),
    );

    const wrapper = mount(App);
    await flushPromises();

    expect(wrapper.get('a[href="/governance/identity"]').text()).toContain("Accounts & access");
    expect(wrapper.text()).toContain("Demo Administrator");
    expect(wrapper.find(".identity-management-workspace table").exists()).toBe(true);
  });

  it("shows an actionable error when the health API cannot be reached", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((input: RequestInfo | URL) =>
        String(input).includes("security/preflight")
          ? Promise.resolve(jsonResponse(preflight))
          : Promise.reject(new Error("network unavailable")),
      ),
    );
    const wrapper = mount(App);
    await flushPromises();

    await wrapper.get('a[href="/status"]').trigger("click");
    expect(wrapper.get('[role="alert"]').text()).toContain("network unavailable");
  });

  it("switches the full shell to Traditional Chinese and persists the preference", async () => {
    installApiMock();
    const wrapper = mount(App);
    await flushPromises();

    await wrapper.findAll(".language-switch button")[1].trigger("click");

    expect(wrapper.text()).toContain("完成七步驟 Demo 導引");
    expect(wrapper.text()).toContain("模具規定");
    expect(document.documentElement.lang).toBe("zh-TW");
    expect(window.localStorage.getItem("mold-ai.locale")).toBe("zh-TW");

    await wrapper.findAll(".language-switch button")[0].trigger("click");
    expect(wrapper.text()).toContain("Complete the seven-step guided Demo");
  });
});
