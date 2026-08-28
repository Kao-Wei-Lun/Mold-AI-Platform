const TOKEN_STORAGE_KEY = "mold-ai.demo-access-token";
const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);
let csrfToken = "";

export function getDemoAccessToken(): string {
  return typeof window === "undefined" ? "" : window.sessionStorage.getItem(TOKEN_STORAGE_KEY) || "";
}

export function setDemoAccessToken(token: string): void {
  window.sessionStorage.setItem(TOKEN_STORAGE_KEY, token.trim());
}

export function clearDemoAccessToken(): void {
  window.sessionStorage.removeItem(TOKEN_STORAGE_KEY);
}

export function setCsrfToken(token: string): void {
  csrfToken = token.trim();
}

export function clearCsrfToken(): void {
  csrfToken = "";
}

export function consumeDemoAccessBootstrap(): boolean {
  if (typeof window === "undefined" || !window.location.hash.startsWith("#mold-ai-bootstrap=")) {
    return false;
  }
  const encoded = window.location.hash.slice("#mold-ai-bootstrap=".length);
  const token = new URLSearchParams(encoded).get("token")?.trim() || "";
  window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}`);
  if (!token) return false;
  setDemoAccessToken(token);
  return true;
}

export async function apiFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  const token = getDemoAccessToken();
  const method = (init.method || "GET").toUpperCase();
  if (token && !headers.has("Authorization")) headers.set("Authorization", `Bearer ${token}`);
  if (!SAFE_METHODS.has(method) && csrfToken && !headers.has("X-CSRFToken")) {
    headers.set("X-CSRFToken", csrfToken);
  }
  const response = await fetch(input, {
    ...init,
    credentials: init.credentials || "include",
    headers,
  });
  if (response.status === 401 && typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent("mold-ai:unauthorized"));
  }
  return response;
}

function contentDispositionFilename(response: Response): string | null {
  const value = response.headers.get("Content-Disposition") || "";
  const utf8 = value.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  if (utf8) return decodeURIComponent(utf8);
  return value.match(/filename="?([^";]+)"?/i)?.[1] || null;
}

export async function downloadProtectedArtifact(url: string, fallbackName: string): Promise<void> {
  const response = await apiFetch(url, { headers: { Accept: "*/*" } });
  if (!response.ok) throw new Error(`Artifact download returned HTTP ${response.status}`);
  const objectUrl = URL.createObjectURL(await response.blob());
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = contentDispositionFilename(response) || fallbackName;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(objectUrl);
}
