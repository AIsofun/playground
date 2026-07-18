import { useCallback, useEffect, useState } from "react";

import { getApiBaseUrl } from "@/lib/env";
import { joinBaseUrl } from "@/lib/urls";
import type { SOPStep } from "@/types/sopUi";

/** GET /api/sop/{id} 响应（字段随后端扩展） */
export type SopApiDocument = {
  steps?: SOPStep[];
  sop_id?: string;
  id?: string;
  [key: string]: unknown;
};

export type UseSopState = {
  data: SopApiDocument | null;
  error: string | null;
  loading: boolean;
  refetch: () => Promise<void>;
};

async function fetchSopDocument(
  sopId: string,
  signal: AbortSignal,
): Promise<SopApiDocument> {
  const base = getApiBaseUrl();
  if (!base) {
    throw new Error("VITE_API_BASE_URL 未配置");
  }
  const url = joinBaseUrl(base, `/api/sop/${encodeURIComponent(sopId)}`);
  const res = await fetch(url, { signal });
  if (!res.ok) {
    throw new Error(`SOP 请求失败：HTTP ${res.status}`);
  }
  return (await res.json()) as SopApiDocument;
}

/**
 * 加载 SOP 文档（workstation-ui.md §5.1：GET /api/sop/{id}）
 */
export function useSop(sopId: string | null): UseSopState {
  const [data, setData] = useState<SopApiDocument | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(
    async (signal: AbortSignal) => {
      if (!sopId) {
        setData(null);
        setError(null);
        setLoading(false);
        return;
      }
      setLoading(true);
      setError(null);
      try {
        const doc = await fetchSopDocument(sopId, signal);
        if (!signal.aborted) setData(doc);
      } catch (e) {
        if ((e as Error).name === "AbortError") return;
        if (!signal.aborted) {
          setData(null);
          setError(
            e instanceof Error ? e.message : "SOP 请求异常，请检查网络或后端服务",
          );
        }
      } finally {
        if (!signal.aborted) setLoading(false);
      }
    },
    [sopId],
  );

  useEffect(() => {
    const ac = new AbortController();
    void load(ac.signal);
    return () => ac.abort();
  }, [load]);

  const refetch = useCallback(async () => {
    const ac = new AbortController();
    await load(ac.signal);
  }, [load]);

  return { data, error, loading, refetch };
}
