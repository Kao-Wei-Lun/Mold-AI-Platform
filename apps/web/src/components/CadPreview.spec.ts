import { flushPromises, mount } from "@vue/test-utils";

import CadPreview from "./CadPreview.vue";

const rendererSpies = vi.hoisted(() => ({
  dispose: vi.fn(),
  setAnimationLoop: vi.fn(),
}));
const controlsSpies = vi.hoisted(() => ({
  dispose: vi.fn(),
  update: vi.fn(),
}));

vi.mock("three", async (importOriginal) => {
  const actual = await importOriginal<typeof import("three")>();
  class WebGLRenderer {
    setPixelRatio(): void {}
    setSize(): void {}
    render(): void {}
    setAnimationLoop(callback: unknown): void {
      rendererSpies.setAnimationLoop(callback);
    }
    dispose(): void {
      rendererSpies.dispose();
    }
  }
  return { ...actual, WebGLRenderer };
});

vi.mock("three/addons/controls/OrbitControls.js", async () => {
  const { Vector3 } = await vi.importActual<typeof import("three")>("three");
  class OrbitControls {
    target = new Vector3();
    enableDamping = false;
    enableRotate = false;
    enableZoom = false;
    enablePan = false;
    screenSpacePanning = false;
    minDistance = 0;
    maxDistance = Number.POSITIVE_INFINITY;
    update(): void {
      controlsSpies.update();
    }
    dispose(): void {
      controlsSpies.dispose();
    }
  }
  return { OrbitControls };
});

vi.mock("three/addons/loaders/STLLoader.js", async () => {
  const { BoxGeometry } = await vi.importActual<typeof import("three")>("three");
  class STLLoader {
    parse(): InstanceType<typeof BoxGeometry> {
      return new BoxGeometry(2, 1, 0.5);
    }
  }
  return { STLLoader };
});

describe("CadPreview", () => {
  beforeEach(() => {
    rendererSpies.dispose.mockClear();
    rendererSpies.setAnimationLoop.mockClear();
    controlsSpies.dispose.mockClear();
    controlsSpies.update.mockClear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("downloads STL through the authenticated wildcard media path and exposes viewer controls", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      arrayBuffer: async () => new Uint8Array([1, 2, 3]).buffer,
    });
    vi.stubGlobal("fetch", fetchMock);

    const wrapper = mount(CadPreview, { props: { source: "/preview.stl" } });
    await flushPromises();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const request = fetchMock.mock.calls[0][1] as RequestInit;
    expect(new Headers(request.headers).get("Accept")).toBe("*/*");
    expect(wrapper.text()).toContain("Drag to rotate");
    expect(wrapper.get('button[aria-label="Zoom in"]')).toBeTruthy();
    expect(wrapper.get('button[aria-label="Zoom out"]')).toBeTruthy();
    expect(wrapper.text()).toContain("Reset view");

    const updatesBeforeInteraction = controlsSpies.update.mock.calls.length;
    await wrapper.get('button[aria-label="Zoom in"]').trigger("click");
    await wrapper.get('button[aria-label="Zoom out"]').trigger("click");
    await wrapper.findAll(".viewer-toolbar button")[1].trigger("click");
    expect(controlsSpies.update.mock.calls.length).toBeGreaterThan(updatesBeforeInteraction);

    wrapper.unmount();
    expect(controlsSpies.dispose).toHaveBeenCalledOnce();
    expect(rendererSpies.dispose).toHaveBeenCalledOnce();
  });

  it("shows the HTTP failure and lets the user retry the preview", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: false, status: 406, arrayBuffer: vi.fn() })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        arrayBuffer: async () => new Uint8Array([1]).buffer,
      });
    vi.stubGlobal("fetch", fetchMock);

    const wrapper = mount(CadPreview, { props: { source: "/preview.stl" } });
    await flushPromises();

    expect(wrapper.get('[role="alert"]').text()).toContain("HTTP 406");
    await wrapper.get('[role="alert"] button').trigger("click");
    await flushPromises();

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(wrapper.find('[role="alert"]').exists()).toBe(false);
  });
});
