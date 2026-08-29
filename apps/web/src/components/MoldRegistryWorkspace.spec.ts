import { flushPromises, mount } from "@vue/test-utils";

import type { LocalAccount } from "../api/identity";
import { emptyMasterDataOptions } from "../api/masterData";
import * as registryApi from "../api/registry";
import { setLocale } from "../i18n";
import MoldRegistryWorkspace from "./MoldRegistryWorkspace.vue";

const account: LocalAccount = {
  id: "engineer-1",
  username: "engineer",
  email: "engineer@example.test",
  display_name: "Mold Engineer",
  status: "active",
  locale: "zh-TW",
  timezone: "Asia/Taipei",
  row_version: 1,
  roles: ["mold_engineer"],
  permissions: ["public-demo:read", "registry:read", "registry:manage"],
  data_scopes: ["public-demo"],
  role_assignments: [],
  last_login_at: null,
  created_at: "2026-08-29T00:00:00Z",
};

const project: registryApi.RegistryProject = {
  id: "project-1",
  code: "DEMO-CAD",
  name: "Curated CAD Demonstration",
  description: "Synthetic hierarchy",
  scope: "public-demo",
  classification: "public_demo",
  status: "active",
  row_version: 1,
  part_count: 1,
  mold_count: 16,
};

describe("MoldRegistryWorkspace", () => {
  beforeEach(() => {
    setLocale("zh-TW");
    vi.spyOn(registryApi, "fetchRegistry").mockResolvedValue({
      projects: [project],
      parts: [],
      molds: [],
      revisions: [],
    });
  });

  afterEach(() => vi.restoreAllMocks());

  it("renders the governed hierarchy summary", async () => {
    const wrapper = mount(MoldRegistryWorkspace, {
      props: { currentAccount: account, masterDataOptions: emptyMasterDataOptions() },
    });
    await flushPromises();

    expect(wrapper.text()).toContain("模具台帳與版本生命週期");
    expect(wrapper.text()).toContain("DEMO-CAD");
    expect(wrapper.text()).toContain("16");
  });

  it("creates a project with an audit reason", async () => {
    const createSpy = vi.spyOn(registryApi, "createProject").mockResolvedValue({
      ...project,
      id: "project-2",
      code: "NEW-PROJECT",
      name: "New project",
    });
    const wrapper = mount(MoldRegistryWorkspace, {
      props: { currentAccount: account, masterDataOptions: emptyMasterDataOptions() },
    });
    await flushPromises();

    const inputs = wrapper.findAll(".registry-editor input");
    await inputs[0].setValue("NEW-PROJECT");
    await inputs[1].setValue("New project");
    await inputs[2].setValue("Approved creation");
    await wrapper.get(".registry-editor").trigger("submit");
    await flushPromises();

    expect(createSpy).toHaveBeenCalledWith(expect.objectContaining({
      code: "NEW-PROJECT",
      name: "New project",
      reason: "Approved creation",
    }));
  });
});
