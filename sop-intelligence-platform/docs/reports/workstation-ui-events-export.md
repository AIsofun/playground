# workstation_ui — 对外事件与入参契约导出

> **范围**：`frontend/workstation/` 当前实现（`p1-workstation-ui` 结案版）。  
> **说明**：本仓库工位前端以 **React 回调 props** 与 **WebSocket JSON 的 `type` 字段** 为主要对外契约；**未**使用 `window.dispatchEvent` / `CustomEvent`，因此不存在字面量形如 `VIOLATION_CONFIRMED` 的浏览器自定义事件名。工人确认 HUD 对应组件回调 **`onAcknowledge`**；若后端遥测需要统一事件名，建议别名 **`HUD_ACKNOWLEDGED`**（语义等价，需在集成层自行映射）。

---

## 一、WebSocket → 前端（服务端推送）

连接 URL：`{VITE_WS_BASE_URL}/ws/workstation/{workstation_id}`（见 `useWorkstationWs`）。

消息体为 JSON，根级 **`type`** 决定分发（`src/ws/dispatchWorkstationMessage.ts`）。

| `type`（事件名） | 含义 | 入参（JSON 字段） | 前端处理 |
|------------------|------|-------------------|----------|
| `FSM_STATE_UPDATE` | FSM 状态推进 | **`state_id`** `string`（如 `STEP_3`、`STEP_DONE`）；可选 **`timestamp`** `string` | 更新运行态；`DemoPage` 驱动列表 / seek |
| `COMPLIANCE_ALERT` | 合规违规告警 | 可选 **`title`**、**`suggestion`** `string`；可选 **`related_step_id`** `number`；允许扩展字段 | 映射为 **VIOLATION** HUD（`HudOverlay`） |
| `HESITATION_WARNING` | 犹豫 / 超时 | 同上 | 映射为 **TIMEOUT** HUD |
| `SOP_SWITCH` | 切换 SOP | 规格预留；当前分发器 **未解析**，可扩展 | 应在扩展后重置步骤与播放器 |

未识别或非 JSON 报文：静默忽略（不展示技术堆栈，符合 `frontend/AGENTS.md`）。

---

## 二、Hooks 对外回调（订阅式「事件」）

### 2.1 `useWorkstationWs(workstationId, options)`

| 回调名（option 字段） | 触发条件 | 入参类型 |
|------------------------|----------|----------|
| `onFsmStateUpdate` | 收到 `FSM_STATE_UPDATE` 且 `state_id` 合法 | `FsmStateUpdateMessage`：`{ type, state_id, timestamp? }` |
| `onComplianceAlert` | 收到 `COMPLIANCE_ALERT` | `ComplianceAlertMessage`（含扩展索引签名） |
| `onHesitationWarning` | 收到 `HESITATION_WARNING` | `HesitationWarningMessage` |

连接状态枚举：`idle` | `connecting` | `connected` | `reconnecting` | `disconnected`（非回调，为 hook 返回值 `status`）。

---

## 三、UI 组件回调（父组件订阅）

### 3.1 `HudOverlay`

| 回调名 | 语义（建议遥测别名） | 入参 |
|--------|----------------------|------|
| `onAcknowledge` | 工人已读告警并关闭 HUD（别名建议：`HUD_ACKNOWLEDGED`） | `()` 无参 |

当前 HUD 载荷类型（props `hud`）：`HudActivePayload` = `HudTimeoutPayload | HudViolationPayload`（`src/types/workstation.ts`），字段包括 `type`、`title`、`suggestion`、`relatedStepId?`。

### 3.2 `InstructionList`

| 回调名 | 语义 | 入参 |
|--------|------|------|
| `onStepClick` | 用户点击某 SOP 步骤 | `(step: SOPStep)` |

### 3.3 `SOPPlayer`

| 回调名 | 语义 | 入参 |
|--------|------|------|
| `onTimeUpdate` | 播放进度 | `(t: number)` 当前秒 |
| `onRateChange` | 倍速变化 | `(rate: number)` |
| `onFullscreenChange` | 全屏状态 | `(fs: boolean)` |

`ref` 命令式 API：`seekToKeyframe(keyframeIndex: number)`（非事件，为方法）。

---

## 四、Mock 演示（T06）

### 4.1 `MockIntervalRunner.start(config)`

| 回调名 | 语义 | 入参 |
|--------|------|------|
| `onFsmStateUpdate` | 每次推进发送等价 WS 的 FSM 状态 | `(stateId: string)` |
| `onTimeoutAtStep` | 命中 `injectTimeoutAtSteps` | `(stepId: number)` |
| `onViolationAtStep` | 命中 `injectViolationAtSteps`（当前 `/demo` 未接 UI，可接 VIOLATION HUD） | `(stepId: number)` |

---

## 五、路由 / 导航（应用内）

| 机制 | 说明 |
|------|------|
| `useAppNavigate()` | 返回 `(to: "/" \| "/demo") => void`，封装 `history.pushState`（`src/navContext.tsx`） |

无全局事件名；仅为函数调用。

---

## 六、与规格示例名的对照

若集成文档或 MES 需要使用 **大写下划线事件名**，可与上表建立映射，例如：

| 集成侧事件名（建议） | 实际来源 |
|----------------------|----------|
| `FSM_STATE_UPDATE` | WS `type` 或 `MockIntervalRunner.onFsmStateUpdate` |
| `COMPLIANCE_ALERT` | WS `type` |
| `HESITATION_WARNING` | WS `type` |
| `HUD_ACKNOWLEDGED` | `HudOverlay.onAcknowledge()` 触发时由父组件转发 |
| `SOP_STEP_CLICKED` | `InstructionList.onStepClick` |

**不存在**：`VIOLATION_CONFIRMED`（当前代码未定义）；违规确认与超时确认统一为 **`onAcknowledge`**。

---

**文档版本**：与 `p1-workstation-ui` 结案提交一致；后续增加误报按钮、Kafka 等时再增量更新本表。
