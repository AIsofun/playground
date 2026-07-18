# 工位屏（workstation_ui）演示说明

本文档说明如何在本地运行 **Mock / Real** 演示闭环，以及如何为后续 **产线工位 HLS** 接入做准备。规格对齐见 `docs/module-specs/workstation-ui.md` 与根目录 `frontend/AGENTS.md`（工位屏须使用 HLS 为正式能力）。

---

## 一、环境与启动

### 1.1 前置条件

- Node.js 18+（推荐 LTS）
- 已安装 [pnpm](https://pnpm.io/)（与 `package.json` 中 `packageManager` 字段一致）

### 1.2 安装依赖

在仓库内执行：

```bash
cd frontend/workstation
pnpm install
```

### 1.3 环境变量（可选）

复制示例文件并按需修改：

```bash
cp .env.example .env
```

| 变量 | 用途 | 演示是否必需 |
|------|------|----------------|
| `VITE_API_BASE_URL` | REST 根地址 | 仅 **Real** 模式需要 |
| `VITE_WS_BASE_URL` | WebSocket 根地址 | 仅 **Real** 模式需要 |
| `VITE_DEMO_VIDEO_URL` | 演示视频 mp4 地址（优先于内置与本地文件） | 可选（网络不可达外链时推荐配置） |

### 1.4 启动开发服务

```bash
pnpm dev
```

浏览器访问（端口以终端输出为准）：

- **首页（入口壳）**：`http://localhost:5173/`（说明 + 跳转 `/demo`；完整 T02/T06 在演示页）
- **完整演示页（T06）**：`http://localhost:5173/demo`

> 路由由 `src/ClientRouter.tsx` 通过 `history.pushState` 实现；直接刷新 `/demo` 需依赖 Vite 开发服务器对 SPA 的回退（默认已支持）。

---

## 二、Mock 演示（无需后端）

### 2.1 进入演示页

1. 启动 `pnpm dev`。
2. 打开 `http://localhost:5173/demo`（或从首页点击 **「完整演示」**）。

### 2.2 界面说明

- **左侧 300px**：SOP 步骤列表（`InstructionList`）、数据源模式、连接状态摘要。
- **右侧主区**：`SOPPlayer`（视频 + 全屏 / 倍速）、`InstructionCard`（当前步骤详情）。
- **右下角**：Mock 模式下为绿色 **「演示模式」** 提示条；Real 模式下为 **WebSocket 连接状态** HUD。

### 2.3 数据源开关

侧栏顶部两个大按钮：

| 按钮 | 行为 |
|------|------|
| **Mock 演示** | 使用 `src/data/mockWorkstation.ts` 中的 `MOCK_SOP_DEMO`；**MockIntervalRunner** 驱动 FSM。 |
| **Real 接口** | 使用 `useSop` / `useFsmGraph` / `useWorkstationWs` 拉真实后端（需 `.env` 与可用服务）。 |

切换模式时会 **重置 FSM 与 HUD**，并 **停止 Mock 定时器 / 断开 WS**，避免双源与重复事件（对齐 T06 DoD）。

### 2.4 Mock 时间线与可观察行为

| 时刻（约） | 行为 |
|------------|------|
| 进入 Mock 瞬间 | 发送 `STEP_0`（准备态，列表不高亮具体工步）。 |
| 之后每 **8 秒** | 自动发送 `FSM_STATE_UPDATE`，依次 `STEP_1` → … → `STEP_N` → `STEP_DONE`。 |
| 进入 **STEP_3** | 注入 **TIMEOUT** 类 HUD（动作超时 / 犹豫演示）；需点击 **「已知晓」** 关闭（对齐误触与现场交互）。 |
| 步骤变化 | 左侧高亮与自动滚动居中；右侧详情卡切换；播放器按步骤 **keyframe** 做 **seek**（优先 `keyframe_time_sec`）。 |
| `STEP_DONE` | 显示 **工序已完成** 视图；Mock 定时器结束（不循环，除非后续改配置）。 |

实现入口：`src/mock/MockIntervalRunner.ts`、`src/pages/DemoPage.tsx`。

### 2.5 演示视频不可见时的处理

视频候选顺序由 `src/lib/demoVideoSources.ts` 汇总，逻辑为：

1. `VITE_DEMO_VIDEO_URL`（若配置）
2. Real 模式下接口返回的 `demo_video_src`（若存在）
3. 本地静态：`/demo-sop-guide.mp4`（即 `public/demo-sop-guide.mp4`）
4. 内置默认外链（`MOCK_SOP_DEMO.demo_video_src`）

`SOPPlayer` 会在 **当前地址加载失败** 时自动尝试下一候选；全部失败则显示 **中文故障说明**（内网拦截、放置本地文件、配置环境变量等）。

**推荐做法（内网 / 国内）**：

1. 将任意短 **mp4**（H.264，建议 &lt; 50MB）复制为：  
   `frontend/workstation/public/demo-sop-guide.mp4`
2. 重启 `pnpm dev`，再打开 `/demo`。

或在 `.env` 中设置可访问的 mp4 URL：

```env
VITE_DEMO_VIDEO_URL=https://你的文件服务/工位演示.mp4
```

---

## 三、Real 演示（需要后端）

### 3.1 配置

在 `.env` 中填写（示例见 `.env.example`）：

```env
VITE_API_BASE_URL=http://localhost:8000
VITE_WS_BASE_URL=ws://localhost:8000
```

### 3.2 操作步骤

1. 确保后端提供 `GET /api/sop/demo`、`GET /api/fsm/demo`（或你环境对应的 id），以及 `WS`：`/ws/workstation/demo`（与 `useWorkstationWs` 拼接规则一致）。
2. 在 `/demo` 点击 **Real 接口**。
3. 观察侧栏 **REST / WS** 文案与右下角 **WS 状态**（已连接 / 重连中 / 断开；指数退避 1/2/4/8/16 s）。

### 3.3 消息与 HUD（Real）

- `FSM_STATE_UPDATE`：驱动步骤高亮与 seek。
- `COMPLIANCE_ALERT`：映射为 **VIOLATION** HUD。
- `HESITATION_WARNING`：映射为 **TIMEOUT** HUD。

解析与分发：`src/ws/dispatchWorkstationMessage.ts`、`src/hooks/useWorkstationWs.ts`。

---

## 四、后续产线：工位 HLS 配置步骤（规划）

> **正式约束**（`frontend/AGENTS.md`）：工位 SOP 引导须使用 **HLS 流**，支持断点续播，**不**使用「仅 mp4 直链」作为产线方案。当前仓库中的 `<video src="*.mp4">` 与多候选回退用于 **开发演示 / T06**，上产线前应替换为 HLS 播放链路。

### 4.1 媒体与打包

1. **源素材**：产线录制的装配引导视频（建议多码率，1080p 横屏为主）。
2. **转码为 HLS**：使用 FFmpeg 或媒体服务器（如 **AWS MediaConvert、阿里云 MPS、自建 nginx-rtmp + ffmpeg**）输出：
   - `master.m3u8`（多码率可选）
   - `index.m3u8` + `*.ts`（或 fMP4 分片）
3. **存放位置**：
   - **对象存储 + CDN**（推荐）：如 S3/OSS + CloudFront/阿里云 CDN，开启 **HTTPS**。
   - 或 **内网 MinIO / 静态 Nginx**，由工厂网络访问。

### 4.2 播放端技术选型（前端实现阶段）

在 `SOPPlayer`（或并列新组件 `SOPPlayerHls`）中：

1. 引入 **hls.js**（Safari 原生 `ManagedMediaSource` / `src` 直挂 m3u8 可单独分支）。
2. 用 **m3u8 URL** 替代当前 mp4 `src`；销毁组件时调用 `hls.destroy()`，避免内存与重复监听。
3. **seek 与关键帧**：HLS 为分段流，`currentTime` 仍可 seek；若需与 `keyframe_time_sec` 严格对齐，应保证 **GOP / 切片边界** 与文档约定一致，并在规格中固化「以时间码为准」的 seek 策略（见 `workstation-ui.md` §6）。

### 4.3 数据契约（后端 / SOP 文档）

1. 在 `SOPDocument`（或 `GET /api/sop/{id}` 响应）中增加或改用字段，例如：
   - `sop_video_hls_url`：主播放列表地址（`https://.../master.m3u8`）
   - 或 `sop_video_type: "hls"` + `sop_video_src` 指向 m3u8  
2. **MockSOPBundle**（`src/types/sopUi.ts`）同步扩展字段，便于本地 Mock 使用 **测试用 m3u8**（如公网测试流，仅开发用）。
3. **环境变量**：可增加 `VITE_DEMO_HLS_URL` 仅用于演示；产线 URL **必须由接口返回**，避免硬编码（与 `VITE_API_BASE_URL` 规则一致）。

### 4.4 网络与安全

1. **HTTPS 页面**不得请求 **明文 HTTP** HLS，浏览器会拦截；CDN 与 API 需 **TLS**。
2. **跨域**：m3u8/ts 所在域需正确配置 **CORS**（`Access-Control-Allow-Origin` 等），否则 hls.js 无法拉取分片。
3. **鉴权**（可选）：m3u8 使用 **短期签名 URL** 或 **Cookie 同域**；避免把长期密钥写进前端。

### 4.5 与现有代码的衔接清单（实施时）

| 序号 | 事项 |
|------|------|
| 1 | 扩展 `SOPPlayer` 或新增 HLS 容器组件，接入 hls.js / 原生 HLS。 |
| 2 | `MOCK_SOP_DEMO` 与 API 类型增加 HLS 字段；`buildDemoVideoCandidates` 改为「HLS 优先」或独立 `hlsCandidates`。 |
| 3 | `DemoPage` / 正式工位页：根据 `sop_video_type` 分支渲染 mp4 演示 vs HLS 产线。 |
| 4 | 文档：更新 `docs/module-specs/workstation-ui.md` 中「SOPPlayer / 视频」小节，固化 T03 验收项（HLS + seek + 全屏 + 倍速在 Chrome/Edge 的行为）。 |
| 5 | **断点续播**：使用 `localStorage` 或后端记录 `workstation_id + sop_id + lastTime`，在 `loadedmetadata` / `canplay` 后恢复 `currentTime`（注意隐私与工单切换时清空）。 |

### 4.6 验收建议（产线前）

- 在 **工厂 Wi‑Fi / 有线** 与 **1920×1080** 分辨率下实测：首帧时间、卡顿时长、seek 响应。
- 弱网模拟（Chrome DevTools throttling）下确认缓冲策略与 UI 提示（禁止向工人展示技术堆栈，见 `frontend/AGENTS.md`）。

---

## 五、相关文件索引

| 路径 | 说明 |
|------|------|
| `src/pages/DemoPage.tsx` | `/demo` 页面与 Mock/Real 集成 |
| `src/mock/MockIntervalRunner.ts` | 定时 FSM + 步骤注入 |
| `src/data/mockWorkstation.ts` | Mock SOP 与默认演示视频 URL |
| `src/lib/demoVideoSources.ts` | 演示视频候选链 |
| `src/components/SOPPlayer.tsx` | 播放器（当前 mp4；后续扩展 HLS） |
| `src/ClientRouter.tsx` | `/` 与 `/demo` 路由 |
| `docs/module-specs/workstation-ui.md` | 模块规格与 T01–T06 |

---

**文档版本**：与当前仓库 `workstation_ui` 实现同步；HLS 小节为上线前实施清单，以规格评审为准。
