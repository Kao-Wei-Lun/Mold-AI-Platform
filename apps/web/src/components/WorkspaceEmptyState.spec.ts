import { mount } from "@vue/test-utils";

import WorkspaceEmptyState from "./WorkspaceEmptyState.vue";

describe("WorkspaceEmptyState", () => {
  it("explains the next step and emits one action", async () => {
    const wrapper = mount(WorkspaceEmptyState, {
      props: {
        eyebrow: "CAD required",
        title: "Prepare geometry first",
        message: "Open CAD and return after processing.",
        actionLabel: "Open CAD",
      },
    });

    expect(wrapper.text()).toContain("Prepare geometry first");
    await wrapper.get("button").trigger("click");
    expect(wrapper.emitted("action")).toHaveLength(1);
  });
});
