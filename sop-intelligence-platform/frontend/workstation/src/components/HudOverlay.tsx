import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, Clock } from "lucide-react";
import type { HudActivePayload } from "@/types/workstation";

type HudOverlayProps = {
  hud: HudActivePayload | null;
  /** 工人确认后关闭（对齐 frontend/AGENTS.md：须手动确认） */
  onAcknowledge: () => void;
};

/**
 * T05：VIOLATION 全视口红色半透明遮罩 + 处置建议；TIMEOUT 高对比琥珀面板。
 */
export function HudOverlay({ hud, onAcknowledge }: HudOverlayProps) {
  return (
    <AnimatePresence>
      {hud ? (
        <motion.div
          key={`${hud.type}-${hud.title}`}
          role="alertdialog"
          aria-modal="true"
          aria-labelledby="hud-title"
          aria-describedby="hud-suggestion"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
          className={
            hud.type === "VIOLATION"
              ? "fixed inset-0 z-[200] flex items-center justify-center bg-red-950/75 p-6 backdrop-blur-sm"
              : "fixed inset-0 z-[200] flex items-end justify-center bg-black/40 p-6 pb-10 backdrop-blur-[2px]"
          }
        >
          <motion.div
            initial={hud.type === "VIOLATION" ? { scale: 0.96, y: 12 } : { y: 40, opacity: 0 }}
            animate={{ scale: 1, y: 0, opacity: 1 }}
            exit={hud.type === "VIOLATION" ? { scale: 0.98, opacity: 0 } : { y: 24, opacity: 0 }}
            transition={{ type: "spring", stiffness: 320, damping: 28 }}
            className={
              hud.type === "VIOLATION"
                ? "max-w-3xl rounded-2xl border-4 border-red-400/90 bg-red-950/95 p-8 text-center shadow-2xl shadow-red-900/50"
                : "max-w-3xl rounded-2xl border-4 border-amber-400/80 bg-amber-950/95 p-8 text-center shadow-2xl shadow-amber-900/40"
            }
          >
            <div className="mb-4 flex justify-center">
              {hud.type === "VIOLATION" ? (
                <AlertTriangle className="size-16 text-red-300" aria-hidden />
              ) : (
                <Clock className="size-16 text-amber-300" aria-hidden />
              )}
            </div>
            <h2
              id="hud-title"
              className="text-industrial-lg font-bold tracking-tight text-white"
            >
              {hud.type === "VIOLATION" ? "违规告警" : "动作超时 / 犹豫"}
              {hud.relatedStepId != null ? (
                <span className="ml-2 text-industrial font-semibold text-white/80">
                  · 步骤 {hud.relatedStepId}
                </span>
              ) : null}
            </h2>
            <p className="mt-2 text-industrial font-semibold text-white">{hud.title}</p>
            <p
              id="hud-suggestion"
              className="mt-4 text-left text-industrial leading-relaxed text-white/90"
            >
              <span className="font-bold text-white">处置建议：</span>
              {hud.suggestion}
            </p>
            <button
              type="button"
              onClick={onAcknowledge}
              className="mt-8 min-h-14 min-w-[12rem] rounded-xl border-2 border-white/40 bg-white/10 px-8 text-industrial font-bold text-white hover:bg-white/20 active:scale-[0.99]"
            >
              已知晓
            </button>
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
