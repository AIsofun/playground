/**
 * T06 / workstation-ui.md §7.2：演示用定时推进 FSM，并可在指定步骤注入 HUD 事件。
 * 切换到 real 模式时务必调用 `stop()` 清理定时器。
 */
export type MockIntervalRunnerConfig = {
  /** 每步推进间隔（毫秒） */
  stepIntervalMs: number;
  /** 进入 `STEP_k` 时触发 TIMEOUT HUD（k 为 SOP step_id） */
  injectTimeoutAtSteps?: number[];
  /** 进入 `STEP_k` 时触发 VIOLATION HUD */
  injectViolationAtSteps?: number[];
  /** 是否在 STEP_DONE 后从 STEP_0 重新开始 */
  loop?: boolean;
  /** 最大步骤号（如 14 步则 sequence 含 STEP_1..STEP_14） */
  maxStepId: number;
  onFsmStateUpdate: (stateId: string) => void;
  onTimeoutAtStep?: (stepId: number) => void;
  onViolationAtStep?: (stepId: number) => void;
};

function buildSequence(maxStepId: number): string[] {
  return [
    "STEP_0",
    ...Array.from({ length: maxStepId }, (_, i) => `STEP_${i + 1}`),
    "STEP_DONE",
  ];
}

function stepNumberFromStateId(stateId: string): number | null {
  const m = /^STEP_(\d+)$/.exec(stateId);
  if (!m) return null;
  return Number.parseInt(m[1]!, 10);
}

export class MockIntervalRunner {
  private intervalId: ReturnType<typeof setInterval> | null = null;

  private clearIntervalSafe() {
    if (this.intervalId != null) {
      clearInterval(this.intervalId);
      this.intervalId = null;
    }
  }

  /** 停止定时器；在模式切换 / 卸载时必须调用。 */
  stop(): void {
    this.clearIntervalSafe();
  }

  /**
   * 立即发送 `STEP_0`，随后每隔 `stepIntervalMs` 发送下一步直至 `STEP_DONE`（默认不循环）。
   */
  start(config: MockIntervalRunnerConfig): void {
    this.stop();

    const {
      maxStepId,
      stepIntervalMs,
      loop = false,
      injectTimeoutAtSteps,
      injectViolationAtSteps,
      onFsmStateUpdate,
      onTimeoutAtStep,
      onViolationAtStep,
    } = config;

    const seq = buildSequence(maxStepId);

    const emitInjections = (stateId: string) => {
      const stepNum = stepNumberFromStateId(stateId);
      if (stepNum == null) return;
      if (injectTimeoutAtSteps?.includes(stepNum)) {
        onTimeoutAtStep?.(stepNum);
      }
      if (injectViolationAtSteps?.includes(stepNum)) {
        onViolationAtStep?.(stepNum);
      }
    };

    const emit = (index: number) => {
      const stateId = seq[index]!;
      onFsmStateUpdate(stateId);
      emitInjections(stateId);
    };

    emit(0);
    let nextIndex = 1;

    this.intervalId = setInterval(() => {
      if (nextIndex >= seq.length) {
        if (loop) {
          nextIndex = 0;
          emit(nextIndex);
          nextIndex = 1;
        } else {
          this.stop();
        }
        return;
      }

      emit(nextIndex);
      const justDone = seq[nextIndex] === "STEP_DONE";
      nextIndex += 1;

      if (justDone && !loop) {
        this.stop();
      }
    }, stepIntervalMs);
  }
}
