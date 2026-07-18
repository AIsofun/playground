import type {
  ComplianceAlertMessage,
  FsmStateUpdateMessage,
  HesitationWarningMessage,
} from "@/types/workstationWs";
import { getMessageType, isRecord } from "@/types/workstationWs";

export type WorkstationWsDispatchHandlers = {
  onFsmStateUpdate?: (msg: FsmStateUpdateMessage) => void;
  onComplianceAlert?: (msg: ComplianceAlertMessage) => void;
  onHesitationWarning?: (msg: HesitationWarningMessage) => void;
};

/**
 * 服务端 WS 消息分发（§5.2）：预留 FSM_STATE_UPDATE / COMPLIANCE_ALERT，其余类型可后续扩展。
 */
export function dispatchWorkstationMessage(
  raw: unknown,
  handlers: WorkstationWsDispatchHandlers,
): void {
  const type = getMessageType(raw);
  if (!type || !isRecord(raw)) return;

  switch (type) {
    case "FSM_STATE_UPDATE": {
      const stateId = raw.state_id;
      if (typeof stateId !== "string") return;
      const msg: FsmStateUpdateMessage = {
        type: "FSM_STATE_UPDATE",
        state_id: stateId,
        timestamp: typeof raw.timestamp === "string" ? raw.timestamp : undefined,
      };
      handlers.onFsmStateUpdate?.(msg);
      break;
    }
    case "COMPLIANCE_ALERT": {
      const msg = raw as ComplianceAlertMessage;
      if (msg.type !== "COMPLIANCE_ALERT") return;
      handlers.onComplianceAlert?.(msg);
      break;
    }
    case "HESITATION_WARNING": {
      const msg = raw as HesitationWarningMessage;
      if (msg.type !== "HESITATION_WARNING") return;
      handlers.onHesitationWarning?.(msg);
      break;
    }
    default:
      break;
  }
}
