// src/api/client.ts
export const API_BASE =
  import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

async function parseError(res: Response, fallback: string) {
  const text = await res.text().catch(() => "");
  return text || fallback;
}

async function parseJson<T>(res: Response): Promise<T> {
  // Some endpoints may return empty body (204 or plain OK).
  // We defensively handle that without blowing up the client.
  const text = await res.text().catch(() => "");
  if (!text) return {} as T;
  try {
    return JSON.parse(text) as T;
  } catch {
    // If it isn't JSON, return it as a string-like payload
    return text as unknown as T;
  }
}

export async function apiGet<T>(path: string, options?: { signal?: AbortSignal }): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { signal: options?.signal });
  if (!res.ok) throw new Error(await parseError(res, `GET ${path} failed (${res.status})`));
  return parseJson<T>(res);
}

export async function apiPost<T>(path: string, body?: any): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await parseError(res, `POST ${path} failed (${res.status})`));
  return parseJson<T>(res);
}

export async function apiPut<T>(path: string, body: any): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await parseError(res, `PUT ${path} failed (${res.status})`));
  return parseJson<T>(res);
}

export async function apiPatch<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await parseError(res, `PATCH ${path} failed (${res.status})`));
  return parseJson<T>(res);
}

export async function apiDelete<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
  });
  if (!res.ok) throw new Error(await parseError(res, `DELETE ${path} failed (${res.status})`));
  return parseJson<T>(res);
}
