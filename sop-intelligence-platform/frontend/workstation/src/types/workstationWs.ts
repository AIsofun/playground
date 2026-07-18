/**
 * WebSocket 消息（对齐 workstation-ui.md §5.2）
 */

export const WS_RECONNECT_DELAYS_MS = [1000, 2000, 4000, 8000, 16000] as const;

export type WorkstationWsConnectionStatus =
  | "idle"
  | "connecting"
  | "connected"
  | "reconnecting"
  | "disconnected";

export type WsMessageType =
  | "FSM_STATE_UPDATE"
  | "COMPLIANCE_ALERT"
  | "HESITATION_WARNING"
  | "SOP_SWITCH";

export type FsmStateUpdateMessage = {
  type: "FSM_STATE_UPDATE";
  state_id: string;
  timestamp?: string;
};

export type ComplianceAlertMessage = {
  type: "COMPLIANCE_ALERT";
  /** T05 HUD 字段预留 */
  title?: string;
  suggestion?: string;
  related_step_id?: number;
  [key: string]: unknown;
};

/** §5.2：超时/犹豫 → 前端映射为 TIMEOUT HUD */
export type HesitationWarningMessage = {
  type: "HESITATION_WARNING";
  title?: string;
  suggestion?: string;
  related_step_id?: number;
  [key: string]: unknown;
};

export type WorkstationWsMessage =
  | FsmStateUpdateMessage
  | ComplianceAlertMessage
  | {
      type: Exclude<WsMessageType, "FSM_STATE_UPDATE" | "COMPLIANCE_ALERT">;
      [key: string]: unknown;
    };

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

export function getMessageType(raw: unknown): string | undefined {
  if (!isRecord(raw)) return undefined;
  const t = raw.type;
  return typeof t === "string" ? t : undefined;
}
