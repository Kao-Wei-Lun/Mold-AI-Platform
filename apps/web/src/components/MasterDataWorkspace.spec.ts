import { flushPromises, mount } from "@vue/test-utils";

import * as masterDataApi from "../api/masterData";
import type { LocalAccount } from "../api/identity";
import { setLocale } from "../i18n";
import MasterDataWorkspace from "./MasterDataWorkspace.vue";

const account: LocalAccount = {
  id: "steward-1",
  username: "steward",
  email: "steward@example.test",
  display_name: "Data Steward",
  status: "active",
  locale: "zh-TW",
  timezone: "Asia/Taipei",
  row_version: 1,
  roles: ["data_steward"],
  permissions: ["public-demo:read", "public-demo:write", "master-data:read", "master-data:manage"],
  data_scopes: ["public-demo"],
  role_assignments: [],
  last_login_at: null,
  created_at: "2026-08-29T00:00:00Z",
};

const dataset: masterDataApi.MasterDataItem = {
  id: "dataset-1",
  kind: "dataset",
  code: "public-demo-v1",
  name_en: "Public Demo",
  name_zh_tw: "公開 Demo",
  description_en: "Authorized synthetic data",
  description_zh_tw: "已授權合成資料",
  status: "active",
  sort_order: 10,
  attributes: {},
  aliases: [],
  source_system: "public_demo_seed",
  source_refs: [],
  scope: "public-demo",
  classification: "public_demo",
  effective_from: null,
  effective_to: null,
  row_version: 1,
  created_at: "2026-08-29T00:00:00Z",
  updated_at: "2026-08-29T00:00:00Z",
  references: { artifacts: 16 },
};

describe("MasterDataWorkspace", () => {
  beforeEach(() => {
    setLocale("zh-TW");
    vi.spyOn(masterDataApi, "fetchMasterData").mockResolvedValue({
      results: [dataset],
      pagination: { page: 1, page_size: 25, total: 1 },
    });
    vi.stubGlobal("confirm", vi.fn(() => true));
  });

  afterEach(() => vi.restoreAllMocks());

  it("renders bilingual governed data, immutable code and reference summary", async () => {
    const wrapper = mount(MasterDataWorkspace, { props: { currentAccount: account } });
    await flushPromises();

    expect(wrapper.text()).toContain("公開 Demo");
    expect(wrapper.text()).toContain("artifacts: 16");
    expect(wrapper.get('input[pattern="[A-Za-z0-9][A-Za-z0-9._/-]*"]').attributes("disabled")).toBeDefined();
    expect(wrapper.text()).toContain("建立項目");
  });

  it("creates a new canonical code through the managed form", async () => {
    const created = { ...dataset, id: "dataset-2", code: "supplier-demo-v1", name_en: "Supplier Demo", name_zh_tw: "供應商 Demo" };
    const createSpy = vi.spyOn(masterDataApi, "createMasterData").mockResolvedValue(created);
    const wrapper = mount(MasterDataWorkspace, { props: { currentAccount: account } });
    await flushPromises();

    await wrapper.get(".section-heading button").trigger("click");
    const inputs = wrapper.findAll(".master-data-editor input");
    await inputs[0].setValue("supplier-demo-v1");
    await inputs[2].setValue("Supplier Demo");
    await inputs[3].setValue("供應商 Demo");
    await wrapper.get('input[maxlength="512"]').setValue("Add approved supplier dataset");
    await wrapper.get(".master-data-editor form, .master-data-editor").trigger("submit");
    await flushPromises();

    expect(createSpy).toHaveBeenCalledWith(expect.objectContaining({
      kind: "dataset",
      code: "supplier-demo-v1",
      name_en: "Supplier Demo",
      name_zh_tw: "供應商 Demo",
      reason: "Add approved supplier dataset",
    }));
  });
});
