<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import {
  AmbientLight,
  Box3,
  Color,
  DirectionalLight,
  Mesh,
  MeshStandardMaterial,
  PerspectiveCamera,
  Scene,
  Vector3,
  WebGLRenderer,
} from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { STLLoader } from "three/addons/loaders/STLLoader.js";

import { apiFetch } from "../api/client";
import { useI18n } from "../i18n";

const { t } = useI18n();

const props = defineProps<{ source: string; accent?: "default" | "warning" | "pass" }>();

const canvas = ref<HTMLCanvasElement | null>(null);
const loading = ref(true);
const error = ref<string | null>(null);
const errorDetail = ref<string | null>(null);
const transparent = ref(false);
const view = ref<"iso" | "front" | "top">("iso");

let renderer: WebGLRenderer | null = null;
let scene: Scene | null = null;
let camera: PerspectiveCamera | null = null;
let controls: OrbitControls | null = null;
let mesh: Mesh | null = null;
let modelCenter = new Vector3();
let modelDistance = 10;

const transparencyLabel = computed(() => (transparent.value ? t("Solid") : t("Transparent")));

function resize(): void {
  if (!canvas.value || !renderer || !camera) return;
  const width = canvas.value.clientWidth || 640;
  const height = canvas.value.clientHeight || 420;
  renderer.setSize(width, height, false);
  camera.aspect = width / height;
  camera.updateProjectionMatrix();
}

function applyView(): void {
  if (!camera || !controls) return;
  const offsets = {
    iso: new Vector3(1, 1, 1),
    front: new Vector3(0, -1, 0.15),
    top: new Vector3(0, 0.05, 1),
  };
  camera.position.copy(modelCenter).add(offsets[view.value].normalize().multiplyScalar(modelDistance));
  controls.target.copy(modelCenter);
  controls.update();
}

function selectView(nextView: "iso" | "front" | "top"): void {
  view.value = nextView;
  applyView();
}

function zoomBy(scale: number): void {
  if (!camera || !controls) return;
  const offset = camera.position.clone().sub(controls.target);
  const currentDistance = Math.max(offset.length(), 0.001);
  const nextDistance = Math.min(
    controls.maxDistance,
    Math.max(controls.minDistance, currentDistance * scale),
  );
  camera.position.copy(controls.target).add(offset.setLength(nextDistance));
  controls.update();
}

function toggleTransparency(): void {
  transparent.value = !transparent.value;
  const material = mesh?.material;
  if (material instanceof MeshStandardMaterial) {
    material.transparent = transparent.value;
    material.opacity = transparent.value ? 0.42 : 1;
    material.depthWrite = !transparent.value;
    material.needsUpdate = true;
  }
}

async function loadModel(source: string): Promise<void> {
  if (!scene || !camera || !controls) return;
  loading.value = true;
  error.value = null;
  errorDetail.value = null;
  if (mesh) {
    scene.remove(mesh);
    mesh.geometry.dispose();
    if (mesh.material instanceof MeshStandardMaterial) mesh.material.dispose();
  }

  try {
    const response = await apiFetch(source, { headers: { Accept: "*/*" } });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.arrayBuffer();
    if (!payload.byteLength) throw new Error("The STL preview is empty.");
    const geometry = new STLLoader().parse(payload);
    geometry.computeVertexNormals();
    const colors = { default: 0x3f72ef, warning: 0xd95b3d, pass: 0x16845b };
    const material = new MeshStandardMaterial({
      color: colors[props.accent || "default"],
      roughness: 0.42,
      metalness: 0.08,
    });
    mesh = new Mesh(geometry, material);
    scene?.add(mesh);

    const bounds = new Box3().setFromObject(mesh);
    const size = bounds.getSize(new Vector3());
    bounds.getCenter(modelCenter);
    modelDistance = Math.max(size.x, size.y, size.z, 1) * 1.8;
    controls.minDistance = modelDistance * 0.08;
    controls.maxDistance = modelDistance * 8;
    applyView();
    loading.value = false;
  } catch (caught) {
    error.value = t("Preview geometry could not be loaded with the current Demo session.");
    errorDetail.value = caught instanceof Error ? caught.message : null;
    loading.value = false;
  }
}

onMounted(() => {
  if (!canvas.value) return;
  scene = new Scene();
  scene.background = new Color(0xf4f7fb);
  camera = new PerspectiveCamera(42, 1, 0.01, 100000);
  renderer = new WebGLRenderer({ canvas: canvas.value, antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  controls = new OrbitControls(camera, canvas.value);
  controls.enableDamping = true;
  controls.enableRotate = true;
  controls.enableZoom = true;
  controls.enablePan = true;
  controls.screenSpacePanning = true;

  scene.add(new AmbientLight(0xffffff, 1.7));
  const keyLight = new DirectionalLight(0xffffff, 2.4);
  keyLight.position.set(4, -3, 6);
  scene.add(keyLight);
  const fillLight = new DirectionalLight(0xa9c4ff, 1.2);
  fillLight.position.set(-4, 2, -2);
  scene.add(fillLight);

  resize();
  renderer.setAnimationLoop(() => {
    controls?.update();
    if (scene && camera) renderer?.render(scene, camera);
  });
  window.addEventListener("resize", resize);
  loadModel(props.source);
});

watch(
  () => [props.source, props.accent] as const,
  ([source]) => {
    if (renderer) loadModel(source);
  },
);

watch(view, applyView);

onBeforeUnmount(() => {
  window.removeEventListener("resize", resize);
  renderer?.setAnimationLoop(null);
  controls?.dispose();
  mesh?.geometry.dispose();
  if (mesh?.material instanceof MeshStandardMaterial) mesh.material.dispose();
  renderer?.dispose();
});
</script>

<template>
  <div class="cad-preview">
    <div class="viewer-toolbar">
      <button type="button" class="secondary-button" :aria-pressed="view === 'iso'" @click="selectView('iso')">{{ t("Iso") }}</button>
      <button type="button" class="secondary-button" :aria-pressed="view === 'front'" @click="selectView('front')">{{ t("Front") }}</button>
      <button type="button" class="secondary-button" :aria-pressed="view === 'top'" @click="selectView('top')">{{ t("Top") }}</button>
      <button type="button" class="secondary-button" @click="toggleTransparency">
        {{ transparencyLabel }}
      </button>
      <button type="button" class="secondary-button" :aria-label="t('Zoom in')" :title="t('Zoom in')" @click="zoomBy(0.78)">+</button>
      <button type="button" class="secondary-button" :aria-label="t('Zoom out')" :title="t('Zoom out')" @click="zoomBy(1.28)">−</button>
      <button type="button" class="secondary-button" @click="selectView(view)">{{ t("Reset view") }}</button>
    </div>
    <canvas ref="canvas" :aria-label="t('Interactive CAD preview')"></canvas>
    <p v-if="loading" class="viewer-message">{{ t("Loading engineering preview...") }}</p>
    <p v-else-if="!error" class="viewer-message viewer-help">
      {{ t("Drag to rotate · Scroll or pinch to zoom · Right-drag to pan") }}
    </p>
    <div v-if="error" class="viewer-message viewer-error" role="alert">
      <span>{{ error }}</span>
      <small v-if="errorDetail">{{ errorDetail }}</small>
      <button type="button" class="secondary-button" @click="loadModel(source)">{{ t("Retry preview") }}</button>
    </div>
  </div>
</template>
