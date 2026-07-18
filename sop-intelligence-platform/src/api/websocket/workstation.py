"""工位 WebSocket 推送：FSM 状态更新 + 合规告警。

MVP 阶段：Demo 模式下服务端驱动 FSM 步进（等效后端 MockIntervalRunner），
步骤 2 注入 HESITATION_WARNING；后续接入真实 FSMRunner.snapshot 推送。
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter()

_DEMO_STEPS = [
    {"state_id": "STEP_0"},
    {"state_id": "STEP_1"},
    {"state_id": "STEP_2"},
    {"state_id": "STEP_3"},
    {"state_id": "STEP_4"},
    {"state_id": "STEP_DONE"},
]

_HESITATION_AT_STEP = 2
_STEP_INTERVAL_SEC = 8


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.websocket("/ws/workstation/{workstation_id}")
async def workstation_ws(websocket: WebSocket, workstation_id: str) -> None:
    """Demo 模式：每 N 秒推送 FSM_STATE_UPDATE，指定步骤注入 HESITATION_WARNING。"""
    await websocket.accept()
    logger.info("WS 工位连接 workstation_id=%s", workstation_id)

    try:
        for step_info in _DEMO_STEPS:
            state_id = step_info["state_id"]

            await websocket.send_text(
                json.dumps(
                    {
                        "type": "FSM_STATE_UPDATE",
                        "state_id": state_id,
                        "timestamp": _now_iso(),
                    },
                    ensure_ascii=False,
                )
            )

            # 在指定步骤注入超时/犹豫告警
            step_num = _parse_step_num(state_id)
            if step_num == _HESITATION_AT_STEP:
                await asyncio.sleep(0.5)
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "HESITATION_WARNING",
                            "title": "动作超时 / 犹豫",
                            "suggestion": "请回到标准节拍完成「母排连接与紧固」关键动作；"
                            "仍异常请呼叫班组长协助。",
                            "related_step_id": step_num,
                            "timestamp": _now_iso(),
                        },
                        ensure_ascii=False,
                    )
                )

            if state_id == "STEP_DONE":
                break

            await asyncio.sleep(_STEP_INTERVAL_SEC)

        # 推送完毕后保持连接等待客户端关闭
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        logger.info("WS 工位断开 workstation_id=%s", workstation_id)
    except Exception:
        logger.exception("WS 工位异常 workstation_id=%s", workstation_id)


def _parse_step_num(state_id: str) -> int | None:
    if state_id.startswith("STEP_") and state_id != "STEP_DONE":
        try:
            return int(state_id.split("_")[1])
        except (ValueError, IndexError):
            return None
    return None

