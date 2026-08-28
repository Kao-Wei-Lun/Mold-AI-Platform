import { mount } from "@vue/test-utils";

import { pushToast, resetToasts } from "../toast";
import ToastRegion from "./ToastRegion.vue";

describe("ToastRegion", () => {
  beforeEach(resetToasts);
  afterEach(resetToasts);

  it("announces success and lets the user dismiss it", async () => {
    pushToast("CAD processing started.", "success", 0);
    const wrapper = mount(ToastRegion);

    expect(wrapper.get(".toast-message").attributes("role")).toBe("status");
    expect(wrapper.text()).toContain("CAD processing started.");
    await wrapper.get(".toast-message button").trigger("click");
    expect(wrapper.find(".toast-message").exists()).toBe(false);
  });

  it("uses an alert for an error", () => {
    pushToast("Unable to complete the request.", "error", 0);
    const wrapper = mount(ToastRegion);

    expect(wrapper.get(".toast-message").attributes("role")).toBe("alert");
  });
});
