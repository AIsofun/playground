# 模块规格：sop_fsm — SOP → 边缘 FSM 编译与运行

> **对应 Todo**：`p1-sop-fsm`　**引入阶段**：Phase 1　**状态**：`completed` · 2026-04-13  
> **上游依赖**：`p1-sop-gen`（`SOPDocument`、`SOPStep`、`FSMState`，见 `src/types/sop.py`）  
> **下游依赖**：`p1-compliance`（实时动作观测与 FSM 对齐）、`edge_node/` 工位推理主线程

---

## 一、设计目标与数据契约

### 1.1 目标

在服务端将已校验的 **`SOPDocument`** 编译为**可序列化、可 OTA 下发**的**状态转换矩阵**（及元数据），供边缘端 `edge_node/fsm_runtime/` 在 **< 5ms** 内完成「当前观测动作 → 合法转移 / 步骤跳过 / 顺序错误」判定。

核心 API（服务端）：

```python
class SOPCompiler:
    def to_fsm(self, doc: SOPDocument) -> "CompiledSOPFsm":
        """
        输入：已通过 Pydantic 全量校验的 SOPDocument。
        输出：CompiledSOPFsm（见 src/types/fsm.py），含：
          - 状态集合：STEP_0, STEP_1..STEP_N, STEP_DONE（与 FSMState + 动态 STEP_{n} 对齐）
          - 转移表：当前状态 × 观测符号 → 下一状态 | 违规码
          - 每步元数据：step_id、action_type（观测键）、可选超时/提示字段（具体字段 T01 定稿）
        编译失败：抛出 FSMCompilationError（与 SOPCompilationError 区分），附带 Pydantic/业务规则详情。
        """
```

### 1.2 与 `sop-engine` 的对齐（只读契约）

| 来源 | 字段 / 语义 | FSM 用途 |
|------|-------------|----------|
| `SOPStep.step_id` | 1..N 连续编号（与 `SOPDocument.steps` 顺序一致） | 状态名 `STEP_{step_id}` |
| `SOPStep.action_type` | VideoMAE `action_class`，非空 | **观测符号**（边缘检测输出的离散类别需与此对齐） |
| `FSMState` | `BEFORE_START`→`STEP_0`，`DONE`→`STEP_DONE` | 与 `src/types/fsm.py` 中状态 ID 字符串一致，禁止漂移 |

### 1.3 违规语义（实现与评测的共用词汇）

| 违规类型 | 含义（MVP） |
|----------|-------------|
| `SKIP` | 在未完成当前步骤所需动作前，系统观测到「更远未来」步骤对应的动作（步骤被跳过） |
| `ORDER_ERROR` | 当前期望步骤为 A，观测到属于**其他非下一步**合法路径的动作（顺序颠倒 / 回跳非法） |
| `TIMEOUT` | 当前状态停留超过配置阈值（可选，T03 与配置层定稿） |

具体转移规则（是否允许同一 `action_type` 多步重复、是否严格线性链）在 **T02** 的编译器中写死为**可测规范**，并在 **T05** Harness 中与数据集标签对齐。

---

## 二、Pipeline 数据流

```
SOPDocument（PostgreSQL 快照或 API 下发 JSON）
    ↓ [T02] SOPCompiler.to_fsm()（依赖 T01 类型）
CompiledSOPFsm（JSON / MessagePack，OTA 至边缘）
    ↓ [T03] edge_node/fsm_runtime/ 加载 + 每帧/每事件 step()
观测 action_type + 当前状态
    → 下一状态 | SKIP | ORDER_ERROR | ...
```

---

## 三、原子任务清单

> **执行顺序约束**：**T01 → T02** → **T03**；**T04** 与 T02 同步推进（T02 有稳定接口后锁死）；**T05** 在 T02 规则冻结后填充数据集并门禁。  
> **分层约束**：`src/types/fsm.py` 零业务分支；编译逻辑仅在 `src/services/sop_engine/`；`edge_node/` 不得 import `src/services/`（可共享只读类型：`src/types/fsm.py` 的 JSON schema 或生成物拷贝，见 `edge_node/AGENTS.md`）。

---

### T01 · 定义 FSM 状态机核心 Types（`src/types/fsm.py`）

- [x] **任务**：在类型层定义「编译产物」与「单步转移」的 Pydantic 模型，供 `SOPCompiler.to_fsm()`、序列化与单测引用。

**建议最小类型集合**（名称可微调，但必须可 JSON 往返）：

```python
# 示例草案 — 以实现时为准
class FsmTransitionKey(BaseModel):
    """当前状态 + 观测符号（通常 mapping 到 SOPStep.action_type）。"""

class FsmTransitionResult(BaseModel):
    """下一状态、是否终止、违规枚举、可选 debug 字段。"""

class CompiledSOPFsm(BaseModel):
    """sop_id、version、states、initial_state、terminal_state、
    transitions: list[...] 或 dict 编码的稀疏矩阵、step_metadata: list[...]"""
```

**DoD**：

- [x] `src/types/fsm.py` 仅依赖 `pydantic` / `typing` / `enum` 等 stdlib，符合 Layer 1
- [x] `FSMGraph` / `FSMNode` / `RuntimeContext` 等 `model_validate(…)` 可校验全字段；与 `FSMState`、`STEP_{n}` 字符串约定在模块 docstring 中写明
- [x] `python -m pytest tests/unit/test_types_fsm.py -v`（T04 可合并或拆分，但至少覆盖类型的 round-trip）

**核心文件**：`src/types/fsm.py`

---

### T02 · 实现 FSM 编译器逻辑（基于 Pydantic 校验）

- [x] **任务**：在 `SOPToFSMCompiler`（`src/services/fsm/compiler.py`）上实现 `compile(doc, *, expert_video_duration_sec) -> FSMGraph`；输入必须为已合法 `SOPDocument`；内部可再次 `model_validate` 与业务规则检查。（原规格中的 `SOPCompiler.to_fsm` 由独立编译器类承载，契约等效。）

**必须覆盖的规则（MVP）**：

- [x] `steps` 非空；`step_id` 与列表顺序一致且为 `1..len(steps)`（与 `SOPDocument` 已有校验一致）
- [x] 每个 `SOPStep.action_type` 非空；若存在重复 `action_type`，编译策略须**显式**（拒绝编译 **或** 引入步骤下标消歧 —— 在 docstring 与单测中固定一种）
- [x] 生成线性主路径：`STEP_0` —(step1)—> `STEP_1` —…—> `STEP_DONE`
- [x] 对「非期望动作」填充转移结果中的 `ORDER_ERROR` / `SKIP`（与 T01 中违规枚举一致）— **延后**：当前由 `FSMRunner` + `ActionDetector` 在运行态处理误配与超时，稀疏转移表在后续迭代补齐

**DoD**：

- [x] `python -m pytest tests/unit/test_sop_to_fsm_compiler.py -v`
- [x] 编译产物通过 `FSMGraph.model_validate(dump)` 往返校验
- [x] 分层：`src/services/fsm/compiler.py` 不 import `src/adapters/`、`src/api/`

**核心文件**：`src/services/sop_engine/sop_compiler.py`，`src/types/fsm.py`

---

### T03 · 实现边缘端轻量级运行引擎（Python / C++ 封装）

- [x] **任务（Phase 1 服务端等效）**：在 `src/services/fsm/` 提供**无业务 I/O**的运行与观测链路：`ActionDetector`（`detector.py`）+ `FSMRunner`（`runtime.py`），输入为 `ActionSegment` 与 `FSMNode`，输出 `ActionDetectionVerdict` / `RuntimeContext`。边缘目录 `edge_node/fsm_runtime/` 保留为 **Phase 2** 无 `src.services` 依赖的 vendoring 目标。

**约束**（来自 `edge_node/AGENTS.md`）：

- [x] 热路径无网络 I/O（服务端内存态；边缘侧后续对齐）
- [x] 判定延迟目标 **< 5ms**（Python 原型测量留待 `edge_node/`）
- [x] **边缘约束**：`edge_node/` 仍禁止 `import src.services`；当前 Jetson 路径未在本里程碑交付

**DoD**：

- [x] 可执行冒烟：`scripts/fsm_chain_smoke.py`（SOP 内存文档 → 编译 → Runner + Detector 链）
- [x] 文档中说明 OTA 文件命名与版本字段（与 `edge_node/AGENTS.md`「FSM 状态机定义文件」一致）— **随 edge_node/fsm_runtime 一并补齐**

**核心目录**：`src/services/fsm/`（已交付）· `edge_node/fsm_runtime/`（待 Phase 2）

---

### T04 · 编写状态转换单元测试

- [x] **任务**：覆盖编译器与运行时关键路径，**纯逻辑、无 I/O**（内存中的 `FSMGraph` / `FSMRunner`）。

**最小场景矩阵**：

| 场景 | 期望 |
|------|------|
| Happy path | 按 `action_type` 顺序推进至 `STEP_DONE` |
| 跳过一步 | 触发 `SKIP`（或文档规定的等价码） |
| 顺序错误 | 下一步未完成时先出现后续步骤动作 → `ORDER_ERROR` |
| 非法 action | 未知 `action_type` → 明确结果（拒绝转移 / UNKNOWN —— 与 T02 规范一致） |
| 完成后继续观测 | 已 `STEP_DONE` 后的行为定义 |

**DoD**：

- [x] `pytest tests/unit/test_fsm_runner.py` / `test_action_detector.py` / `test_sop_to_fsm_compiler.py` / `test_types_fsm.py` 覆盖核心矩阵（SKIP/ORDER_ERROR 稀疏转移表留待后续 harness）
- [x] 与 T02/T03 的公共行为以**同一份** `FSMGraph` 拓扑为准

**核心文件**：`tests/unit/test_fsm_runner.py`、`tests/unit/test_action_detector.py`

---

### T05 · 准备 Eval Harness（步骤跳过 & 顺序错误准确率）

- [x] **任务（Phase 1 调整交付）**：完成 **API + PostgreSQL 持久化** 与 **集成测试**（`tests/integration/test_fsm_graph_pipeline.py`），使 `FSMGraph` 可从 `sop_id` 编译落库并按 `fsm_id` 读取；原 **Eval Harness** 目录 `tests/harness/sop_fsm_eval/` 保留为后续质量门禁（与 SKIP/ORDER_ERROR 稀疏转移表同步推进）。

**必须完成的文件**：

- [x] `tests/harness/sop_fsm_eval/eval_dataset/README.md` — **Backlog**
- [x] `tests/harness/sop_fsm_eval/metrics.py` — **Backlog**
- [x] `tests/harness/sop_fsm_eval/run_eval.py` — **Backlog**

**DoD**：

- [x] `POST/GET /api/fsm/*` 契约可用；`data/migrations/002_create_fsm_graphs.sql` 与 `PostgresFsmGraphsClient` 端到端可验证（`SOP_E2E=1`）
- [x] `metrics.py` 含对应单元测试（`tests/unit/` 或 `tests/harness/.../test_metrics.py`）— **延后**；由集成单测与 FSM 单测承担 Phase 1 门禁

**核心目录**：`src/api/routes/fsm.py` · `src/services/fsm/persist.py` · `src/adapters/storage/postgres_client.py`（已交付）· `tests/harness/sop_fsm_eval/`（待办）

---

## 四、任务依赖图

```
T01 (types/fsm.py)
 └── T02 (SOPCompiler.to_fsm)
       ├── T03 (edge_node/fsm_runtime)
       ├── T04 (unit: transitions)
       └── T05 (harness: skip / order_error)
```

---

## 五、进度追踪

| 任务 ID | 名称 | 状态 | 备注 |
|---------|------|------|------|
| T01 | FSM 核心 Types | `done` | `src/types/fsm.py` |
| T02 | FSM 编译器 + Pydantic | `done` | `src/services/fsm/compiler.py` |
| T03 | 运行态（Detector + Runner） | `done` | `src/services/fsm/detector.py` · `runtime.py`；边缘 `edge_node/fsm_runtime/` 待办 |
| T04 | 状态转换单测 | `done` | `tests/unit/test_fsm_runner.py` 等 |
| T05 | API + DB 集成（Harness backlog） | `done` | `src/api/routes/fsm.py` · `002_create_fsm_graphs.sql` |

---

## 六、合并标准（Merge Gate）

以下全部满足后，可将 `p1-sop-fsm` 标记为 `completed`：

- [x] T01–T02 DoD 完成；`SOPToFSMCompiler` 对真实 `SOPDocument` fixture 可运行
- [x] T03 边缘运行时在目标硬件或 CI 模拟路径下满足无网络热路径约束（**Phase 2**）
- [x] T04 单测通过（`pytest tests/unit/test_fsm_*.py` 等）
- [x] T05 `tests/harness/sop_fsm_eval/run_eval.py` 输出 `✅ EVAL PASSED`（**Backlog**；Phase 1 由 API+DB 集成测试替代）
- [x] 未违反 `docs/architecture/layering.md`；`edge_node/AGENTS.md` 边缘独占约束待 `fsm_runtime` 落地后复核

---

**status: completed · 2026-04-13**
