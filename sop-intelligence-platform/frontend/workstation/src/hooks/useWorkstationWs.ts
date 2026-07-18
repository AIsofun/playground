import { useEffect, useRef, useState } from "react";

import { getWsBaseUrl } from "@/lib/env";
import { joinBaseUrl } from "@/lib/urls";
import type {
  ComplianceAlertMessage,
  FsmStateUpdateMessage,
  HesitationWarningMessage,
  WorkstationWsConnectionStatus,
} from "@/types/workstationWs";
import { WS_RECONNECT_DELAYS_MS } from "@/types/workstationWs";
import { dispatchWorkstationMessage } from "@/ws/dispatchWorkstationMessage";

export type UseWorkstationWsOptions = {
  enabled?: boolean;
  onFsmStateUpdate?: (msg: FsmStateUpdateMessage) => void;
  onComplianceAlert?: (msg: ComplianceAlertMessage) => void;
  onHesitationWarning?: (msg: HesitationWarningMessage) => void;
};

export type UseWorkstationWsResult = {
  status: WorkstationWsConnectionStatus;
  /** 最近一次解析成功的 FSM 状态推送（供 UI / 调试） */
  lastFsmStateUpdate: FsmStateUpdateMessage | null;
  /** 最近一次合规告警（T05 HUD 预留） */
  lastComplianceAlert: ComplianceAlertMessage | null;
  /** 最近一次犹豫/超时告警 */
  lastHesitationWarning: HesitationWarningMessage | null;
  /** 指数退避重试用尽（§5.2 / AGENTS.md） */
  reconnectExhausted: boolean;
};

function buildWorkstationWsUrl(workstationId: string): string | null {
  const base = getWsBaseUrl();
  if (!base) return null;
  return joinBaseUrl(base, `/ws/workstation/${encodeURIComponent(workstationId)}`);
}

/**
 * 工位 WebSocket（§5.2）：`VITE_WS_BASE_URL` + `/ws/workstation/{id}`，指数退避重连 [1,2,4,8,16]s。
 */
export function useWorkstationWs(
  workstationId: string | null,
  options: UseWorkstationWsOptions = {},
): UseWorkstationWsResult {
  const {
    enabled = true,
    onFsmStateUpdate,
    onComplianceAlert,
    onHesitationWarning,
  } = options;

  const [status, setStatus] = useState<WorkstationWsConnectionStatus>("idle");
  const [lastFsmStateUpdate, setLastFsmStateUpdate] =
    useState<FsmStateUpdateMessage | null>(null);
  const [lastComplianceAlert, setLastComplianceAlert] =
    useState<ComplianceAlertMessage | null>(null);
  const [lastHesitationWarning, setLastHesitationWarning] =
    useState<HesitationWarningMessage | null>(null);
  const [reconnectExhausted, setReconnectExhausted] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const failureCountRef = useRef(0);
  const shouldRunRef = useRef(false);
  const onFsmRef = useRef(onFsmStateUpdate);
  const onAlertRef = useRef(onComplianceAlert);
  const onHesitationRef = useRef(onHesitationWarning);

  onFsmRef.current = onFsmStateUpdate;
  onAlertRef.current = onComplianceAlert;
  onHesitationRef.current = onHesitationWarning;

  useEffect(() => {
    onFsmRef.current = onFsmStateUpdate;
    onAlertRef.current = onComplianceAlert;
    onHesitationRef.current = onHesitationWarning;
  }, [onFsmStateUpdate, onComplianceAlert, onHesitationWarning]);

  useEffect(() => {
    shouldRunRef.current = false;
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    wsRef.current?.close(1000, "effect_cleanup");
    wsRef.current = null;

    if (!enabled || !workstationId) {
      setStatus("idle");
      setReconnectExhausted(false);
      failureCountRef.current = 0;
      setLastFsmStateUpdate(null);
      setLastComplianceAlert(null);
      setLastHesitationWarning(null);
      return;
    }

    const url = buildWorkstationWsUrl(workstationId);
    if (!url) {
      setStatus("idle");
      setReconnectExhausted(false);
      failureCountRef.current = 0;
      setLastFsmStateUpdate(null);
      setLastComplianceAlert(null);
      setLastHesitationWarning(null);
      return;
    }

    shouldRunRef.current = true;
    setReconnectExhausted(false);
    failureCountRef.current = 0;

    const clearReconnectTimer = () => {
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
    };

    const scheduleReconnect = () => {
      clearReconnectTimer();
      if (!shouldRunRef.current) return;

      failureCountRef.current += 1;
      if (failureCountRef.current > WS_RECONNECT_DELAYS_MS.length) {
        setStatus("disconnected");
        setReconnectExhausted(true);
        return;
      }

      setStatus("reconnecting");
      const delayMs =
        WS_RECONNECT_DELAYS_MS[failureCountRef.current - 1] ?? 16000;
      reconnectTimerRef.current = setTimeout(() => {
        reconnectTimerRef.current = null;
        connect();
      }, delayMs);
    };

    const connect = () => {
      if (!shouldRunRef.current) return;

      try {
        setStatus(
          failureCountRef.current > 0 ? "reconnecting" : "connecting",
        );
        const ws = new WebSocket(url);
        wsRef.current = ws;

        ws.onopen = () => {
          if (!shouldRunRef.current) return;
          failureCountRef.current = 0;
          setReconnectExhausted(false);
          setStatus("connected");
        };

        ws.onmessage = (ev) => {
          if (!shouldRunRef.current) return;
          try {
            const raw: unknown = JSON.parse(String(ev.data));
            dispatchWorkstationMessage(raw, {
              onFsmStateUpdate: (msg) => {
                setLastFsmStateUpdate(msg);
                onFsmRef.current?.(msg);
              },
              onComplianceAlert: (msg) => {
                setLastComplianceAlert(msg);
                onAlertRef.current?.(msg);
              },
              onHesitationWarning: (msg) => {
                setLastHesitationWarning(msg);
                onHesitationRef.current?.(msg);
              },
            });
          } catch {
            /* 非 JSON 或结构异常：忽略 */
          }
        };

        ws.onerror = () => {
          /* 具体错误在 onclose 中统一退避；此处不弹技术堆栈 */
        };

        ws.onclose = () => {
          wsRef.current = null;
          if (!shouldRunRef.current) return;
          scheduleReconnect();
        };
      } catch {
        if (!shouldRunRef.current) return;
        scheduleReconnect();
      }
    };

    connect();

    return () => {
      shouldRunRef.current = false;
      clearReconnectTimer();
      wsRef.current?.close(1000, "unmount");
      wsRef.current = null;
    };
  }, [enabled, workstationId]);

  return {
    status,
    lastFsmStateUpdate,
    lastComplianceAlert,
    lastHesitationWarning,
    reconnectExhausted,
  };
}
