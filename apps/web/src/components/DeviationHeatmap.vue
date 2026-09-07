<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import {
  AmbientLight,
  Box3,
  BufferAttribute,
  BufferGeometry,
  Color,
  PerspectiveCamera,
  Points,
  PointsMaterial,
  Scene,
  Vector3,
  WebGLRenderer,
} from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

import { useI18n } from "../i18n";

const props = defineProps<{
  positions: number[][];
  deviations: number[];
  tolerance: number;
}>();
const { t } = useI18n();
const canvas = ref<HTMLCanvasElement | null>(null);
let renderer: WebGLRenderer | null = null;
let scene: Scene | null = null;
let camera: PerspectiveCamera | null = null;
let controls: OrbitControls | null = null;
let cloud: Points | null = null;

function deviationColor(value: number): Color {
  if (Math.abs(value) <= props.tolerance) return new Color(0x20a36a);
  return value < 0 ? new Color(0x2463eb) : new Color(0xdc3f38);
}

function renderCloud(): void {
  if (!scene || !camera || !controls || !props.positions.length) return;
  if (cloud) {
    scene.remove(cloud);
    cloud.geometry.dispose();
    (cloud.material as PointsMaterial).dispose();
  }
  const geometry = new BufferGeometry();
  geometry.setAttribute("position", new BufferAttribute(new Float32Array(props.positions.flat()), 3));
  geometry.setAttribute(
    "color",
    new BufferAttribute(
      new Float32Array(props.deviations.flatMap((value) => deviationColor(value).toArray())),
      3,
    ),
  );
  geometry.computeBoundingBox();
  const bounds = geometry.boundingBox || new Box3();
  const center = bounds.getCenter(new Vector3());
  const size = bounds.getSize(new Vector3());
  const distance = Math.max(size.x, size.y, size.z, 1) * 1.9;
  cloud = new Points(
    geometry,
    new PointsMaterial({ size: Math.max(distance * 0.009, 0.02), vertexColors: true }),
  );
  scene.add(cloud);
  camera.position.copy(center).add(new Vector3(1, 1, 1).normalize().multiplyScalar(distance));
  controls.target.copy(center);
  controls.update();
}

function resize(): void {
  if (!renderer || !camera || !canvas.value) return;
  const width = canvas.value.clientWidth || 640;
  const height = canvas.value.clientHeight || 420;
  renderer.setSize(width, height, false);
  camera.aspect = width / height;
  camera.updateProjectionMatrix();
}

onMounted(() => {
  if (!canvas.value) return;
  scene = new Scene();
  scene.background = new Color(0xf4f7fb);
  scene.add(new AmbientLight(0xffffff, 2));
  camera = new PerspectiveCamera(42, 1, 0.01, 100000);
  renderer = new WebGLRenderer({ canvas: canvas.value, antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  controls = new OrbitControls(camera, canvas.value);
  controls.enableDamping = true;
  resize();
  renderCloud();
  renderer.setAnimationLoop(() => {
    controls?.update();
    if (scene && camera) renderer?.render(scene, camera);
  });
  window.addEventListener("resize", resize);
});

watch(() => [props.positions, props.deviations], renderCloud, { deep: true });

onBeforeUnmount(() => {
  window.removeEventListener("resize", resize);
  renderer?.setAnimationLoop(null);
  controls?.dispose();
  cloud?.geometry.dispose();
  if (cloud) (cloud.material as PointsMaterial).dispose();
  renderer?.dispose();
});
</script>

<template>
  <div class="deviation-heatmap">
    <div class="heatmap-legend" :aria-label="t('Deviation heatmap legend')">
      <span class="negative">{{ t("Negative deviation") }}</span>
      <span class="within">{{ t("Within tolerance") }}</span>
      <span class="positive">{{ t("Positive deviation") }}</span>
    </div>
    <canvas ref="canvas" :aria-label="t('Interactive 3D deviation cloud')"></canvas>
    <small>{{ t("Drag to rotate · Scroll or pinch to zoom · Right-drag to pan") }}</small>
  </div>
</template>
