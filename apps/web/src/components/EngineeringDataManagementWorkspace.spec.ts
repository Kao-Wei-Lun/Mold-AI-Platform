import { flushPromises, mount } from "@vue/test-utils";

import * as engineeringApi from "../api/engineeringData";
import type { LocalAccount } from "../api/identity";
import { emptyMasterDataOptions } from "../api/masterData";
import * as registryApi from "../api/registry";
import { setLocale } from "../i18n";
import EngineeringDataManagementWorkspace from "./EngineeringDataManagementWorkspace.vue";

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
  permissions: ["engineering-data:read", "engineering-data:manage", "registry:read"],
  data_scopes: ["public-demo"],
  role_assignments: [],
  last_login_at: null,
  created_at: "2026-08-29T00:00:00Z",
};

const options = emptyMasterDataOptions();
options.machine = [
  { id: "machine-1", code: "IM-120T", name_en: "120T", name_zh_tw: "120T 射出機", attributes: {}, row_version: 1 },
];
options.material = [
  { id: "material-1", code: "ABS-GENERAL", name_en: "ABS", name_zh_tw: "通用 ABS", attributes: {}, row_version: 1 },
];
options.product_type = [
  { id: "product-1", code: "housing", name_en: "Housing", name_zh_tw: "外殼", attributes: {}, row_version: 1 },
];

describe("EngineeringDataManagementWorkspace", () => {
  beforeEach(() => {
    setLocale("zh-TW");
    vi.spyOn(engineeringApi, "fetchEngineeringData").mockResolvedValue({
      trials: [
        {
          trial_case_id: "trial-1",
          case_code: "TRIAL-001",
          mold_revision_ref: "MOLD-001@A",
          machine_code: "IM-120T",
          material_code: "ABS-GENERAL",
          product_type: "housing",
          purpose: "Qualification",
          outcome: "pass",
          started_at: "2026-08-29T00:00:00Z",
          lifecycle_status: "closed",
          row_version: 1,
          corrections: [],
          provenance: { source_record_id: "fixture:1" },
        },
      ],
      studies: [],
      profiles: [],
    });
    vi.spyOn(registryApi, "fetchRegistry").mockResolvedValue({
      projects: [],
      parts: [],
      molds: [],
      revisions: [
        {
          id: "revision-1",
          mold_id: "mold-1",
          mold_code: "MOLD-001",
          revision_code: "A",
          status: "released",
          change_summary: "Initial",
          source_system: "platform_demo",
          source_revision_id: null,
          row_version: 1,
          released_at: "2026-08-29T00:00:00Z",
          artifact_count: 1,
        },
      ],
    });
  });

  afterEach(() => vi.restoreAllMocks());

  it("renders lifecycle counts and governed trial evidence", async () => {
    const wrapper = mount(EngineeringDataManagementWorkspace, {
      props: { currentAccount: account, masterDataOptions: options },
    });
    await flushPromises();

    expect(wrapper.text()).toContain("試模、CAE 與 HMI 資料生命週期");
    expect(wrapper.text()).toContain("TRIAL-001");
    expect(wrapper.text()).toContain("MOLD-001@A");
  });

  it("submits canonical selections with an audit reason", async () => {
    const createSpy = vi.spyOn(engineeringApi, "createManagedTrial").mockResolvedValue(
      {} as engineeringApi.ManagedTrial,
    );
    const wrapper = mount(EngineeringDataManagementWorkspace, {
      props: { currentAccount: account, masterDataOptions: options },
    });
    await flushPromises();

    const form = wrapper.get(".registry-editor");
    const inputs = form.findAll("input");
    await inputs[0].setValue("TRIAL-NEW");
    const selects = form.findAll("select");
    await selects[1].setValue("IM-120T");
    await selects[2].setValue("ABS-GENERAL");
    await selects[3].setValue("housing");
    await inputs[1].setValue("New qualification");
    await inputs[3].setValue("Approved manual entry");
    await form.trigger("submit");
    await flushPromises();

    expect(createSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        case_code: "TRIAL-NEW",
        machine_code: "IM-120T",
        material_code: "ABS-GENERAL",
        product_type: "housing",
        reason: "Approved manual entry",
      }),
    );
  });
});
