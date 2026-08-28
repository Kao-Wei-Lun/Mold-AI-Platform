import { flushPromises, mount } from "@vue/test-utils";

import { clearCsrfToken, setCsrfToken } from "../api/client";
import type { LocalAccount } from "../api/identity";
import IdentityManagementWorkspace from "./IdentityManagementWorkspace.vue";

function response(payload: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
  } as Response;
}

const catalog = {
  roles: [
    { code: "viewer", name: "Viewer", description: "Read only", permissions: ["public-demo:read"] },
    {
      code: "platform_admin",
      name: "Platform Admin",
      description: "Identity management",
      permissions: ["public-demo:read", "public-demo:write", "identity:manage"],
    },
  ],
  data_scopes: [
    { id: "scope-1", code: "public-demo", name: "Public Synthetic Demo", classification: "public_demo" },
  ],
};

function account(overrides: Partial<LocalAccount> = {}): LocalAccount {
  return {
    id: "account-admin",
    username: "admin",
    email: "admin@example.test",
    display_name: "Demo Administrator",
    status: "active",
    locale: "zh-TW",
    timezone: "Asia/Taipei",
    row_version: 1,
    roles: ["platform_admin"],
    permissions: ["public-demo:read", "public-demo:write", "identity:manage"],
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
    ...overrides,
  };
}

describe("IdentityManagementWorkspace", () => {
  beforeEach(() => {
    setCsrfToken("identity-csrf");
    vi.stubGlobal("confirm", vi.fn().mockReturnValue(true));
  });

  afterEach(() => {
    clearCsrfToken();
    vi.restoreAllMocks();
  });

  it("denies the workspace when the signed-in account lacks identity management permission", async () => {
    const viewer = account({ permissions: ["public-demo:read"], roles: ["viewer"] });
    const wrapper = mount(IdentityManagementWorkspace, { props: { currentAccount: viewer } });
    await flushPromises();

    expect(wrapper.get('[role="alert"]').text()).toContain("Identity management access denied");
    expect(wrapper.find("table").exists()).toBe(false);
  });

  it("loads governed accounts and presents status, roles and scope", async () => {
    const viewer = account({
      id: "account-viewer",
      username: "viewer",
      display_name: "Demo Viewer",
      roles: ["viewer"],
      permissions: ["public-demo:read"],
      role_assignments: [
        {
          id: "assignment-viewer",
          role_code: "viewer",
          role_name: "Viewer",
          scope_code: "public-demo",
          scope_name: "Public Synthetic Demo",
          valid_from: null,
          valid_to: null,
        },
      ],
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/admin/users")) return response({ results: [account(), viewer] });
        if (url.endsWith("/admin/identity-catalog")) return response(catalog);
        throw new Error(`Unexpected request: ${url}`);
      }),
    );

    const wrapper = mount(IdentityManagementWorkspace, { props: { currentAccount: account() } });
    await flushPromises();

    expect(wrapper.text()).toContain("Accounts and access");
    expect(wrapper.text()).toContain("Demo Administrator");
    expect(wrapper.text()).toContain("Demo Viewer");
    expect(wrapper.text()).toContain("Public Synthetic Demo");
    expect(wrapper.findAll("tbody tr")).toHaveLength(2);
  });

  it("loads after an administrator session is restored on a direct route", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/admin/users")) return response({ results: [account()] });
      if (url.endsWith("/admin/identity-catalog")) return response(catalog);
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    const wrapper = mount(IdentityManagementWorkspace, { props: { currentAccount: null } });
    await flushPromises();

    expect(wrapper.text()).toContain("Identity management access denied");
    await wrapper.setProps({ currentAccount: account() });
    await flushPromises();

    expect(wrapper.text()).toContain("Demo Administrator");
    expect(wrapper.find("table").exists()).toBe(true);
  });

  it("does not offer self-lockout actions to the current platform administrator", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/admin/users")) return response({ results: [account()] });
        if (url.endsWith("/admin/identity-catalog")) return response(catalog);
        throw new Error(`Unexpected request: ${url}`);
      }),
    );
    const wrapper = mount(IdentityManagementWorkspace, { props: { currentAccount: account() } });
    await flushPromises();

    const labels = wrapper.findAll("button").map((button) => button.text());
    expect(labels).not.toContain("Suspend");
    expect(labels).not.toContain("Disable");
    expect(labels).not.toContain("Revoke");
    expect(labels).toContain("Revoke sessions");
  });

  it("creates an account with a governed role and audit reason", async () => {
    const created = account({
      id: "account-new",
      username: "new-engineer",
      display_name: "New Engineer",
      roles: ["viewer"],
      permissions: ["public-demo:read"],
    });
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/admin/users") && (!init?.method || init.method === "GET")) {
        return response({ results: [account()] });
      }
      if (url.endsWith("/admin/identity-catalog")) return response(catalog);
      if (url.endsWith("/admin/users") && init?.method === "POST") {
        expect(new Headers(init.headers).get("X-CSRFToken")).toBe("identity-csrf");
        expect(JSON.parse(String(init.body))).toMatchObject({
          username: "new-engineer",
          role_code: "viewer",
          scope_code: "public-demo",
          reason: "New Demo operator",
        });
        return response(created, 201);
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    const wrapper = mount(IdentityManagementWorkspace, { props: { currentAccount: account() } });
    await flushPromises();

    await wrapper.get(".identity-heading button").trigger("click");
    const form = wrapper.get(".identity-create-form");
    const inputs = form.findAll("input");
    await inputs[0].setValue("new-engineer");
    await inputs[1].setValue("New Engineer");
    await inputs[2].setValue("new@example.test");
    await inputs[3].setValue("Strong-Demo-Password-2026!");
    await inputs[4].setValue("New Demo operator");
    await form.trigger("submit");
    await flushPromises();

    expect(wrapper.text()).toContain("Account created successfully.");
    expect(wrapper.text()).toContain("New Engineer");
  });

  it("requires a reason and confirmation before suspending an account", async () => {
    const target = account({
      id: "account-target",
      username: "target",
      display_name: "Target Engineer",
      roles: ["viewer"],
      permissions: ["public-demo:read"],
      role_assignments: [],
    });
    const suspended = { ...target, status: "suspended" as const, row_version: 2 };
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/admin/users") && !init?.method) return response({ results: [target] });
      if (url.endsWith("/admin/identity-catalog")) return response(catalog);
      if (url.endsWith(`/admin/users/${target.id}/suspend`)) {
        expect(JSON.parse(String(init?.body))).toEqual({ reason: "Pending access review" });
        return response({ account: suspended, revoked_sessions: 2 });
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    const wrapper = mount(IdentityManagementWorkspace, { props: { currentAccount: account() } });
    await flushPromises();

    const suspendButton = wrapper.findAll(".identity-action-buttons button").find((button) =>
      button.text().includes("Suspend"),
    );
    expect(suspendButton?.attributes("disabled")).toBeDefined();
    await wrapper.get(".identity-action-section textarea").setValue("Pending access review");
    await suspendButton?.trigger("click");
    await flushPromises();

    expect(window.confirm).toHaveBeenCalledOnce();
    expect(wrapper.text()).toContain("2 sessions revoked");
    expect(wrapper.text()).toContain("suspended");
  });
});
