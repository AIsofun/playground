"""边缘置信度分档阈值（与 ``src/config/vlm.py`` 出厂默认数值保持一致）。

``edge_node`` 禁止 import ``src/config``；修改默认阈值时须与服务端同步并更新本文件注释日期。
"""

from __future__ import annotations

# 与 src/config/vlm.py 中 VLMSettings 默认 CONF_LOW / CONF_HIGH 对齐（domain-logic.md §2）
CONF_LOW: float = 0.4
CONF_HIGH: float = 0.7
