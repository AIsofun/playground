"""
FastMCP quickstart example

Run from the repository root:
    uv run servers/fastmcp_quickstart.py
"""

import logging
import os
from mcp.server.fastmcp import FastMCP

# 日志文件固定到脚本所在目录，避免 Claude Desktop 以 system32 作为 cwd 时产生权限错误
_LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcp_server.log")

# stdio 传输模式下 stdout 是 MCP 协议专用通道，日志只能写文件，不能写 stdout/stderr
# 只配置具名 logger，避免根 logger 捕获第三方库（mcp/anyio 等）的 DEBUG 输出污染协议流
logger = logging.getLogger("ServerDemo")
logger.setLevel(logging.DEBUG)
_handler = logging.FileHandler(_LOG_FILE, encoding="utf-8")
_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s - %(message)s"))
logger.addHandler(_handler)
logger.propagate = False  # 阻止日志冒泡到根 logger，防止第三方 handler 捕获

#Create an MCP server
#mcp = FastMCP("ServerDemo", json_response = True)
mcp = FastMCP("MCPServerDemo")
logger.info("MCP server 'MCPServerDemo' 已初始化")

# Add an addition tool
@mcp.tool()
def add(a: int, b:int) -> int:
    """Add two numbers"""
    logger.info("调用工具 add: a=%s, b=%s", a, b)
    result = a + b
    logger.debug("add 结果: %s + %s = %s", a, b, result)
    return result

# Add a dynamic greeting resource
@mcp.resource("greeting://{name}")
def get_greeting(name: str) -> str:
    """Get a personalized greeting"""
    logger.info("调用资源 get_greeting: name='%s'", name)
    greeting = f"Hello, {name}!"
    logger.debug("get_greeting 返回: %s", greeting)
    return greeting

# Add a prompt
@mcp.prompt()
def greet_user(name: str, style: str = "friendly") -> str:
    """Generate a greeting prompt"""
    logger.info("调用 prompt greet_user: name='%s', style='%s'", name, style)
    styles = {
        "friendly": "Please write a warm, friendly greeting",
        "formal": "Please write a formal, professional greeting",
        "casual": "Please write a casual, relaxed greeting",
    }
    selected_style = styles.get(style, styles['friendly'])
    if style not in styles:
        logger.warning("未知的 style '%s'，回退到默认 'friendly'", style)
    result = f"{selected_style} for someone named {name}."
    logger.debug("greet_user 返回: %s", result)
    return result

#Run with streamable HTTP transport
if __name__ == "__main__":
    logger.info("启动 MCP server，transport=stdio")
    #mcp.run(transport="streamable-http") #网页打开
    mcp.run(transport="stdio") #stdio模式；Inspector