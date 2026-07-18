import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from "react";
import { Maximize2, Minimize2, Gauge } from "lucide-react";
import type { SOPStep } from "@/types/sopUi";

const RATES = [0.5, 1, 1.25, 1.5, 2] as const;

export type SOPPlayerHandle = {
  /** 按整段视频的 0-based 绝对帧号 `keyframe_index` 定位（§2.1 / §6.1） */
  seekToKeyframe: (keyframeIndex: number) => void;
};

type SOPPlayerProps = {
  /** 主地址；可与 `srcFallbacks` 组合为候选链（见 `activeSrc`） */
  src: string;
  /** 主地址加载失败时依次尝试（工业内网常需本地文件） */
  srcFallbacks?: string[];
  steps: SOPStep[];
  assumedFps: number;
  className?: string;
  onTimeUpdate?: (t: number) => void;
  onRateChange?: (rate: number) => void;
  onFullscreenChange?: (fs: boolean) => void;
};

function resolveSeekSeconds(
  keyframeIndex: number,
  steps: SOPStep[],
  assumedFps: number,
): number | null {
  const step = steps.find((s) => s.keyframe_index === keyframeIndex);
  if (step?.keyframe_time_sec != null) return step.keyframe_time_sec;
  if (step) return step.keyframe_index / assumedFps;
  const fallback = keyframeIndex / assumedFps;
  return Number.isFinite(fallback) ? fallback : null;
}

function mergeCandidates(src: string, fallbacks?: string[]): string[] {
  const rest = (fallbacks ?? []).filter((u) => u && u !== src);
  return [src, ...rest];
}

export const SOPPlayer = forwardRef<SOPPlayerHandle, SOPPlayerProps>(
  function SOPPlayer(
    {
      src,
      srcFallbacks,
      steps,
      assumedFps,
      className,
      onTimeUpdate,
      onRateChange,
      onFullscreenChange,
    },
    ref,
  ) {
    const shellRef = useRef<HTMLDivElement>(null);
    const videoRef = useRef<HTMLVideoElement>(null);
    const [rateIdx, setRateIdx] = useState(1);
    const rate = RATES[rateIdx];
    const [fs, setFs] = useState(false);

    const candidates = useMemo(
      () => mergeCandidates(src, srcFallbacks),
      [src, srcFallbacks],
    );
    const [candidateIdx, setCandidateIdx] = useState(0);
    const [loadFailed, setLoadFailed] = useState(false);

    const activeSrc = candidates[candidateIdx] ?? src;

    useEffect(() => {
      setCandidateIdx(0);
      setLoadFailed(false);
    }, [src, srcFallbacks]);

    const seekToKeyframe = useCallback(
      (keyframeIndex: number) => {
        const v = videoRef.current;
        if (!v) return;
        const sec = resolveSeekSeconds(keyframeIndex, steps, assumedFps);
        if (sec == null) return;
        v.currentTime = Math.min(Math.max(0, sec), v.duration || Infinity);
        void v.play().catch(() => {});
      },
      [assumedFps, steps],
    );

    useImperativeHandle(ref, () => ({ seekToKeyframe }), [seekToKeyframe]);

    useEffect(() => {
      const v = videoRef.current;
      if (v) v.playbackRate = rate;
      onRateChange?.(rate);
    }, [rate, onRateChange]);

    useEffect(() => {
      const el = shellRef.current;
      if (!el) return;
      const onFs = () => {
        const active = document.fullscreenElement === el;
        setFs(active);
        onFullscreenChange?.(active);
      };
      document.addEventListener("fullscreenchange", onFs);
      return () => document.removeEventListener("fullscreenchange", onFs);
    }, [onFullscreenChange]);

    const toggleFullscreen = useCallback(() => {
      const el = shellRef.current;
      if (!el) return;
      if (document.fullscreenElement === el) void document.exitFullscreen();
      else void el.requestFullscreen();
    }, []);

    const cycleRate = useCallback(() => {
      setRateIdx((i) => (i + 1) % RATES.length);
    }, []);

    const rateLabel = useMemo(() => `${rate}x`, [rate]);

    const onVideoError = useCallback(() => {
      setCandidateIdx((i) => {
        const next = i + 1;
        if (next < candidates.length) return next;
        setLoadFailed(true);
        return i;
      });
    }, [candidates.length]);

    return (
      <div
        ref={shellRef}
        className={`relative flex h-full min-h-[280px] w-full min-w-0 flex-col overflow-hidden rounded-2xl border border-slate-700 bg-black ${className ?? ""}`}
      >
        {loadFailed ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-4 p-8 text-center text-industrial text-slate-200">
            <p className="font-bold text-amber-200">视频无法加载</p>
            <p className="max-w-2xl text-base leading-relaxed text-slate-300">
              当前网络可能拦截外链。请将任意短 mp4 放到{" "}
              <span className="font-mono text-emerald-200">
                frontend/workstation/public/demo-sop-guide.mp4
              </span>
              ，或在{" "}
              <span className="font-mono text-emerald-200">.env</span> 中设置{" "}
              <span className="font-mono text-emerald-200">VITE_DEMO_VIDEO_URL</span>{" "}
              指向可访问的 mp4 地址后重启{" "}
              <span className="font-mono text-emerald-200">pnpm dev</span>。
            </p>
          </div>
        ) : (
          <>
            <video
              key={activeSrc}
              ref={videoRef}
              className="h-full min-h-[260px] w-full flex-1 bg-black object-contain"
              src={activeSrc}
              controls
              playsInline
              preload="auto"
              onTimeUpdate={(e) => onTimeUpdate?.(e.currentTarget.currentTime)}
              onError={onVideoError}
            />
            {/* AI 扫描线特效 —— 增强演示科技感 */}
            <div
              className="pointer-events-none absolute inset-0 overflow-hidden"
              aria-hidden
            >
              <div className="absolute left-0 h-[2px] w-full animate-scanline bg-gradient-to-r from-transparent via-emerald-400/40 to-transparent" />
            </div>
          </>
        )}
        <div className="pointer-events-auto absolute bottom-4 right-4 z-10 flex flex-wrap gap-3">
          <button
            type="button"
            onClick={toggleFullscreen}
            className="inline-flex min-h-14 min-w-[7rem] items-center justify-center gap-2 rounded-xl border-2 border-slate-500 bg-slate-900/90 px-6 text-industrial font-semibold text-slate-100 shadow-lg backdrop-blur hover:bg-slate-800 active:scale-[0.98]"
            aria-label={fs ? "退出全屏" : "全屏"}
          >
            {fs ? <Minimize2 className="size-8" /> : <Maximize2 className="size-8" />}
            {fs ? "退出全屏" : "全屏"}
          </button>
          <button
            type="button"
            onClick={cycleRate}
            className="inline-flex min-h-14 min-w-[10rem] items-center justify-center gap-2 rounded-xl border-2 border-amber-600/80 bg-amber-950/90 px-6 text-industrial font-semibold text-amber-50 shadow-lg backdrop-blur hover:bg-amber-900/90 active:scale-[0.98]"
            aria-label={`播放速度 ${rateLabel}`}
          >
            <Gauge className="size-8 shrink-0" />
            倍速 {rateLabel}
          </button>
        </div>
      </div>
    );
  },
);
