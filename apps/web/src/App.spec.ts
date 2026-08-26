import { flushPromises, mount } from "@vue/test-utils";

import App from "./App.vue";

describe("App", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows dependency status returned by the backend", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          status: "ok",
          services: [
            { name: "database", status: "ok", detail: null },
            { name: "redis", status: "ok", detail: null },
            { name: "qdrant", status: "ok", detail: null },
          ],
        }),
      }),
    );

    const wrapper = mount(App);
    await flushPromises();

    expect(wrapper.text()).toContain("Platform services");
    expect(wrapper.text()).toContain("database");
    expect(wrapper.findAll(".status-pill")).toHaveLength(3);
  });

  it("shows an actionable error when the API cannot be reached", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network unavailable")));

    const wrapper = mount(App);
    await flushPromises();

    expect(wrapper.get('[role="alert"]').text()).toContain("network unavailable");
  });
});
