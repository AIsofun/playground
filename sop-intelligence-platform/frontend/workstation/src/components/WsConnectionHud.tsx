import type { WorkstationWsConnectionStatus } from "@/types/workstationWs";

type Props = {
  status: WorkstationWsConnectionStatus;
  reconnectExhausted: boolean;
};

function labelForStatus(status: WorkstationWsConnectionStatus): string {
  switch (status) {
    case "connected":
      return "已连接";
    case "reconnecting":
    case "connecting":
      return "自动重连中";
    case "disconnected":
      return "断开";
    case "idle":
    default:
      return "断开";
  }
}

export function WsConnectionHud({ status, reconnectExhausted }: Props) {
  const label = labelForStatus(status);
  const isReconnecting = status === "reconnecting" || status === "connecting";
  const tone =
    status === "connected"
      ? "border-emerald-500/50 bg-emerald-500/10 text-emerald-200"
      : status === "disconnected" || status === "idle"
        ? "border-rose-500/40 bg-rose-500/10 text-rose-100"
        : "border-amber-500/45 bg-amber-500/10 text-amber-100";

  return (
    <div
      className={`pointer-events-none fixed bottom-4 right-4 z-50 max-w-md rounded-lg border px-4 py-3 text-base shadow-lg backdrop-blur-sm ${tone}`}
      role="status"
      aria-live="polite"
    >
      <div className="flex items-center gap-2">
        {isReconnecting ? (
          <svg
            className="size-5 shrink-0 animate-spin text-amber-300"
            viewBox="0 0 24 24"
            fill="none"
            aria-hidden
          >
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="3"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8v3a5 5 0 00-5 5H4z"
            />
          </svg>
        ) : null}
        <p className="font-semibold tracking-wide">WebSocket</p>
      </div>
      <p className="mt-1 text-base leading-snug">
        状态：<span className="font-mono">{label}</span>
      </p>
      {isReconnecting ? (
        <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-amber-900/50">
          <div className="h-full animate-pulse rounded-full bg-amber-400/70" style={{ width: "60%" }} />
        </div>
      ) : null}
      {reconnectExhausted ? (
        <p className="mt-2 text-base leading-snug text-rose-50/90">
          连接断开，请刷新页面或检查网络
        </p>
      ) : null}
    </div>
  );
}
