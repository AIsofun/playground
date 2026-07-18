import { useCallback, useEffect, useRef } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import type { SOPStep } from "@/types/sopUi";

type InstructionListProps = {
  steps: SOPStep[];
  currentStepId: number | null;
  workflowDone: boolean;
  onStepClick: (step: SOPStep) => void;
};

/**
 * T04：步骤列表；currentStepId 变化时平滑滚动至可视区居中。
 */
export function InstructionList({
  steps,
  currentStepId,
  workflowDone,
  onStepClick,
}: InstructionListProps) {
  const itemRefs = useRef<Map<number, HTMLLIElement>>(new Map());

  const setItemRef = useCallback((stepId: number, el: HTMLLIElement | null) => {
    if (el) itemRefs.current.set(stepId, el);
    else itemRefs.current.delete(stepId);
  }, []);

  useEffect(() => {
    if (workflowDone) {
      const last = steps[steps.length - 1];
      if (last) {
        const el = itemRefs.current.get(last.step_id);
        requestAnimationFrame(() => {
          el?.scrollIntoView({ behavior: "smooth", block: "center" });
        });
      }
      return;
    }
    if (currentStepId == null) return;
    const el = itemRefs.current.get(currentStepId);
    requestAnimationFrame(() => {
      el?.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  }, [currentStepId, workflowDone, steps]);

  return (
    <ScrollArea className="min-h-0 flex-1">
      <ol className="space-y-2 p-4 pr-3">
        {steps.map((step) => {
          const isCurrent = !workflowDone && currentStepId === step.step_id;
          const dimmed = !isCurrent;
          return (
            <li
              key={step.step_id}
              ref={(el) => setItemRef(step.step_id, el)}
              className={cn(
                "rounded-xl border-2 transition-opacity duration-300",
                dimmed ? "opacity-40" : "opacity-100",
                isCurrent
                  ? "border-emerald-400/80 bg-emerald-500/15 shadow-[0_0_0_0_rgba(52,211,153,0.5)] animate-breathe"
                  : "border-border/80 bg-secondary/30"
              )}
            >
              <button
                type="button"
                onClick={() => onStepClick(step)}
                className="w-full px-4 py-4 text-left text-industrial font-semibold text-foreground"
              >
                <span className="mr-2 font-mono text-base text-muted-foreground">
                  #{step.step_id}
                </span>
                {step.title}
              </button>
            </li>
          );
        })}
      </ol>
    </ScrollArea>
  );
}
