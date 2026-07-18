"""合规监控演示预设 — 为 Demo 模式提供硬编码的合规事件序列。

前端 Real/Demo 切换时，后端 WS 推送合规事件不依赖真实推理，
而是使用此模块的预设时间线。
"""

from __future__ import annotations

from typing import Any

DEMO_COMPLIANCE_EVENTS: list[dict[str, Any]] = [
    {
        "event_id": "demo-evt-001",
        "event_type": "COMPLIANT",
        "step_id": 1,
        "confidence": 0.85,
        "message": "底壳放置与模组入位 — 合规",
        "offset_sec": 5.0,
    },
    {
        "event_id": "demo-evt-002",
        "event_type": "COMPLIANT",
        "step_id": 2,
        "confidence": 0.78,
        "message": "母排连接与紧固 — 合规",
        "offset_sec": 18.0,
    },
    {
        "event_id": "demo-evt-003",
        "event_type": "HESITATION_WARNING",
        "step_id": 2,
        "confidence": 0.45,
        "message": "母排紧固动作犹豫 — 请确认扭矩",
        "offset_sec": 24.0,
    },
    {
        "event_id": "demo-evt-004",
        "event_type": "COMPLIANT",
        "step_id": 3,
        "confidence": 0.82,
        "message": "热管理系统连接 — 合规",
        "offset_sec": 30.0,
    },
    {
        "event_id": "demo-evt-005",
        "event_type": "COMPLIANT",
        "step_id": 4,
        "confidence": 0.90,
        "message": "顶盖密封与最终质检 — 合规",
        "offset_sec": 44.0,
    },
]


def get_demo_events_for_step(step_id: int) -> list[dict[str, Any]]:
    """返回与指定步骤关联的演示合规事件。"""
    return [e for e in DEMO_COMPLIANCE_EVENTS if e["step_id"] == step_id]
