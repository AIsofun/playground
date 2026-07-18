from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Demo Server")


@mcp.tool()
def add(a: float, b: float) -> str:
    """Add two numbers together."""
    result = a + b
    return f"{a} + {b} = {result}"

@mcp.tool()
def get_weather(city: str) -> str:
    """Get the current weather for a city (mock data for demo)."""
    mock_data = {
        "beijing": "北京：晴天，26°C，微风",
        "北京": "北京：晴天，26°C，微风",
        "shanghai": "上海：多云，23°C，东南风",
        "上海": "上海：多云，23°C，东南风",
        "guangzhou": "广州：小雨，28°C，南风",
        "广州": "广州：小雨，28°C，南风",
        "shenzhen": "深圳：阴天，27°C，东风",
        "深圳": "深圳：阴天，27°C，东风",
    }
    key = city.lower()
    return mock_data.get(key, f"{city}：晴天，22°C，微风（默认数据）")

@mcp.tool()
def word_count(text: str) -> str:
    """Count the number of words and characters in a text."""
    words = len(text.split())
    chars = len(text)
    return f"字符数：{chars}，单词/词组数：{words}"

if __name__ == "__main__":
    import sys
    transport = "sse" if "--http" in sys.argv else "stdio"
    mcp.run(transport=transport)
