# AgentDemoForCom

一个 **MCP (Model Context Protocol) + 本地 LLM (Ollama)** 的 Agent 演示项目。

一个 MCP Server 提供工具，两个 Client 演示通过不同传输方式连接它，再借助 Ollama 上的本地模型实现「工具调用 (tool calling)」对话。

## 项目结构

| 文件 | 角色 | 说明 |
| ---- | ---- | ---- |
| `server.py` | MCP Server | 用 FastMCP 暴露 3 个工具：`add`（加法）、`get_weather`（查天气，mock 数据）、`word_count`（字数统计） |
| `client.py` | Client（stdio） | 以子进程方式启动 `server.py`，通过标准输入输出通信 |
| `clientHttp.py` | Client（HTTP/SSE） | 连接一个已在 8000 端口运行的 server，通过 SSE 通信 |

两个 client 逻辑几乎一致：从 MCP Server 获取工具列表 → 转成 OpenAI tool 格式 → 进入对话循环；把用户输入交给 Ollama 模型，模型决定是否调用工具，调用结果再喂回模型，直到生成最终回复。

## 运行前提

1. **Python ≥ 3.14**
2. **安装依赖**（项目使用 [uv](https://github.com/astral-sh/uv)）：

   ```bash
   uv sync
   ```

3. **本地运行 Ollama**，并拉取一个支持 tool calling 的模型：

   ```bash
   ollama pull qwen2.5:7b
   ```

   相关配置写在 client 文件顶部：

   - `OLLAMA_BASE_URL = http://localhost:11434/v1`
   - `MODEL = qwen2.5:7b`（也可换成 `llama3.1:8b` 等支持工具调用的模型）

## 使用方式

### 方式 A — stdio（推荐，无需手动启动 server）

```bash
uv run python client.py
```

client 会自动以子进程启动 `server.py`，然后进入交互式对话。

### 方式 B — HTTP/SSE（需要分两个终端）

```bash
# 终端 1：以 SSE 模式启动 server，监听 http://localhost:8000/sse
uv run python server.py --http

# 终端 2：启动 HTTP client
uv run python clientHttp.py
```

## 交互示例

启动后进入交互式对话，输入 `exit` / `quit` / `退出` 结束。可以尝试：

- `3.5 加 7 等于多少？` → 模型调用 `add` 工具
- `北京天气怎么样？` → 调用 `get_weather`
- `统计一下 "hello world foo" 有几个词` → 调用 `word_count`

终端会打印 `[调用工具]` 和 `[工具结果]`，可以看到 Agent 调用工具的完整过程。
