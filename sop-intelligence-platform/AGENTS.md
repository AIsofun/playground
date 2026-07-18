# AGENTS.md — SOP 智脑 全局 AI 宪法

> **阅读优先级**：每次开始任何任务前，AI Agent 必须先读本文件，再读 `SPEC.md` 确认当前 Todo，最后读对应子目录的 `AGENTS.md` 获取局部约束。

---

## 一、项目定位（不得偏离）

本项目是 **SOP 智脑 — 动力电池装配 SOP 智能化平台**。  
核心飞轮：**自动生成 SOP → 驱动合规监控 → 沉淀专属数据 → 微调专有模型 → 质量根因溯源**。  
战略边界：**只做动力电池装配场景**，不做通用视觉检测、不做排程优化、不做供应链协同。

---

## 二、代码分层规则（禁止违反）

本项目 `src/` 目录执行**严格单向依赖**，违反者 CI 拒绝合并：

```
Layer 1: src/types/       ← 零外部依赖，只有 Pydantic 数据模型
Layer 2: src/config/      ← 仅依赖 types/
Layer 3: src/services/    ← 依赖 types/ + config/，含核心业务逻辑
Layer 4: src/adapters/    ← 依赖 types/ + config/，禁止含业务逻辑
Layer 5: src/api/         ← 可依赖所有层，禁止含业务逻辑
```

**禁止行为**：
- `types/` 中不得 import `services/` 或 `adapters/` 的任何内容
- `adapters/` 中不得写 if/else 业务判断，只做 I/O 封装
- `api/` 中不得直接操作数据库，必须经过 `services/` 或 `adapters/`
- 跨层反向引用（高层 import 低层的反向不算，低层 import 高层违规）

CI 工具：`import-linter`，配置见 `.importlinter`（待创建）。

---

## 三、edge_node/ 独立部署约束

`edge_node/` 部署于 NVIDIA Jetson Orin NX 16GB，与 `src/` 分层体系**相互独立**：

- **唯一共享**：`edge_node/fsm_runtime/` 可共享 `src/types/sop.py` 的类型定义（只读引用）
- **禁止**：`edge_node/` 中任何模块不得 import `src/services/` 或 `src/adapters/`
- **实时性约束**：主推理线程延迟目标 < 20ms，禁止在主线程做任何网络 I/O（gRPC 上传必须在独立线程）
- 详见 `edge_node/AGENTS.md`

---

## 四、AI 组件修改规则

### VLM Prompt 修改
1. 修改 `.ai/prompts/` 中的 Prompt 模板
2. 同步更新 `docs/module-specs/` 对应规格文档
3. 重新运行 `tests/harness/[模块]_eval/run_eval.py`，指标必须达标后方可提交

### 置信度阈值修改
- 阈值常量定义在 `src/config/vlm.py`（`CONF_LOW=0.4`, `CONF_HIGH=0.7`）
- 修改后必须同步更新 `docs/domain-logic.md` 中的说明
- 重跑 `tests/harness/compliance_eval/run_eval.py`

### 模型更新（TensorRT / QLoRA）
- 参照 `.ai/skills/tensorrt-int8.md` 或 `.ai/skills/qlora-tuning.md` 执行
- 禁止直接修改 `model_pipeline/` 脚本而不更新对应 Skill 文档

---

## 五、测试规则（TDD 2.0）

| 类型 | 路径 | 规则 |
|------|------|------|
| Eval Harness | `tests/harness/` | **先于实现存在**；AI 输出质量评估；无 Harness 达标不得合并 |
| 单元测试 | `tests/unit/` | pytest，纯逻辑，禁止 I/O；函数级正确性 |
| 集成测试 | `tests/integration/` | Docker Compose 环境；含真实 Kafka / MinIO |
| 性能基准 | `tests/performance/` | 每次变更必跑；回归即阻断合并 |

**硬性质量门禁**（来自 `docs/eval-standards.md`）：
- SOP 生成：步骤完整性 > 0.90，关键帧准确率 > 0.85
- 合规监控：Recall > 0.95，FPR < 5%，UNCERTAIN 比例 < 15%
- 异常检测：AUROC > 0.90
- 质量根因：根因命中率 > 0.80

---

## 六、Git 提交规范

```
<type>(<scope>): <subject>

type: feat | fix | refactor | test | docs | chore
scope: types | config | sop-engine | compliance | agents | edge | model | frontend | deploy
```

**禁止提交**：
- 未通过 Harness 的 AI 组件代码
- 含硬编码密钥、IP 地址、数据库密码的文件
- 直接修改 `docs/domain-logic.md` 中的阈值而未同步更新 `src/config/`

---

## 七、每次开始新任务的标准流程

```
1. 读 SPEC.md，确认当前任务 Todo ID
2. 读本文件（已完成）+ [子目录]/AGENTS.md 了解局部约束
3. 读 docs/module-specs/[模块名].md 了解技术规格
4. 读 docs/domain-logic.md 确认业务规则（置信度阈值等）
5. 如涉及 AI 组件，先在 tests/harness/[模块]_eval/ 准备 eval_dataset 和 metrics.py
6. 实现代码，确保 src/ 分层依赖不违反 docs/architecture/layering.md
7. 运行 tests/harness/run_eval.py 直到指标达标
8. 运行 tests/performance/ 基准回归
9. 更新 SPEC.md，标记任务完成
```

---

## 八、子目录 AGENTS.md 位置索引

| 路径 | 管辖范围 |
|------|----------|
| `src/services/sop_engine/AGENTS.md` | VLM Prompt 修改必须同步 `.ai/prompts/` |
| `src/services/compliance/AGENTS.md` | 阈值修改必须同步 `docs/domain-logic.md` |
| `src/services/agents/AGENTS.md` | 所有 Agent 须含 Human-in-Loop 节点 |
| `edge_node/AGENTS.md` | 实时性约束，禁止网络 I/O 阻塞主线程 |
| `frontend/AGENTS.md` | 误报按钮防重提交，WebSocket 断线重连 |
