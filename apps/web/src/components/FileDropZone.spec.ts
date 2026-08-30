import { mount } from "@vue/test-utils";

import FileDropZone from "./FileDropZone.vue";

describe("FileDropZone", () => {
  it("supports native selection and exposes the configured accessible input", async () => {
    const wrapper = mount(FileDropZone, {
      props: { id: "cad-file", accept: ".step,.stl", prompt: "Drop CAD here" },
    });
    const file = new File(["solid"], "part.stl", { type: "model/stl" });
    const input = wrapper.get('input[type="file"]');
    Object.defineProperty(input.element, "files", { value: [file] });

    await input.trigger("change");

    expect(input.attributes("id")).toBe("cad-file");
    expect(input.attributes("accept")).toBe(".step,.stl");
    expect(wrapper.emitted("select")?.[0]).toEqual([file]);
  });

  it("shows drag feedback and emits the first dropped file", async () => {
    const wrapper = mount(FileDropZone, {
      props: { id: "knowledge-file", accept: ".pdf", prompt: "Drop document here" },
    });
    const file = new File(["pdf"], "guide.pdf", { type: "application/pdf" });

    await wrapper.get(".file-drop-zone").trigger("dragenter");
    expect(wrapper.get(".file-drop-zone").classes()).toContain("dragging");
    await wrapper.get(".file-drop-zone").trigger("drop", {
      dataTransfer: { files: [file] },
    });

    expect(wrapper.emitted("select")?.[0]).toEqual([file]);
    expect(wrapper.get(".file-drop-zone").classes()).not.toContain("dragging");
  });

  it("renders the selected file summary", () => {
    const file = new File(["screen"], "screen.png", { type: "image/png" });
    const wrapper = mount(FileDropZone, {
      props: { id: "hmi-file", accept: "image/png", prompt: "Drop image here", selectedFile: file },
    });

    expect(wrapper.text()).toContain("screen.png");
    expect(wrapper.text()).toContain("Ready to upload");
    expect(wrapper.get('input[type="file"]').attributes("required")).toBeUndefined();
  });
});
