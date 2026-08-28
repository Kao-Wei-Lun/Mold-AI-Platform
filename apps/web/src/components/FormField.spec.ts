import { mount } from "@vue/test-utils";

import FormField from "./FormField.vue";

describe("FormField", () => {
  it("links helper and error text to a required control", () => {
    const wrapper = mount(FormField, {
      props: {
        label: "Material",
        required: true,
        helper: "Select an approved material.",
        error: "Material is required.",
      },
      slots: {
        default:
          '<template #default="{ fieldId, describedBy, invalid }"><select :id="fieldId" :aria-describedby="describedBy" :aria-invalid="invalid"><option>ABS</option></select></template>',
      },
    });

    const select = wrapper.get("select");
    expect(wrapper.get(".required-mark").text()).toBe("*");
    expect(wrapper.get(".field-hint").text()).toContain("approved material");
    expect(wrapper.get('[role="alert"]').text()).toContain("required");
    expect(select.attributes("aria-invalid")).toBe("true");
    expect(select.attributes("aria-describedby")).toContain("helper");
    expect(select.attributes("aria-describedby")).toContain("error");
  });

  it("omits optional descriptions when they are not supplied", () => {
    const wrapper = mount(FormField, {
      props: { label: "Optional note" },
      slots: { default: "<input />" },
    });

    expect(wrapper.find(".required-mark").exists()).toBe(false);
    expect(wrapper.find(".field-hint").exists()).toBe(false);
    expect(wrapper.find(".field-error").exists()).toBe(false);
  });
});
