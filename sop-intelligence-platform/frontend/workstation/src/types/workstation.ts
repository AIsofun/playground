/** 与 workstation-ui.md §5.2 告警类消息对齐（前端展示子集） */
export type HudViolationPayload = {
  type: "VIOLATION";
  title: string;
  suggestion: string;
  relatedStepId?: number;
};

export type HudTimeoutPayload = {
  type: "TIMEOUT";
  title: string;
  suggestion: string;
  relatedStepId?: number;
};

export type HudActivePayload = HudViolationPayload | HudTimeoutPayload;
