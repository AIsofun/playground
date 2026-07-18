# AGENTS.md — agents 子模块专属规则

> **覆盖范围**：`src/services/agents/` 目录。全局规则见根目录 `AGENTS.md`。

---

## 一、模块职责边界

```
comply_alert.py        ← 合规告警 Agent（LangGraph 单节点）
quality_root_cause.py  ← 质量根因 Agent（LangGraph 多节点 + Human-in-Loop）
sop_switch.py          ← SOP 切换 Agent（LangGraph 单节点）
```

所有 Agent 均基于 **LangGraph** 构建，LLM 后端使用 **DeepSeek-V3 API 或 Qwen3-32B 本地部署**，与 VLM（Qwen2.5-VL）分开部署，避免资源争抢。

---

## 二、Human-in-Loop 强制规则

**所有可能触发外部系统写操作的 Agent，必须包含 Human-in-Loop 节点**。

当前涉及的 Agent：`quality_root_cause.py`

```
LangGraph 节点序列（quality_root_cause）：
  query_timescale → correlate_operator → correlate_parts
      → generate_report → [PAUSE: Human-in-Loop]
      → (质量工程师确认) → create_mes_ticket
```

**实现要求**：
1. 报告生成后，Agent 状态必须切换为 `WAITING_APPROVAL`，**不得继续执行**
2. 通过 `src/api/routes/reports.py` 的 `POST /api/reports/{id}/approve` 接口恢复执行
3. 超时（默认 24 小时）未确认，Agent 自动终止并发送提醒，**不自动创建 MES 工单**
4. Human-in-Loop 超时时长配置在 `src/config/agents.py`

---

## 三、各 Agent 工具清单（不得超出）

| Agent | 允许调用的工具 | 禁止调用的工具 |
|-------|--------------|--------------|
| `comply_alert` | 企业微信/钉钉 Webhook；工位屏 WebSocket 推送 | MES API；数据库写操作 |
| `quality_root_cause` | TimescaleDB 查询；PostgreSQL 零件批次查询；MES REST API（仅在 Human-in-Loop 确认后）| 直接修改 SOP；删除数据 |
| `sop_switch` | Milvus 查询（按产品型号召回 SOP）；工位屏 WebSocket 推送 | MES API；任何写操作 |

---

## 四、根因报告格式规范

`quality_root_cause` Agent 输出的报告必须遵循 5W1H 格式，写入 PostgreSQL `reports` 表：

```json
{
  "report_id": "uuid",
  "triggered_at": "ISO8601",
  "workstation_id": "string",
  "what": "缺陷描述（类型、数量、严重程度）",
  "when": "发生时间段",
  "where": "具体工位和 SOP 步骤",
  "who": "操作员 ID、班次",
  "why": "根因分析（SOP 偏差记录、零件批次异常等）",
  "how": "纠正措施建议",
  "status": "PENDING_APPROVAL | APPROVED | REJECTED",
  "mes_ticket_id": "string | null"
}
```

---

## 五、LLM 调用规则

- **禁止**在 Agent 代码中硬编码 System Prompt，必须从 `.ai/prompts/root-cause-analysis.txt` 加载
- **禁止**使用流式输出（Agent 节点必须等待完整 LLM 响应后再进入下一节点）
- **必须**设置 LLM 调用超时（默认 60 秒，配置在 `src/config/agents.py`）
- **必须**记录每次 LLM 调用的 token 消耗到 PostgreSQL `llm_usage` 表（用于成本追踪）

---

## 六、禁止行为清单

- ❌ 任何 Agent 未经 Human-in-Loop 确认直接调用 MES API 创建工单
- ❌ Agent 工具调用超出上表"允许调用的工具"范围
- ❌ 在 Agent 代码中直接实例化数据库连接（必须通过 `src/adapters/`）
- ❌ `comply_alert` Agent 写入任何持久化存储（只推送，不存储）
- ❌ 修改 Agent System Prompt 而不更新 `.ai/prompts/` 对应文件
