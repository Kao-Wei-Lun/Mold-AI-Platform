export type ServiceState = {
  name: string;
  status: "ok" | "error";
  detail: string | null;
};

export type ReadinessResponse = {
  status: "ok" | "degraded";
  services: ServiceState[];
};

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "";

export async function fetchReadiness(): Promise<ReadinessResponse> {
  const response = await fetch(`${apiBaseUrl}/api/v1/health/ready`, {
    headers: { Accept: "application/json" },
  });

  const payload = (await response.json()) as ReadinessResponse;
  if (!response.ok && response.status !== 503) {
    throw new Error(`Health endpoint returned HTTP ${response.status}`);
  }
  return payload;
}
