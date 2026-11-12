const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000/api/v1";

export async function apiFetch<T>(path: string, options: RequestInit = {}, token?: string | null): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> | undefined),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `Request failed (${res.status})`);
  }
  return res.json() as Promise<T>;
}

export function getDownloadUrl(evidenceFileId: number): string {
  return `${API_BASE}/evidence/${evidenceFileId}/download`;
}

