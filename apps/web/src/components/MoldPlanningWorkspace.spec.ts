import { mount } from "@vue/test-utils";

import MoldPlanningWorkspace from "./MoldPlanningWorkspace.vue";

describe("MoldPlanningWorkspace", () => {
  it("presents a five-step context-driven planning journey", () => {
    const wrapper = mount(MoldPlanningWorkspace);

    expect(wrapper.get("h2").text()).toContain("Plan the mold");
    expect(wrapper.findAll(".planning-step-list li")).toHaveLength(5);
    expect(wrapper.text()).toContain("No mold plans yet");
  });

  it("keeps rule governance in the dedicated governance route", async () => {
    const wrapper = mount(MoldPlanningWorkspace);
    await wrapper.get(".planning-intro button").trigger("click");

    expect(wrapper.emitted("navigate")?.[0]).toEqual(["/governance/rules"]);
  });
});
