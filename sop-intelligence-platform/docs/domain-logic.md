# 领域规则：SOP FSM、合规三档与阈值

本文档描述 **动力电池装配工位合规 MVP（`p1-compliance`）** 的领域语义：边缘/FSM 输出如何映射到合规三档、与服务端慢路径的衔接，以及与类型、配置、测试的交叉引用。

---

## 1. 数值真源（阈值）

**置信度阈值仅以代码为真源**：`src/config/vlm.py` 中的 `VLMSettings.CONF_LOW`、`VLMSettings.CONF_HIGH`（及模块级导出 `CONF_LOW`、`CONF_HIGH`），可通过环境变量覆盖，且受校验：`0 ≤ CONF_LOW < CONF_HIGH ≤ 1`。

本文档**不重复**默认数值；说明中写作 **`CONF_LOW`**、**`CONF_HIGH`** 表示「当前运行配置从 `vlm.py` 解析得到的值」。产品说明若需示例，可写「默认与 `vlm.py` 出厂默认一致」，避免与代码漂移。

---

## 2. 合规三档：`COMPLIANT` / `UNCERTAIN` / `VIOLATION`

设 \(s \in [0,1]\) 为**边缘侧对「当前观测与当前 FSM 期望是否一致」给出的标量置信度**（来源可为动作分类器 + 与期望动作的对齐得分等，由 `edge_node`/`fsm_runtime` 定义具体计算，但**输出必须可归一化到 \([0,1]\)** 以便统一分档）。

| 档位 | 区间（闭开约定） | MVP 行为 |
|------|------------------|----------|
| **COMPLIANT** | \(s \ge\) **`CONF_HIGH`** | 高置信合规：边缘**不上传帧**；本地日志可选；不触发服务端 VLM。 |
| **UNCERTAIN** | **`CONF_LOW`** \(\le s <\) **`CONF_HIGH`** | 不确定：边缘**截帧经 gRPC 上送**服务端；服务端调用 VLM 复核后再做最终合规判定与事件发布。 |
| **VIOLATION** | \(s <\) **`CONF_LOW`** **或**命中「关键规则」硬违规 | 明确违规：边缘**可直接告警**（Kafka/路由/工位 WS，实现以 `compliance-service` 规格为准）；**不等待 VLM** 以降低延迟；是否仍上传帧由实现版本决定，**MVP 默认以上报告警为主、可不送 VLM**。 |

**闭开约定说明**：与 `src/services/compliance/AGENTS.md` 中「低于 `CONF_LOW` = VIOLATION」「高于（含边界实践上与 `CONF_HIGH` 对齐）合规」一致；**`s == CONF_LOW` 归入 `UNCERTAIN`**；**`s == CONF_HIGH` 归入 `COMPLIANT`**（与 `vlm.py` 中 `CONF_HIGH` 文档「at or above」一致）。

**「关键规则」**：不依赖 \(s\) 的硬条件（如安全互锁、顺序颠倒、禁区触发等），一旦触发即 **`VIOLATION`**，即使 \(s\) 处于中间带。具体规则表由 `docs/module-specs/edge-node.md` / FSM 规格维护；本文件只定义档位语义。

---

## 3. 与 FSM / 动作观测类型的关系

- 服务端 FSM 与 `ActionDetectionVerdict`（`MATCH` / `MISMATCH` / `UNCERTAIN`）见 `src/types/sop.py` 及 `docs/module-specs/sop-fsm.md`。  
- **动作观测的 `UNCERTAIN`**（无法对齐期望动作）在边缘应**收敛**为合规三档中的 **`UNCERTAIN` 或 `VIOLATION`**（由 \(s\) 与关键规则决定），**不得**与「合规三档」同名枚举混用时不加注释。

---

## 4. 大小模型分歧与数据湖（概念）

当边缘已给出某一档（尤其经 VLM 复核前后对比时），**边缘结论与 VLM 结论不一致**且满足 `src/services/compliance/AGENTS.md` 第三节的分歧模式时，视为**分歧样本**，应写入数据湖（MinIO 对象 + PostgreSQL 元数据），`source: "auto"`。  
与现场 **「误报」人工入湖**（`routes/feedback.py`：`POST /feedback/false-positive`，应用前缀见 `docs/architecture/layering.md`）的关系见 `docs/module-specs/compliance-service.md`。

---

## 5. 与产品规划文档、配置注释的差异与「以何为准」

| 来源 | 问题 |
|------|------|
| `plan/sop-intelligence-platform.md` 第四章表格 | 「不确定区间」写作「0.4–0.6」、`edge_node` 小节写作「0.4–0.6」；与 **`CONF_HIGH` 默认 0.7** 不一致。 |
| `src/config/vlm.py` 中 `CONF_LOW` 的字段说明 | 英文 docstring 写「Frames **below** this are **UNCERTAIN**…」，与 **`CONF_LOW` 作为不确定区下界**（低于为 `VIOLATION`）矛盾。 |

**以何为准（本 Step SSOT）**：

1. **分档区间与语义**：以 **本文件 `docs/domain-logic.md`** 与 **`src/services/compliance/AGENTS.md`** 为准（二者一致：`CONF_LOW` 为不确定区下界；`CONF_HIGH` 为合规区下界）。  
2. **默认数值**：仅以 **`src/config/vlm.py`** 为准（文档不抄数字）。  
3. **`plan/sop-intelligence-platform.md`**：叙事与架构仍有效；**不确定区间数值表述**应理解为历史简写，**工程含义 = \([CONF\_LOW, CONF\_HIGH)\)**。

**待代码/文档后续 Step 对齐**（本步不改代码）：

- [ ] 修正 `src/config/vlm.py` 中 **`CONF_LOW` docstring**，与分档语义一致。  
- [ ] 可选：将 `plan/sop-intelligence-platform.md` 中「0.4–0.6」改为「\[CONF_LOW, CONF_HIGH)」或「见 domain-logic」。

---

## 6. 相关路径

| 主题 | 路径 |
|------|------|
| 阈值与 VLM HTTP 超时等 | `src/config/vlm.py` |
| 合规服务契约 | `docs/module-specs/compliance-service.md` |
| Harness 门禁 | `docs/eval-standards.md` |
| 分层与 Topic / 桶名引用 | `docs/architecture/layering.md` |
| 子模块强制规则 | `src/services/compliance/AGENTS.md` |
| 架构叙事 | `plan/sop-intelligence-platform.md` 第四章「实时合规监控」、`edge_node` 与 `services/compliance_service/` 小节 |

---

## 7. 变更流程（阈值）

修改 `CONF_LOW` / `CONF_HIGH` 须同步更新本文件对区间的文字说明（不含硬编码数字）、执行 `tests/harness/compliance_eval/run_eval.py` 并满足 `docs/eval-standards.md` 中的合规门禁。详见根目录 `AGENTS.md` 与 `src/services/compliance/AGENTS.md`。
