# 模块规格：workstation_ui — 工位交互屏（SOP 播放 + FSM 联动 + HUD 告警）

> **对应 Todo**：`p1-workstation-ui`　**引入阶段**：Phase 1　**状态**：`completed`（2026-04-13）  
> **运行环境**：标准 PC 浏览器（Chrome / Edge）  
> **目标分辨率**：1080p 及以上，横屏布局  
> **技术栈**：Vite + React + Tailwind CSS + shadcn/ui（含 `lucide-react`、`framer-motion`）  
> **上游依赖**：`p1-sop-gen`（`SOPDocument` / `SOPStep`）、`p1-sop-fsm`（`FSMGraph` / 运行态 `STEP_n`）  
> **下游依赖**：`p1-compliance`（实时告警消息 / 字段预留）

---

## 一、目标与非目标

### 1.1 目标（MVP）

- 在 `frontend/workstation/` 构建**可演示、可扩展**的工位交互屏原型：
  - 播放 SOP 引导视频（工业现场可读、操作简单）
  - SOP 步骤列表与 FSM 当前状态**实时联动**：自动高亮当前步骤、保持居中可视
  - 违规/超时等事件以 **HUD** 形式叠加显示处理建议
  - 提供 **MockInterval** 演示模式，弱化对后端实时流稳定性的依赖

### 1.2 非目标（Phase 1 不做）

- 不做通用的视频素材管理、上传与转码体系
- 不做复杂的权限/多租户管理（留给 dashboard / SaaS 化阶段）
- 不在前端实现业务判定逻辑（仅展示与转发，不“替代”后端决策）

---

## 二、核心联动模型（SOP ↔ FSM ↔ UI）

### 2.1 SOP 与 FSM 的对齐

- **SOPStep**（来自 `GET /api/sop/{id}`）：
  - `step_id`: 1..N（与 steps 顺序一致）
  - `keyframe_index`: 用于定位关键帧（前端用于 seek）
  - 其他字段：标题/要点/安全提示等（以实际 SOPDocument 结构为准）

- **FSM 运行态状态**：
  - 状态字符串形如 `STEP_0`, `STEP_1` .. `STEP_N`, `STEP_DONE`
  - **映射规则（必须固定）**：`STEP_{k}` → 当前 SOP 步骤 `step_id = k`
    - `STEP_0` 表示未开始/准备态（UI 不高亮具体步骤）
    - `STEP_DONE` 表示完成态（UI 进入完成视图）

### 2.2 UI 行为（状态驱动）

- 当 FSM 当前状态变化时：
  - `InstructionList` 自动切换高亮到对应 `step_id`
  - 滚动容器自动滚动，使高亮项**保持在可视区域中心**
  - 主内容区（InstructionCard）切换到当前步骤详情
  - 若用户点击了某步骤，则播放器 `seek` 到该步骤对应关键帧位置

---

## 三、页面结构与布局（1080p 横屏）

### 3.1 Layout：Sidebar + Main Content Area

- **Sidebar（左）**
  - SOP 步骤列表（InstructionList）
  - 连接状态（WS / Polling）与当前 FSM 状态简览
  -（可选）演示模式开关（mock/real）

- **Main（右）**
  - SOPPlayer（视频播放器）
  - HUD Overlay（叠加层，显示超时/违规通知与建议）
  - 当前步骤详情（InstructionCard）

### 3.2 工业现场可用性约束（UI/UX）

- 字体基线不小于 24px（观看距离 > 1m）
- 交互控件避免“精细点击”（大按钮/大间距）
- 错误态禁止显示技术堆栈，只展示友好提示与可恢复操作（重试/刷新）

---

## 四、组件清单（MVP）

### 4.1 `SOPPlayer`

- **技术实现**：原生 `<video>` 或 Video.js（二选一，T03 固化）
- **必备能力**：
  - 点击 SOP 步骤时 `seek` 到对应 `keyframe_index`
  - 全屏切换（按钮）
  - 播放速度控制（0.5x / 1x / 1.25x / 1.5x / 2x）
- **对外接口（建议）**：
  - `seekToKeyframe(stepId | keyframeIndex)`
  - 事件：`onTimeUpdate`, `onRateChange`, `onFullscreenChange`

### 4.2 `InstructionList`（左侧步骤流）

- 展示：步骤号、标题（可选）、状态（未到/当前/已完成）
- 行为：
  - 当前步骤高亮 + 其余降暗
  - 高亮项保持居中可视（scroll container 内居中）
  - 点击步骤触发播放器 seek（同时可切换当前详情卡）

### 4.3 `InstructionCard`（当前步骤详情）

- 展示：当前步骤标题、要点、注意事项、关键帧标记（可选）
- 切换动画：使用 `framer-motion`，保证状态切换平滑、不抖动

### 4.4 `HudOverlay`（实时告警 HUD）

- 覆盖在视频上方，醒目但不破坏基础操作（必要区域支持穿透/避让）
- 告警类型（MVP）：
  - `TIMEOUT`：动作超时/犹豫提示 + 建议
  - `VIOLATION`：红色高优先级通知 + 处置建议
- 动画：入场/退场使用 `framer-motion`
- 堆叠策略（MVP 建议）：只展示“当前最高优先级的一条”，保留历史在侧栏列表（可选）

---

## 五、数据通信层（REST + WebSocket / Polling）

### 5.1 REST（T02 必接）

- `GET /api/sop/{id}`
  - 用途：加载 SOP 文档（步骤列表、关键帧索引等）
- `GET /api/fsm/{id}`
  - 用途：加载 FSM 图/快照（用于初始化与 Polling）

> **约束**：API Base URL 禁止硬编码，必须从 `VITE_API_BASE_URL` 读取。

### 5.2 实时机制（T04 必须：WebSocket 或 Polling）

#### 方案 A：WebSocket（优先）

- 连接：`VITE_WS_BASE_URL` + `/ws/workstation/{workstation_id}`（路径可随服务端调整）
- 最小消息类型（字段允许扩展）：
  - `FSM_STATE_UPDATE`：携带 `state_id`（如 `STEP_3`）及可选 `timestamp`
  - `COMPLIANCE_ALERT`：违规告警（T05 HUD）
  - `HESITATION_WARNING`：超时/犹豫提示（T05 HUD）
  - `SOP_SWITCH`：切换 SOP（重置 UI）
- 断线重连：指数退避（建议 `[1000, 2000, 4000, 8000, 16000]` ms），超过最大次数提示“连接断开，请刷新”

#### 方案 B：Polling（降级/备选）

- 轮询 `GET /api/fsm/{id}`（间隔建议 1s~2s，带退避与停止条件）
- 若恢复 WS，则停止 Polling（避免双源冲突）

### 5.3 ViewModel（前端统一状态）

- `currentStepId: number | null`（由 FSM `state_id` 映射得出）
- `steps: Array<{ stepId; title?; keyframeIndex?; status }>`
- `player: { isPlaying; rate; isFullscreen; currentTime }`
- `hud: { active?: { type; severity; title; suggestion; relatedStepId? } }`
- `connection: { mode: 'ws'|'poll'|'mock'; status: 'connected'|'reconnecting'|'disconnected' }`

---

## 六、`keyframe_index → time` 映射约定（seek 策略）

> 目的：当用户点击 SOP 步骤时，播放器可定位到“该步骤的关键帧”附近。

### 6.1 约定（MVP）

- SOP 数据必须提供以下之一（优先级从高到低）：
  1) `keyframe_time_sec`（直接 seek 到秒）
  2) `keyframe_index + fps`（`time = keyframe_index / fps`）
  3) 仅 `keyframe_index`：由前端使用 `ASSUMED_FPS`（默认 30）做近似映射（**仅演示可用**）

### 6.2 失败策略

- 若无法计算 time：不 seek，仅高亮步骤并提示“关键帧不可用”

---

## 七、演示用 Mock 环境（T06）

### 7.1 目标

- 在后端实时流不稳定或不可用时，仍能演示：
  - FSM 从 `STEP_1` 推进到 `STEP_DONE`
  - 指令流高亮/居中滚动
  - 播放器 seek（可使用近似映射）
  - HUD 告警（插入 TIMEOUT / VIOLATION）

### 7.2 `MockIntervalRunner` 设计

- 配置：
  - `stepIntervalMs`（每步推进间隔）
  - `injectTimeoutAtSteps?: number[]`
  - `injectViolationAtSteps?: number[]`
  - `loop?: boolean`
- 行为：
  - 定时推进 `state_id: STEP_1..STEP_N` → `STEP_DONE`
  - 在指定步骤触发 HUD 事件
  - 切换到 real 模式时必须清理定时器与事件队列

---

## 八、原子任务清单（T01–T06）

> 本清单为执行与验收的唯一依据；每个任务的 DoD 达成即视为完成。

### [x] T01：项目基建（Vite + Tailwind + shadcn/ui + lucide-react + framer-motion）

- **任务**：初始化 `frontend/workstation/`，配置 Tailwind 与 shadcn/ui，建立基础布局（Sidebar + Main Content Area），并引入 `lucide-react` 与 `framer-motion`。
- **DoD**：
  - 本地可启动并渲染布局骨架（1080p/2K 横屏无明显溢出）
  - `lucide-react` 与 `framer-motion` 在界面中有实际使用点（步骤高亮/HUD 动画）

### [x] T02：数据通信层（Fetch/Axios Hooks + REST 接口）

- **任务**：封装 `GET /api/sop/{id}` 与 `GET /api/fsm/{id}` 的数据访问 Hooks；实现统一错误态与超时策略。
- **DoD**：
  - Demo 页可拉取 SOP/FSM 并渲染到 UI
  - API Base URL 仅来自 `VITE_API_BASE_URL`，不硬编码

### [x] T03：工业级视频播放器（SOPPlayer：seek + 全屏 + 倍速）

- **任务**：实现 `SOPPlayer`，支持点击步骤 seek 到对应关键帧；具备全屏切换与播放速度控制。
- **DoD**：
  - 点击任一步骤可稳定跳转并继续播放
  - 全屏与倍速在 Chrome/Edge 可用，状态可回传给外层

### [x] T04：双联动指令流（Instruction List ↔ FSM 实时联动）

- **任务**：实现步骤列表与当前详情的联动；通过 **WebSocket 或 Polling** 接收 FSM 状态变化，驱动自动高亮与“居中滚动”。
- **DoD**：
  - 连续状态更新下高亮与内容同步、滚动稳定不抖动
  - WS 不可用时可降级 Polling（或固定 Polling 但需退避/停止条件）

### [x] T05：实时告警 HUD（TIMEOUT / VIOLATION）

- **任务**：在播放器上叠加 HUD；当 FSM 触发超时或违规时显示醒目通知与建议（字段/枚举按消息契约落地）。
- **DoD**：
  - 可通过 mock 或实时消息触发 HUD 展示与动画
  - HUD 视觉对比强、1080p 可读，且不影响核心播放操作

### [x] T06：演示用 Mock 环境（MockInterval）

- **任务**：实现 `MockIntervalRunner`，模拟 SOP 从第一步到最后一步的流转，支持插入超时/违规事件；并提供 mock/real 切换。
- **DoD**：
  - 后端不可用时依旧可完整演示联动与 HUD
  - 切换数据源时清理订阅/定时器，不产生重复事件

---

## 九、验收方式（建议）

- 浏览器：Chrome / Edge 最新稳定版
- 分辨率：1920×1080（必须通过），2560×1440（建议通过）
- 演示脚本：
  - mock 模式（`/demo`）：自动推进步骤 + 第 3 步注入 **TIMEOUT**；**VIOLATION** 由 Real 模式 WS `COMPLIANCE_ALERT` 或后续扩展 `injectViolationAtSteps` 覆盖
  - real 模式：拉取 SOP/FSM 并开始 WS 更新（若环境可用；Polling 为规格备选）

---

**status: completed**

**结案附录**：前端对外事件与入参汇总见 `docs/reports/workstation-ui-events-export.md`。

