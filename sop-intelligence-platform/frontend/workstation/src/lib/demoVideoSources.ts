import { MOCK_SOP_DEMO } from "@/data/mockWorkstation";

/** 演示页视频候选顺序：环境变量 → 本地 public → 内置默认 CDN */
export function buildDemoVideoCandidates(apiOverride?: string | null): string[] {
  const fromEnv = import.meta.env.VITE_DEMO_VIDEO_URL?.trim();
  const fromApi = apiOverride?.trim();
  const ordered = [
    fromEnv,
    fromApi,
    "/demo-sop-guide.mp4",
    MOCK_SOP_DEMO.demo_video_src,
  ].filter((x): x is string => Boolean(x));
  return [...new Set(ordered)];
}
