import { flushPromises, mount } from "@vue/test-utils";

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
