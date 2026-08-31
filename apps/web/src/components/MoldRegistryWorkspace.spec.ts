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

const revision: registryApi.RegistryRevision = {
  id: "revision-1",
  mold_id: "mold-1",
  mold_code: "DEMO-MOLD-001",
  revision_code: "A",
  status: "released",
  change_summary: "Initial release",
  source_system: "platform_demo",
  source_revision_id: null,
  row_version: 1,
  released_at: "2026-08-29T00:00:00Z",
  artifact_count: 2,
};

const mold: registryApi.RegistryMold = {
  id: "mold-1",
  project_id: project.id,
  project_code: project.code,
  product_part_id: null,
  part_number: null,
  mold_code: "DEMO-MOLD-001",
  name: "Demo housing mold",
  mold_type: "injection",
  cavity_count: 2,
  status: "active",
  row_version: 1,
  revision_count: 1,
  current_revision_id: revision.id,
  current_revision_code: revision.revision_code,
  artifact_count: 2,
  revisions: [revision],
  updated_at: "2026-08-30T00:00:00Z",
};

const page = { number: 1, size: 25, total: 1, sort: "-updated_at", has_next: false };

function mountWorkspace(currentAccount: LocalAccount = account) {
  return mount(MoldRegistryWorkspace, {
    props: { currentAccount, masterDataOptions: emptyMasterDataOptions() },
  });
}

describe("MoldRegistryWorkspace", () => {
  beforeEach(() => {
    setLocale("zh-TW");
    window.history.replaceState(null, "", "/governance/mold-registry");
    vi.spyOn(registryApi, "fetchRegistryOverview").mockResolvedValue({
      schema_version: "1.0",
      counts: {
        active_projects: 1,
        active_molds: 16,
        released_revisions: 1,
        draft_revisions: 0,
        released_without_cad: 0,
        pending_mapping: 1,
      },
    });
    vi.spyOn(registryApi, "fetchRegistryProjects").mockResolvedValue({ schema_version: "1.0", items: [project], page });
    vi.spyOn(registryApi, "fetchRegistryParts").mockResolvedValue({ schema_version: "1.0", items: [], page: { ...page, total: 0 } });
    vi.spyOn(registryApi, "fetchRegistryMolds").mockResolvedValue({ schema_version: "1.0", items: [mold], page });
  });

  afterEach(() => vi.restoreAllMocks());

  it("renders a mold-first governed registry with overview and table", async () => {
    const wrapper = mountWorkspace();
    await flushPromises();

    expect(wrapper.get("#registry-title").text()).toBe("模具台帳");
    expect(wrapper.text()).toContain("管理模具身份、版本與完整工程履歷");
    expect(wrapper.text()).toContain("DEMO-MOLD-001");
    expect(wrapper.text()).toContain("16");
    expect(wrapper.find(".registry-table").exists()).toBe(true);
  });

  it("sends search and hierarchy state to the server and URL", async () => {
    const fetchMolds = vi.mocked(registryApi.fetchRegistryMolds);
    const wrapper = mountWorkspace();
    await flushPromises();

    await wrapper.get("#registry-search-input").setValue("DEMO-MOLD");
    await wrapper.get(".registry-search").trigger("submit");
    await flushPromises();

    expect(fetchMolds).toHaveBeenLastCalledWith(expect.objectContaining({ q: "DEMO-MOLD", view: "table" }));
    expect(window.location.search).toContain("q=DEMO-MOLD");

    const hierarchy = wrapper.findAll(".registry-view-switch button").find((button) => button.text() === "階層");
    await hierarchy?.trigger("click");
    await flushPromises();

    expect(fetchMolds).toHaveBeenLastCalledWith(expect.objectContaining({ q: "DEMO-MOLD", view: "tree" }));
    expect(window.location.search).toContain("view=tree");
    expect(wrapper.text()).toContain("2 CAD 工件");
  });

  it("opens the controlled drawer and creates a project with an audit reason", async () => {
    const createSpy = vi.spyOn(registryApi, "createProject").mockResolvedValue({
      ...project,
      id: "project-2",
      code: "NEW-PROJECT",
      name: "New project",
    });
    const wrapper = mountWorkspace();
    await flushPromises();

    const addButton = wrapper.findAll("button").find((button) => button.text().includes("新增資料"));
    await addButton?.trigger("click");
    const projectTab = wrapper.findAll(".registry-tabs button").find((button) => button.text() === "專案");
    await projectTab?.trigger("click");

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
    expect(wrapper.find(".registry-drawer-backdrop").exists()).toBe(false);
  });

  it("keeps discovery read-only when the account lacks registry manage permission", async () => {
    const wrapper = mountWorkspace({ ...account, permissions: ["registry:read"] });
    await flushPromises();

    expect(wrapper.text()).toContain("DEMO-MOLD-001");
    expect(wrapper.find(".registry-drawer-backdrop").exists()).toBe(false);
    expect(wrapper.findAll("button").some((button) => button.text().includes("新增資料"))).toBe(false);
  });
});
