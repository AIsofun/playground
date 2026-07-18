import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useAppNavigate } from "@/navContext";
import { LayoutPanelLeft, MonitorPlay, Wifi } from "lucide-react";

import { HudOverlay } from "@/components/HudOverlay";
import { InstructionCard } from "@/components/InstructionCard";
import { InstructionList } from "@/components/InstructionList";
import { SOPPlayer, type SOPPlayerHandle } from "@/components/SOPPlayer";
import { WsConnectionHud } from "@/components/WsConnectionHud";
import { MOCK_SOP_DEMO } from "@/data/mockWorkstation";
import { buildDemoVideoCandidates } from "@/lib/demoVideoSources";
import { getWsBaseUrl } from "@/lib/env";
import { fsmStateToView } from "@/lib/fsmView";
import { useFsmGraph } from "@/hooks/useFsmGraph";
import { useSop } from "@/hooks/useSop";
import { useWorkstationWs } from "@/hooks/useWorkstationWs";
import { MockIntervalRunner } from "@/mock/MockIntervalRunner";
import type { HudActivePayload } from "@/types/workstation";
import type { SOPStep } from "@/types/sopUi";

const DEMO_RESOURCE_ID = "demo";

type DataMode = "mock" | "real";

export default function DemoPage() {
  const navigate = useAppNavigate();
  const [mode, setMode] = useState<DataMode>("mock");
  const [fsmStateId, setFsmStateId] = useState("STEP_0");
  const [hud, setHud] = useState<HudActivePayload | null>(null);
  const playerRef = useRef<SOPPlayerHandle>(null);

  const sop = useSop(mode === "real" ? DEMO_RESOURCE_ID : null);
  const fsm = useFsmGraph(mode === "real" ? DEMO_RESOURCE_ID : null);

  const ws = useWorkstationWs(DEMO_RESOURCE_ID, {
    enabled: mode === "real" && Boolean(getWsBaseUrl()),
    onComplianceAlert: (msg) => {
      setHud({
        type: "VIOLATION",
        title: String(msg.title ?? "合规违规"),
        suggestion: String(
          msg.suggestion ?? "请停机确认后按规程复位，必要时上报班组长。",
        ),
        relatedStepId:
          typeof msg.related_step_id === "number"
            ? msg.related_step_id
            : undefined,
      });
    },
    onHesitationWarning: (msg) => {
      setHud({
        type: "TIMEOUT",
        title: String(msg.title ?? "动作犹豫 / 超时"),
        suggestion: String(
          msg.suggestion ?? "请回到标准节拍完成当前关键动作；仍异常请呼叫协助。",
        ),
        relatedStepId:
          typeof msg.related_step_id === "number"
            ? msg.related_step_id
            : undefined,
      });
    },
  });

  const steps: SOPStep[] = useMemo(() => {
    if (mode === "mock") return MOCK_SOP_DEMO.steps;
    const apiSteps = sop.data?.steps;
    if (apiSteps && apiSteps.length > 0) return apiSteps as SOPStep[];
    return [];
  }, [mode, sop.data?.steps]);

  const apiDemoVideo =
    mode === "real"
      ? (sop.data as { demo_video_src?: string } | null)?.demo_video_src
      : undefined;

  const videoCandidates = useMemo(
    () => buildDemoVideoCandidates(apiDemoVideo ?? null),
    [apiDemoVideo],
  );
  const videoSrc = videoCandidates[0] ?? MOCK_SOP_DEMO.demo_video_src;
  const videoFallbacks = videoCandidates.slice(1);

  const assumedFps = useMemo(() => {
    if (mode === "mock") return MOCK_SOP_DEMO.assumed_fps;
    const raw = sop.data as { assumed_fps?: number } | null;
    if (typeof raw?.assumed_fps === "number") return raw.assumed_fps;
    return MOCK_SOP_DEMO.assumed_fps;
  }, [mode, sop.data]);

  useEffect(() => {
    setFsmStateId("STEP_0");
    setHud(null);
  }, [mode]);

  useEffect(() => {
    if (mode !== "real") return;
    if (ws.lastFsmStateUpdate) {
      setFsmStateId(ws.lastFsmStateUpdate.state_id);
    }
  }, [mode, ws.lastFsmStateUpdate]);

  useEffect(() => {
    if (mode !== "mock") return;

    const runner = new MockIntervalRunner();
    runner.start({
      stepIntervalMs: 8000,
      injectTimeoutAtSteps: [2],
      loop: false,
      maxStepId: MOCK_SOP_DEMO.steps.length,
      onFsmStateUpdate: (stateId) => setFsmStateId(stateId),
      onTimeoutAtStep: (stepId) => {
        const relatedStep = MOCK_SOP_DEMO.steps.find(
          (s) => s.step_id === stepId,
        );
        setHud({
          type: "TIMEOUT",
          title: "动作超时 / 犹豫（Mock 注入）",
          suggestion: `请回到标准节拍完成「${relatedStep?.title ?? "当前步骤"}」关键动作；仍异常请呼叫班组长协助。`,
          relatedStepId: stepId,
        });
      },
    });

    return () => {
      runner.stop();
    };
  }, [mode]);

  const view = useMemo(
    () => fsmStateToView(fsmStateId, steps),
    [fsmStateId, steps],
  );

  useEffect(() => {
    if (view.workflowDone || view.currentStepId == null) return;
    const st = steps.find((s) => s.step_id === view.currentStepId);
    if (!st) return;
    playerRef.current?.seekToKeyframe(st.keyframe_index);
  }, [steps, view.currentStepId, view.workflowDone]);

  const currentStep =
    view.currentStepId != null
      ? (steps.find((s) => s.step_id === view.currentStepId) ?? null)
      : null;

  const onStepClick = useCallback(
    (step: SOPStep) => {
      playerRef.current?.seekToKeyframe(step.keyframe_index);
    },
    [],
  );

  const wsEnabled = Boolean(getWsBaseUrl());
  const wsLine =
    mode === "mock"
      ? "WS：Mock（本地 MockIntervalRunner）"
      : !wsEnabled
        ? "WS：未配置 VITE_WS_BASE_URL"
        : ws.reconnectExhausted
          ? "WS：已用尽重试"
          : ws.status === "connected"
            ? "WS：已连接"
            : ws.status === "reconnecting" || ws.status === "connecting"
              ? "WS：重连中"
              : ws.status === "disconnected"
                ? "WS：断开"
                : "WS：待机";

  return (
    <div className="flex h-screen min-h-[1080px] w-full min-w-[1920px] overflow-hidden bg-[#121212] text-foreground">
      <aside className="flex h-full w-[300px] shrink-0 flex-col border-r-2 border-emerald-500/35 bg-card/40">
        <header className="flex shrink-0 flex-col gap-3 border-b border-border px-4 py-3">
          <div className="flex items-center gap-2">
            <LayoutPanelLeft className="size-7 text-emerald-400" aria-hidden />
            <div className="min-w-0 flex-1">
              <p className="truncate text-industrial font-semibold tracking-tight">
                工位演示 / T06
              </p>
              <a
                href="/"
                className="text-base text-emerald-300/90 underline-offset-2 hover:underline"
                onClick={(e) => {
                  e.preventDefault();
                  navigate("/");
                }}
              >
                返回首页
              </a>
            </div>
          </div>

          <div
            className="grid grid-cols-2 gap-2"
            role="group"
            aria-label="数据源切换"
          >
            <button
              type="button"
              aria-pressed={mode === "mock"}
              onClick={() => setMode("mock")}
              className={`min-h-14 rounded-xl border-2 px-3 text-base font-bold transition-colors ${
                mode === "mock"
                  ? "border-emerald-400 bg-emerald-500/20 text-emerald-50"
                  : "border-border bg-secondary/40 text-muted-foreground hover:bg-secondary/60"
              }`}
            >
              Mock 演示
            </button>
            <button
              type="button"
              aria-pressed={mode === "real"}
              onClick={() => setMode("real")}
              className={`min-h-14 rounded-xl border-2 px-3 text-base font-bold transition-colors ${
                mode === "real"
                  ? "border-sky-400 bg-sky-500/20 text-sky-50"
                  : "border-border bg-secondary/40 text-muted-foreground hover:bg-secondary/60"
              }`}
            >
              Real 接口
            </button>
          </div>
        </header>

        <div className="flex shrink-0 flex-col gap-1 border-b border-border px-4 py-2 text-base text-muted-foreground">
          <div className="flex items-center gap-2">
            <Wifi className="size-5 shrink-0 text-emerald-400/90" aria-hidden />
            <span className="truncate">{wsLine}</span>
          </div>
          <span className="truncate text-base text-foreground/80">
            FSM：<span className="font-mono">{fsmStateId}</span>
          </span>
          {mode === "real" && (sop.loading || fsm.loading) ? (
            <span>REST：加载中…</span>
          ) : null}
          {mode === "real" && sop.error ? (
            <span className="truncate text-rose-200/90">SOP：{sop.error}</span>
          ) : null}
          {mode === "real" && fsm.error ? (
            <span className="truncate text-rose-200/90">FSM：{fsm.error}</span>
          ) : null}
          {mode === "real" && ws.lastComplianceAlert ? (
            <span className="truncate text-rose-100/90">
              最近：{ws.lastComplianceAlert.title ?? "COMPLIANCE_ALERT"}
            </span>
          ) : null}
        </div>

        {mode === "real" && (sop.loading || fsm.loading) ? (
            <div className="flex flex-1 flex-col gap-3 p-4">
              {Array.from({ length: 4 }).map((_, i) => (
                <div
                  key={i}
                  className="h-16 animate-pulse rounded-xl border-2 border-border/40 bg-secondary/50"
                />
              ))}
              <p className="mt-2 text-center text-base text-muted-foreground">
                正在从后端加载 SOP 数据…
              </p>
            </div>
          ) : steps.length > 0 ? (
          <InstructionList
            steps={steps}
            currentStepId={view.currentStepId}
            workflowDone={view.workflowDone}
            onStepClick={onStepClick}
          />
        ) : (
          <div className="flex flex-1 items-center justify-center p-4 text-center text-base text-muted-foreground">
            Real 模式未拉到步骤数据；请配置后端或切回 Mock。
          </div>
        )}
      </aside>

      <main className="flex min-h-0 min-w-0 flex-1 flex-col bg-[#121212]">
        <div className="flex items-center gap-3 border-b border-border px-6 py-3">
          <MonitorPlay className="size-8 text-emerald-400" aria-hidden />
          <div>
            <p className="text-industrial-lg font-semibold">SOP 引导演示</p>
            <p className="text-base text-muted-foreground">
              播放器 seek · 步骤联动 · HUD（TIMEOUT / VIOLATION）
            </p>
          </div>
        </div>

        <div className="flex min-h-0 flex-1 flex-col gap-4 p-6">
          <div className="min-h-0 flex-[2] min-h-[320px]">
            <SOPPlayer
              ref={playerRef}
              src={videoSrc}
              srcFallbacks={videoFallbacks}
              steps={steps.length > 0 ? steps : MOCK_SOP_DEMO.steps}
              assumedFps={assumedFps}
              className="h-full min-h-[300px] max-h-[62vh]"
            />
          </div>
          <InstructionCard
            step={view.workflowDone ? null : currentStep}
            workflowComplete={view.workflowDone}
            className="shrink-0"
          />
        </div>
      </main>

      <HudOverlay hud={hud} onAcknowledge={() => setHud(null)} />

      {mode === "real" ? (
        <WsConnectionHud
          status={ws.status}
          reconnectExhausted={ws.reconnectExhausted}
        />
      ) : (
        <div
          className="pointer-events-none fixed bottom-4 right-4 z-50 max-w-md rounded-lg border border-emerald-500/45 bg-emerald-950/90 px-4 py-3 text-base text-emerald-50 shadow-lg backdrop-blur-sm"
          role="status"
        >
          <p className="font-semibold tracking-wide">演示模式</p>
          <p className="mt-1 text-base leading-snug">
            MockIntervalRunner：每 8s 发送 FSM_STATE_UPDATE；第 3 步注入
            TIMEOUT。
          </p>
        </div>
      )}
    </div>
  );
}
