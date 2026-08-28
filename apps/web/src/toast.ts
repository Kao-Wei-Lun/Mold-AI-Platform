import { readonly, ref } from "vue";

export type ToastTone = "success" | "error" | "info";

export interface ToastMessage {
  id: number;
  message: string;
  tone: ToastTone;
}

const messages = ref<ToastMessage[]>([]);
let nextId = 1;

export const toasts = readonly(messages);

export function dismissToast(id: number): void {
  messages.value = messages.value.filter((message) => message.id !== id);
}

export function pushToast(
  message: string,
  tone: ToastTone = "info",
  durationMs = 4500,
): number {
  const id = nextId++;
  messages.value = [...messages.value, { id, message, tone }].slice(-4);
  if (durationMs > 0 && typeof window !== "undefined") {
    window.setTimeout(() => dismissToast(id), durationMs);
  }
  return id;
}

export function resetToasts(): void {
  messages.value = [];
  nextId = 1;
}
