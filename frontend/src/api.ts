import type { Discussion, Post, SourcePresets } from "./types";

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    let message = `请求失败（${response.status}）`;
    try {
      const error = await response.json();
      if (typeof error.detail === "string") message = error.detail;
      else if (Array.isArray(error.detail))
        message = error.detail.map((e: { msg: string }) => e.msg).join("；");
      else if (typeof error.message === "string") message = error.message;
    } catch {
      /* Preserve the useful HTTP status for non-JSON responses. */
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}
export const json = (method: string, data?: unknown): RequestInit => ({
  method,
  ...(data === undefined ? {} : { body: JSON.stringify(data) }),
});

export const getSourcePresets = (signal?: AbortSignal) =>
  api<SourcePresets>("/source-presets", { signal });

export const getDiscussion = (id: string, signal?: AbortSignal) =>
  api<Discussion>(`/items/${encodeURIComponent(id)}/discussion`, {
    ...json("POST"),
    signal,
  });

export const getArticleContent = (id: string, signal?: AbortSignal) =>
  api<Post>(`/items/${encodeURIComponent(id)}/content`, {
    ...json("POST"),
    signal,
  });
