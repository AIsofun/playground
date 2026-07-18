# MCP Server Demo 启动说明

本项目是一个基于 `mcp.server.fastmcp.FastMCP` 的 MCP Server 示例，入口文件是 `main.py`。

项目内提供了：

- Tool: `add(a: int, b: int) -> int`
- Resource: `greeting://{name}`
- Prompt: `greet_user(name: str, style: str = "friendly")`

推荐使用 `modelcontextprotocol/inspector` 做本地演示。Inspector 会在浏览器中提供调试界面，但它连接的是 MCP 服务，不是普通网页应用。

## 环境要求

- Node.js `>= 22.7.5`
- `uv`
- Python 版本满足 `pyproject.toml` 中的要求

在项目根目录执行命令：

```powershell
cd F:\code\myCode\AgentDemoForCom
```

## 方式一：通过 STDIO 启动

当前 `main.py` 默认就是 STDIO 模式：

```python
if __name__ == "__main__":
    logger.info("启动 MCP server，transport=stdio")
    mcp.run(transport="stdio")
```

使用 Inspector 启动：

```powershell
npx -y @modelcontextprotocol/inspector uv run python main.py
```

启动后终端会输出一个带 token 的地址，类似：

```text
http://localhost:6274/?MCP_PROXY_AUTH_TOKEN=...
```

在浏览器中打开该地址。如果没有自动连接，在 Inspector 中手动填写：

```text
Transport Type: STDIO
Command: uv
Arguments: run python main.py
```

点击 `Connect` 后，可以进入：

- `Tools` 页面调用 `add`
- `Resources` 页面测试 `greeting://{name}`
- `Prompts` 页面测试 `greet_user`

示例调用：

```text
Tools -> add
a = 1
b = 2
Result = 3
```

## 方式二：通过 Streamable HTTP 启动

如果要通过 HTTP 方式演示，需要把 `main.py` 末尾的启动方式改成 `streamable-http`：

```python
if __name__ == "__main__":
    logger.info("启动 MCP server，transport=streamable-http")
    mcp.run(transport="streamable-http")
```

然后先启动 MCP Server：

```powershell
uv run python main.py
```

服务启动后，默认 MCP HTTP 端点通常是：

```text
http://localhost:8000/mcp
```

再另开一个终端启动 Inspector：

```powershell
npx -y @modelcontextprotocol/inspector
```

打开 Inspector 页面：

```text
http://localhost:6274
```

在 Inspector 中手动填写：

```text
Transport Type: Streamable HTTP
URL: http://localhost:8000/mcp
```

点击 `Connect` 后，同样可以测试：

- `Tools -> add`
- `Resources -> greeting://{name}`
- `Prompts -> greet_user`

## 端口冲突处理

Inspector 默认使用：

```text
Client UI: http://localhost:6274
Proxy Server: http://localhost:6277
```

如果端口被占用，可以指定其他端口：

```powershell
$env:CLIENT_PORT="6284"
$env:SERVER_PORT="6287"
npx -y @modelcontextprotocol/inspector
```

如果是 STDIO 模式，也可以这样指定端口后启动：

```powershell
$env:CLIENT_PORT="6284"
$env:SERVER_PORT="6287"
npx -y @modelcontextprotocol/inspector uv run python main.py
```

## 注意事项

- STDIO 模式下，`stdout` 是 MCP 协议通道，不能随意 `print()` 日志。
- 当前代码已经把日志写入 `mcp_server.log`，适合 STDIO 模式。
- HTTP 模式适合演示“先启动服务，再用 Inspector 连接 URL”的流程。
- STDIO 模式适合演示“Inspector 直接拉起 MCP Server 进程”的流程。
