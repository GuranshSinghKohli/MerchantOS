export type HealthResponse = {
  status: string;
  version: string;
};

export function apiUrl(path: string): string {
  const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  return `${base.replace(/\/$/, "")}${path}`;
}

export async function fetchHealth(fetcher: typeof fetch = fetch): Promise<HealthResponse> {
  const response = await fetcher(apiUrl("/health"));
  if (!response.ok) {
    throw new Error(`Health check failed: ${response.status}`);
  }
  return (await response.json()) as HealthResponse;
}
