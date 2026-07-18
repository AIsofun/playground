import { AnimatePresence, motion } from "framer-motion";
import type { SOPStep } from "@/types/sopUi";

type InstructionCardProps = {
  step: SOPStep | null;
  /** STEP_DONE：完成视图 */
  workflowComplete?: boolean;
  className?: string;
};

const cardVariants = {
  initial: { opacity: 0, x: 40, scale: 0.97 },
  animate: {
    opacity: 1,
    x: 0,
    scale: 1,
    transition: { duration: 0.32, ease: [0.22, 1, 0.36, 1] },
  },
  exit: {
    opacity: 0,
    x: -30,
    scale: 0.98,
    transition: { duration: 0.2, ease: [0.4, 0, 1, 1] },
  },
};

const listVariants = {
  initial: { opacity: 0, x: -6 },
  animate: (i: number) => ({
    opacity: 1,
    x: 0,
    transition: { delay: i * 0.04, duration: 0.2, ease: [0.22, 1, 0.36, 1] },
  }),
};

/**
 * 当前步骤详情卡：AnimatePresence mode="wait" 避免进出叠化闪烁。
 */
export function InstructionCard({ step, workflowComplete, className }: InstructionCardProps) {
  return (
    <div
      className={`min-h-[14rem] rounded-2xl border border-slate-700 bg-slate-900/80 p-6 shadow-inner ${className ?? ""}`}
    >
      <AnimatePresence mode="wait" initial={false}>
        {workflowComplete ? (
          <motion.div
            key="done"
            variants={cardVariants}
            initial="initial"
            animate="animate"
            exit="exit"
            className="space-y-3 text-center"
          >
            <p className="text-industrial-lg font-bold text-emerald-300">工序已完成</p>
            <p className="text-industrial text-slate-300">
              当前工单 SOP 已全部执行，请等待质检或下一工单下发。
            </p>
          </motion.div>
        ) : step ? (
          <motion.div
            key={step.step_id}
            variants={cardVariants}
            initial="initial"
            animate="animate"
            exit="exit"
            className="space-y-4"
          >
            <div className="flex flex-wrap items-baseline gap-3">
              <span className="rounded-lg bg-indigo-600/30 px-3 py-1 text-industrial font-bold text-indigo-200">
                步骤 {step.step_id}
              </span>
              <h2 className="text-industrial-lg font-bold tracking-tight text-white">
                {step.title}
              </h2>
            </div>
            <ul className="space-y-2">
              {step.bullets.map((b, i) => (
                <motion.li
                  key={`${step.step_id}-b-${i}`}
                  custom={i}
                  variants={listVariants}
                  initial="initial"
                  animate="animate"
                  className="flex gap-3 text-industrial text-slate-200"
                >
                  <span className="mt-1.5 size-2 shrink-0 rounded-full bg-emerald-400" />
                  {b}
                </motion.li>
              ))}
            </ul>
            {step.safety_note ? (
              <motion.p
                initial={{ opacity: 0 }}
                animate={{ opacity: 1, transition: { delay: 0.12, duration: 0.2 } }}
                className="rounded-xl border border-amber-700/50 bg-amber-950/40 px-4 py-3 text-industrial text-amber-100"
              >
                <span className="font-semibold text-amber-300">安全提示：</span>
                {step.safety_note}
              </motion.p>
            ) : null}
          </motion.div>
        ) : (
          <motion.p
            key="empty"
            variants={cardVariants}
            initial="initial"
            animate="animate"
            exit="exit"
            className="text-industrial text-slate-500"
          >
            请从左侧选择步骤
          </motion.p>
        )}
      </AnimatePresence>
    </div>
  );
}
