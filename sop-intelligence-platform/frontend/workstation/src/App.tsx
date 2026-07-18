import { motion } from "framer-motion";
import { LayoutPanelLeft, MonitorPlay } from "lucide-react";

import { useAppNavigate } from "./navContext";

/**
 * 工位壳首页：布局与入口说明；完整交互与 T06 演示见 `/demo`（`DemoPage`）。
 */
export default function App() {
  const navigate = useAppNavigate();

  return (
    <div className="flex h-screen min-h-[1080px] w-full min-w-[1920px] flex-col overflow-hidden bg-[#121212] text-foreground">
      <header className="flex shrink-0 items-center justify-between gap-4 border-b border-border px-8 py-5">
        <div className="flex items-center gap-3">
          <LayoutPanelLeft className="size-8 text-emerald-400" aria-hidden />
          <div>
            <p className="text-industrial-lg font-bold tracking-tight">
              workstation_ui
            </p>
            <p className="text-base text-muted-foreground">
              工位交互屏 · Phase 1 壳与路由入口
            </p>
          </div>
        </div>
        <a
          href="/demo"
          className="shrink-0 rounded-xl border-2 border-emerald-500/60 bg-emerald-500/15 px-8 py-4 text-industrial font-bold text-emerald-50 shadow-lg hover:bg-emerald-500/25"
          onClick={(e) => {
            e.preventDefault();
            navigate("/demo");
          }}
        >
          打开完整演示（/demo）
        </a>
      </header>

      <main className="flex flex-1 flex-col items-center justify-center gap-8 px-8 text-center">
        <MonitorPlay className="size-20 text-emerald-500/80" aria-hidden />
        <motion.div
          className="max-w-3xl space-y-4"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35 }}
        >
          <p className="text-industrial font-semibold text-foreground">
            SOP 视频引导、FSM 联动、HUD 与 Mock/Real 切换均在演示页集成。
          </p>
          <p className="text-base leading-relaxed text-muted-foreground">
            操作说明与后续 HLS 工位配置见{" "}
            <span className="font-mono text-emerald-200/90">frontend/workstation/DEMO.md</span>
            ；模块规格见{" "}
            <span className="font-mono text-emerald-200/90">
              docs/module-specs/workstation-ui.md
            </span>
            。
          </p>
        </motion.div>
      </main>
    </div>
  );
}
