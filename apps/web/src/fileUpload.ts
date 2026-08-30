export const MEBIBYTE = 1024 * 1024;

export const uploadPolicies = {
  cad: { maxBytes: 200 * MEBIBYTE, extensions: ["step", "stp", "stl"] },
  knowledge: { maxBytes: 5 * MEBIBYTE, extensions: ["txt", "md", "pdf", "docx"] },
  hmi: { maxBytes: 10 * MEBIBYTE, extensions: ["png", "jpg", "jpeg"] },
} as const;

export type UploadValidationError = "unsupported_type" | "too_large";

export function fileExtension(file: Pick<File, "name">): string {
  return file.name.split(".").pop()?.toLowerCase() || "";
}

export function validateUploadFile(
  file: Pick<File, "name" | "size">,
  policy: { maxBytes: number; extensions: readonly string[] },
): UploadValidationError | null {
  if (!policy.extensions.includes(fileExtension(file))) return "unsupported_type";
  if (file.size > policy.maxBytes) return "too_large";
  return null;
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < MEBIBYTE) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / MEBIBYTE).toFixed(1)} MB`;
}
