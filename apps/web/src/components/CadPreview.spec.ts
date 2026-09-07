import { flushPromises, mount } from "@vue/test-utils";

import CadPreview from "./CadPreview.vue";

const rendererSpies = vi.hoisted(() => ({
  dispose: vi.fn(),
  setAnimationLoop: vi.fn(),
  render: vi.fn(),
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
    render(scene: unknown): void { rendererSpies.render(scene); }
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
    parse(payload: ArrayBuffer): InstanceType<typeof BoxGeometry> {
      const geometry = new BoxGeometry(2, 1, 0.5);
      geometry.userData.sourceMarker = new Uint8Array(payload)[0];
      return geometry;
    }
  }
  return { STLLoader };
});

describe("CadPreview", () => {
  beforeEach(() => {
    rendererSpies.dispose.mockClear();
    rendererSpies.setAnimationLoop.mockClear();
    rendererSpies.render.mockClear();
    controlsSpies.dispose.mockClear();
    controlsSpies.update.mockClear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  function deferred<T>() {
    let resolve!: (value: T) => void;
    let reject!: (reason: unknown) => void;
    const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
    return { promise, resolve, reject };
  }

  function response(marker: number) {
    return { ok: true, status: 200, arrayBuffer: async () => new Uint8Array([marker]).buffer };
  }

  function currentMeshes() {
    const animate = rendererSpies.setAnimationLoop.mock.calls.find(([value]) => typeof value === "function")![0];
    animate();
    const scene = rendererSpies.render.mock.calls.at(-1)![0] as import("three").Scene;
    return scene.children.filter((object) => (object as import("three").Mesh).isMesh) as import("three").Mesh[];
  }

  it("ignores an older model arriving after the selected model even if abort is ignored", async () => {
    const old = deferred<ReturnType<typeof response>>();
    const fetchMock = vi.fn().mockReturnValueOnce(old.promise).mockResolvedValueOnce(response(2));
    vi.stubGlobal("fetch", fetchMock);
    const wrapper = mount(CadPreview, { props: { source: "/a.stl" } });
    await wrapper.setProps({ source: "/b.stl" });
    await flushPromises();
    expect(currentMeshes().map((item) => item.geometry.userData.sourceMarker)).toEqual([2]);
    old.resolve(response(1));
    await flushPromises();
    expect(currentMeshes().map((item) => item.geometry.userData.sourceMarker)).toEqual([2]);
    expect((fetchMock.mock.calls[0][1].signal as AbortSignal).aborted).toBe(true);
    wrapper.unmount();
  });

  it("ignores an old body finishing late and old errors while a new preview is active", async () => {
    const oldBody = deferred<ArrayBuffer>();
    vi.stubGlobal("fetch", vi.fn()
      .mockResolvedValueOnce({ ok: true, status: 200, arrayBuffer: () => oldBody.promise })
      .mockResolvedValueOnce(response(2)));
    const wrapper = mount(CadPreview, { props: { source: "/a.stl" } });
    await flushPromises();
    await wrapper.setProps({ source: "/b.stl" });
    await flushPromises();
    oldBody.reject(new Error("late network failure"));
    await flushPromises();
    expect(wrapper.find('[role="alert"]').exists()).toBe(false);
    expect(currentMeshes().map((item) => item.geometry.userData.sourceMarker)).toEqual([2]);
    wrapper.unmount();
  });

  it("keeps only the newest request across A to B to A and delayed body completion", async () => {
    const oldBody = deferred<ArrayBuffer>();
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, status: 200, arrayBuffer: () => oldBody.promise })
      .mockResolvedValueOnce(response(2))
      .mockResolvedValueOnce(response(3));
    vi.stubGlobal("fetch", fetchMock);
    const wrapper = mount(CadPreview, { props: { source: "/a.stl" } });
    await flushPromises();
    await wrapper.setProps({ source: "/b.stl" });
    await flushPromises();
    await wrapper.setProps({ source: "/a.stl" });
    await flushPromises();
    oldBody.resolve(new Uint8Array([1]).buffer);
    await flushPromises();
    expect(currentMeshes().map((item) => item.geometry.userData.sourceMarker)).toEqual([3]);
    wrapper.unmount();
  });

  it("disposes the replaced model and does not refetch when only accent changes", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(response(1)).mockResolvedValueOnce(response(2));
    vi.stubGlobal("fetch", fetchMock);
    const wrapper = mount(CadPreview, { props: { source: "/a.stl" } });
    await flushPromises();
    const old = currentMeshes()[0];
    const disposeGeometry = vi.spyOn(old.geometry, "dispose");
    const disposeMaterial = vi.spyOn(old.material as import("three").MeshStandardMaterial, "dispose");
    await wrapper.findAll(".viewer-toolbar button")[3].trigger("click");
    await wrapper.setProps({ accent: "warning" });
    await flushPromises();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await wrapper.setProps({ source: "/b.stl" });
    await flushPromises();
    expect(disposeGeometry).toHaveBeenCalledOnce();
    expect(disposeMaterial).toHaveBeenCalledOnce();
    const material = currentMeshes()[0].material as import("three").MeshStandardMaterial;
    expect(material.transparent).toBe(true);
    expect(material.color.getHex()).toBe(0xd95b3d);
    wrapper.unmount();
  });

  it("cannot add a model after the viewer has unmounted", async () => {
    const late = deferred<ReturnType<typeof response>>();
    const fetchMock = vi.fn().mockReturnValue(late.promise);
    vi.stubGlobal("fetch", fetchMock);
    const wrapper = mount(CadPreview, { props: { source: "/a.stl" } });
    const sceneMeshes = currentMeshes();
    expect(sceneMeshes).toHaveLength(0);
    wrapper.unmount();
    late.resolve(response(1));
    await flushPromises();
    const scene = rendererSpies.render.mock.calls.at(-1)![0] as import("three").Scene;
    expect(scene.children.some((item) => (item as import("three").Mesh).isMesh)).toBe(false);
    expect((fetchMock.mock.calls[0][1].signal as AbortSignal).aborted).toBe(true);
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
