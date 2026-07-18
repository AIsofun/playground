import { useCallback, useEffect, useState } from "react";

import { getApiBaseUrl } from "@/lib/env";
import { joinBaseUrl } from "@/lib/urls";

/** GET /api/fsm/{id} 响应（字段随后端扩展） */
export type FsmGraphApiDocument = {
  fsm_id?: string;
  id?: string;
  states?: unknown[];
  transitions?: unknown[];
  [key: string]: unknown;
};

export type UseFsmGraphState = {
  data: FsmGraphApiDocument | null;
  error: string | null;
  loading: boolean;
  refetch: () => Promise<void>;
};

async function fetchFsmGraph(
  fsmId: string,
  signal: AbortSignal,
): Promise<FsmGraphApiDocument> {
  const base = getApiBaseUrl();
  if (!base) {
    throw new Error("VITE_API_BASE_URL 未配置");
  }
  const url = joinBaseUrl(base, `/api/fsm/${encodeURIComponent(fsmId)}`);
  const res = await fetch(url, { signal });
  if (!res.ok) {
    throw new Error(`FSM 请求失败：HTTP ${res.status}`);
  }
  return (await res.json()) as FsmGraphApiDocument;
}

/**
 * 加载 FSM 图/快照（workstation-ui.md §5.1：GET /api/fsm/{id}）
 */
export function useFsmGraph(fsmId: string | null): UseFsmGraphState {
  const [data, setData] = useState<FsmGraphApiDocument | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(
    async (signal: AbortSignal) => {
      if (!fsmId) {
        setData(null);
        setError(null);
        setLoading(false);
        return;
      }
      setLoading(true);
      setError(null);
      try {
        const doc = await fetchFsmGraph(fsmId, signal);
        if (!signal.aborted) setData(doc);
      } catch (e) {
        if ((e as Error).name === "AbortError") return;
        if (!signal.aborted) {
          setData(null);
          setError(
            e instanceof Error ? e.message : "FSM 请求异常，请检查网络或后端服务",
          );
        }
      } finally {
        if (!signal.aborted) setLoading(false);
      }
    },
    [fsmId],
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
