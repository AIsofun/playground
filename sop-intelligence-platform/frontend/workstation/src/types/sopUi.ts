/**
 * 工位 UI 视图模型（对齐 docs/module-specs/workstation-ui.md §2.1）
 * SOPStep 来自 GET /api/sop/{id} 的简化形态。
 */
export type SOPStep = {
  step_id: number;
  keyframe_index: number;
  /** §6.1 优先：直接 seek（秒） */
  keyframe_time_sec?: number;
  title: string;
  bullets: string[];
  safety_note?: string;
};

export type MockSOPBundle = {
  sop_id: string;
  /** 用于 keyframe_index → time 的演示回退（§6.1） */
  assumed_fps: number;
  steps: SOPStep[];
  /** 演示用公开样本流（非 HLS，仅本地 DoD 验证） */
  demo_video_src: string;
};
