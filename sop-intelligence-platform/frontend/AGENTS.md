# AGENTS.md — frontend 专属规则

> **覆盖范围**：`frontend/` 目录下所有前端代码。全局规则见根目录 `AGENTS.md`。

---

## 一、子项目结构

```
frontend/
├── workstation/    ← 工位交互屏（React 18 + shadcn/ui + WebSocket）
└── dashboard/      ← 管理看板（React 18 + Grafana iframe + shadcn/ui）
```

两个子项目**独立构建部署**，不共享 bundle，但可共享 `types/` 和 `utils/` 公共库。

工位屏 **Mock/Real 演示步骤** 与 **后续 HLS 工位配置** 说明见 `workstation/DEMO.md`；**WS / 组件回调事件契约** 见 `docs/reports/workstation-ui-events-export.md`。

---

## 二、误报标记按钮规则（关键业务逻辑）

`workstation/` 的"标记为误报"按钮是数据飞轮的重要入口，必须严格实现：

```
用户点击 → 立即禁用按钮（防重复提交）→ 调用 POST /api/feedback/false-positive
→ 收到 200 → 按钮变灰 + 显示"已标记"
→ 收到 4xx/5xx → 按钮恢复可点击 + 显示错误提示
→ 网络超时（5s）→ 按钮恢复可点击 + 显示"网络异常，请重试"
```

**禁止**：

- 收到响应前不得恢复按钮（防重复提交）
- 不得在前端自行决定是否标记为误报（只转发用户点击，不做客户端判断）
- 请求体必须包含 `frame_id`、`workstation_id`、`sop_step`

---

## 三、WebSocket 实时推送规范

`workstation/` 通过 WebSocket（`/ws/workstation/{id}`）接收实时状态更新：

**断线重连策略**：

```javascript
// 必须实现指数退避重连，不得无限立即重连
const RECONNECT_DELAYS = [1000, 2000, 4000, 8000, 16000]; // ms
// 超过最大重试次数 → 显示"连接已断开，请刷新页面"
```

**消息类型处理**：


| `type` 字段            | 处理方式               |
| -------------------- | ------------------ |
| `FSM_STATE_UPDATE`   | 高亮当前 SOP 步骤，更新进度条  |
| `COMPLIANCE_ALERT`   | 弹出告警弹窗（红色，含步骤说明）   |
| `HESITATION_WARNING` | 黄色提示（动作犹豫 > 3 秒触发） |
| `SOP_SWITCH`         | 加载新产品 SOP，重置步骤进度   |


---

## 四、工位屏 UX 规则

- SOP 视频引导使用 **HLS 流**，支持断点续播，不使用 MP4 直接播放
- 当前步骤必须**全屏高亮**，其余步骤降暗处理
- 告警弹窗覆盖全屏，工人必须手动确认后消失（不自动消失）
- 字体大小不得小于 24px（工业现场观看距离 > 1 米）
- **禁止**使用需要精细点击的小按钮（工人戴手套操作）

---

## 五、管理看板规则

`dashboard/` 中 Grafana 以 iframe 嵌入方式展示时序数据：

- Grafana 面板 URL 不得硬编码，从环境变量 `GRAFANA_BASE_URL` 读取
- 根因报告列表从 `GET /api/reports` 拉取，**不得**直接查询 TimescaleDB
- 审批按钮调用 `POST /api/reports/{id}/approve`，点击后同样需要禁用防重提交
- 数据刷新间隔：合规率趋势 30 秒，根因报告列表 10 秒

---

## 六、禁止行为清单

- ❌ 误报标记按钮响应完成前恢复可点击状态
- ❌ WebSocket 断线后立即无限重连（必须指数退避）
- ❌ 在前端硬编码 API Base URL（从 `VITE_API_BASE_URL` 环境变量读取）
- ❌ dashboard 直连数据库或 Kafka（只通过 REST API）
- ❌ 在工位屏显示任何技术错误堆栈（只显示友好提示）

