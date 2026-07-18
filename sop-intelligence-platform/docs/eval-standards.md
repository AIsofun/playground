# 各模块 Harness 与质量基准

本文档定义各模块 **Eval Harness** 及关键质量门禁；细分指标以各 `tests/harness/<module>_eval/metrics.py` 实现为准。

**全局流程**：见根目录 `AGENTS.md`（Harness 先于实现、达标方可合并）。

---

## 1. 合规监控（`p1-compliance`）

**Harness 路径**：`tests/harness/compliance_eval/`（`run_eval.py`、`metrics.py`）  
**领域规则与分档**：`docs/domain-logic.md`  
**阈值数值真源**：`src/config/vlm.py`（`CONF_LOW`、`CONF_HIGH`）；**本文件不写入具体默认数字**，避免与代码漂移。

### 1.1 门禁指标（必须同时满足）

| 指标 | 要求 | 说明 |
|------|------|------|
| **Recall** | **> 0.95** | 真违规被正确检出（含经 VLM 复核后最终判为违规的样本）。 |
| **FPR**（False Positive Rate） | **< 5%** | 合规被误判为违规的比例上限。 |
| **`UNCERTAIN` 比例** | **< 15%** | 边缘（或等价前置级）输出为 `UNCERTAIN` 的样本占评估集比例上限；超过则说明阈值区间过宽或场景失配，须回滚阈值或改数据/模型而非放宽门禁。 |

> 口径与 `src/services/compliance/AGENTS.md`、根 `AGENTS.md` 表格一致。

### 1.2 数据集形态（Harness）

为贴近实机 **Fast Path → Slow Path** 链路，评估集须可映射到以下形态之一或组合（在 `compliance_eval` README 或 `metrics.py` 中注明实际采用）：

| 形态 | 说明 |
|------|------|
| **帧级** | 单张 JPEG + 元数据（`workstation_id`、`sop_step`、边缘 \(s\)、可选 FSM 状态）；用于 VLM 复核与分档统计。 |
| **片段级** | 短片段（若干帧或固定窗口）对应单一步骤；标签为该窗口的最终合规/违规真值；用于端到端 Recall/FPR。 |

**标签来源**：可含人工标注违规/合规、合成边界样本；**`UNCERTAIN` 比例**在统计时以领域档 **`UNCERTAIN`** 为准（见 `docs/domain-logic.md`），与 `src/types/sop.py` 中 `ActionDetectionVerdict.UNCERTAIN` 区分统计口径时在 Harness 文档中说明。

### 1.3 相关路径

| 路径 | 用途 |
|------|------|
| `tests/harness/compliance_eval/run_eval.py` | 入口脚本 |
| `tests/harness/compliance_eval/metrics.py` | Recall / FPR / UNCERTAIN 比例等 |
| `docs/module-specs/compliance-service.md` | 契约与数据面 |
| `.ai/prompts/vlm-anomaly-check.txt` | VLM 复核 Prompt |

---

## 2. 其他模块（占位）

以下模块的门禁与数据集要求在原 `SPEC.md` / 对应 `docs/module-specs/*.md` 中已有摘要，详细指标待各 Harness 目录补齐后与本节合并：

- **SOP 生成**：步骤完整性、关键帧准确率等（见 `tests/harness/sop_gen_eval/`）。  
- **FSM**：见 `docs/module-specs/sop-fsm.md` 与 `tests/harness/` 规划。  
- **异常检测 / 根因**（Phase 2+）：`docs/eval-standards.md` 将随 Harness 扩展增量更新。

---

## 3. 变更原则

- 修改 **合规门禁数值** 须同步 `docs/domain-logic.md`、`src/services/compliance/AGENTS.md` 及根 `AGENTS.md` 中引用，并重新跑通 `compliance_eval`。  
- **阈值数字** 仅在 `src/config/vlm.py` 定义；本文件只保留不等式与比例要求。
