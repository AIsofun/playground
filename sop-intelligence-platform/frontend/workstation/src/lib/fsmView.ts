import type { SOPStep } from "@/types/sopUi";

export type WorkstationViewSlice = {
  currentStepId: number | null;
  workflowDone: boolean;
};

/**
 * workstation-ui.md §2.1：STEP_k → step_id = k；STEP_0 不高亮具体步；STEP_DONE → 完成态。
 */
export function fsmStateToView(
  state: string,
  steps: SOPStep[]
): WorkstationViewSlice {
  const maxId = steps.reduce((m, s) => Math.max(m, s.step_id), 0);
  if (state === "STEP_DONE") {
    return { currentStepId: null, workflowDone: true };
  }
  if (state === "STEP_0") {
    return { currentStepId: null, workflowDone: false };
  }
  const m = /^STEP_(\d+)$/.exec(state);
  if (!m) return { currentStepId: null, workflowDone: false };
  const id = Number(m[1]);
  if (id >= 1 && id <= maxId) return { currentStepId: id, workflowDone: false };
  return { currentStepId: null, workflowDone: false };
}

export function buildFsmOptions(stepCount: number): { label: string; value: string }[] {
  const opts = [{ label: "STEP_0（准备）", value: "STEP_0" }];
  for (let k = 1; k <= stepCount; k++) {
    opts.push({ label: `STEP_${k}`, value: `STEP_${k}` });
  }
  opts.push({ label: "STEP_DONE", value: "STEP_DONE" });
  return opts;
}
