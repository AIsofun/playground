import asyncio
import json

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from openai import OpenAI

# ── 配置 ──────────────────────────────────────────────────────────────────────
OLLAMA_BASE_URL = "http://localhost:11434/v1"
MODEL = "qwen2.5:7b"          # 需要支持 tool calling，也可换 llama3.1:8b 等
SERVER_SCRIPT = "server.py"   # MCP Server 入口文件
# ─────────────────────────────────────────────────────────────────────────────

llm = OpenAI(base_url=OLLAMA_BASE_URL, api_key="ollama")


def mcp_tools_to_openai(mcp_tools) -> list[dict]:
    """将 MCP 工具格式转换为 OpenAI tool calling 格式。"""
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description or "",
                "parameters": tool.inputSchema,
            },
        }
        for tool in mcp_tools
    ]


async def run_agent(session: ClientSession):
    """主对话循环：用户输入 → 模型推理 → （可能）调用工具 → 回复。"""
    # 从 MCP Server 获取所有可用工具
    tools_result = await session.list_tools()
    tools = mcp_tools_to_openai(tools_result.tools)

    print(f"\n已连接 MCP Server，可用工具：{[t['function']['name'] for t in tools]}")
    print(f"使用模型：{MODEL}（通过 Ollama）")
    print("输入 'exit' 退出\n")

    messages: list[dict] = []

    while True:
        user_input = input("你：").strip()
        if user_input.lower() in ("exit", "quit", "退出"):
            break
        if not user_input:
            continue

        messages.append({"role": "user", "content": user_input})

        # ── Agent 循环：持续处理工具调用，直到模型给出最终回复 ──────────────
        while True:
            response = llm.chat.completions.create(
                model=MODEL,
                messages=messages,
                tools=tools,
            )
            msg = response.choices[0].message

            # 没有工具调用 → 最终回复
            if not msg.tool_calls:
                print(f"\n模型：{msg.content}\n")
                messages.append({"role": "assistant", "content": msg.content})
                break

            # 有工具调用 → 执行并把结果反馈给模型
            messages.append(msg)  # 把含 tool_calls 的 assistant 消息存入历史

            for tool_call in msg.tool_calls:
                fn_name = tool_call.function.name
                fn_args = json.loads(tool_call.function.arguments)

                print(f"  [调用工具] {fn_name}({fn_args})")

                result = await session.call_tool(fn_name, fn_args)
                tool_output = result.content[0].text if result.content else "（无返回）"

                print(f"  [工具结果] {tool_output}")

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_output,
                })
        # ────────────────────────────────────────────────────────────────────


async def main():
    server_params = StdioServerParameters(
        command="python",
        args=[SERVER_SCRIPT],
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            await run_agent(session)


if __name__ == "__main__":
    asyncio.run(main())
