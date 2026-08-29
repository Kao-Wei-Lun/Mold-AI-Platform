import { flushPromises, mount } from "@vue/test-utils";

import { setLocale } from "../i18n";
import DetailDrawer from "./DetailDrawer.vue";
import HistoryDataCenter from "./HistoryDataCenter.vue";

describe("HistoryDataCenter", () => {
  beforeEach(() => setLocale("en"));
  afterEach(() => vi.unstubAllGlobals());

  it("shows all governed history domains and emits stable routes", async () => {
    const wrapper = mount(HistoryDataCenter, { props: { path: "/data/overview" } });

    expect(wrapper.text()).toContain("Find complete engineering evidence");
    expect(wrapper.text()).toContain("Trial & process");
    expect(wrapper.text()).toContain("Audit & lineage");

    await wrapper.findAll(".history-domain-card-actions button")[0].trigger("click");
    expect(wrapper.emitted("navigate")?.[0]).toEqual(["/data/molds"]);
  });

  it("keeps a domain route selected and renders its history list", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ items: [] }),
    } as Response)));
    const wrapper = mount(HistoryDataCenter, { props: { path: "/data/trials" } });
    await flushPromises();

    expect(wrapper.find(".history-list-heading").text()).toContain("Trial & process");
    expect(wrapper.find(".history-domain-nav button.active").text()).toBe("Trial & process");
    expect(wrapper.find(".data-table-empty").text()).toContain("No trial history");
  });

  it("opens and closes the accessible quick detail drawer", async () => {
    const wrapper = mount(HistoryDataCenter, { props: { path: "/data/overview" }, attachTo: document.body });

    await wrapper.findAll(".history-domain-card-actions button")[1].trigger("click");
    expect(document.body.querySelector('[role="dialog"]')).not.toBeNull();

    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    await wrapper.vm.$nextTick();
    expect(document.body.querySelector('[role="dialog"]')).toBeNull();
    wrapper.unmount();
  });
});

describe("DetailDrawer", () => {
  it("emits close from the close button", async () => {
    const wrapper = mount(DetailDrawer, { props: { open: true, title: "Trial detail" }, attachTo: document.body });
    const close = document.body.querySelector<HTMLButtonElement>('.detail-drawer .icon-button');
    await close?.click();
    expect(wrapper.emitted("close")).toHaveLength(1);
    wrapper.unmount();
  });
});
