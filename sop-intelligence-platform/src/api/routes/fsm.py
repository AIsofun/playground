"""FSM 编译、拓扑查询与运行态流占位（T05）。"""

from __future__ import annotations

import logging
from typing import Any, Literal

from fastapi import APIRouter, Body, HTTPException, Request, WebSocket, status
from pydantic import BaseModel, Field

from src.services.fsm.compiler import FSMCompilationError
from src.services.fsm.persist import FsmGraphPersistService, SopNotFoundForFsmError
from src.services.sop_engine.version_manager import VersionManager
from src.types.fsm import FSMGraph

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/fsm", tags=["fsm"])


def _error_detail(
    code: str,
    message: str,
    *,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"code": code, "message": message}
    if extra:
        body["details"] = extra
    return body


def _persist_or_503(request: Request) -> FsmGraphPersistService:
    vm: VersionManager | None = getattr(request.app.state, "version_manager", None)
    fsm_pg = getattr(request.app.state, "fsm_graphs_client", None)
    if vm is None or fsm_pg is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_error_detail(
                "storage_unavailable",
                "未配置 SOP_POSTGRES_DSN 或 FSM 存储未初始化",
            ),
        )
    return FsmGraphPersistService(vm.sop_versions_postgres, fsm_pg)


class CompileFsmBody(BaseModel):
    """POST /fsm/compile/{sop_id} 可选请求体。"""

    expert_video_duration_sec: float | None = Field(
        default=None,
        gt=0.0,
        description="专家视频时长（秒）；缺省时用 SOP 各步时间戳上界估计",
    )


class CompileFsmResponse(BaseModel):
    """编译落库后的主键与回链字段，便于前端从 SOP 跳转到监控。"""

    fsm_id: str = Field(..., description="本次编译写入的 FSM 主键（UUID 字符串）")
    sop_id: str = Field(..., description="来源 SOP 文档主键")
    sop_version: str = Field(..., description="落库时的 SOP 版本号（product-vMAJOR.MINOR）")
    status: Literal["stored"] = Field(default="stored", description="已写入 fsm_graphs")


class FsmTopologyResponse(BaseModel):
    """静态拓扑：与 ``FsmGraphRow`` 对齐的可 JSON 响应。"""

    fsm_id: str
    sop_id: str
    product_id: str
    version: str
    expert_video_duration_sec: float
    graph: FSMGraph


@router.post(
    "/compile/{sop_id}",
    response_model=CompileFsmResponse,
    summary="按 sop_id 编译 FSM 并写入 PostgreSQL",
)
async def compile_fsm_for_sop(
    request: Request,
    sop_id: str,
    body: CompileFsmBody | None = Body(default=None),
) -> CompileFsmResponse:
    svc = _persist_or_503(request)
    duration = None if body is None else body.expert_video_duration_sec
    try:
        fsm_id, _ = await svc.compile_and_store(
            sop_id,
            expert_video_duration_sec=duration,
        )
    except SopNotFoundForFsmError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_error_detail("not_found", f"不存在 sop_id={sop_id!r} 的 SOP 文档"),
        ) from None
    except FSMCompilationError as exc:
        logger.info("FSM 编译失败：%s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_error_detail(
                "fsm_compilation_failed",
                str(exc),
                extra=getattr(exc, "details", None),
            ),
        ) from exc

    row = await svc.get_topology(fsm_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_error_detail("invariant_broken", "编译成功但无法读回 fsm_graphs 行"),
        )
    return CompileFsmResponse(
        fsm_id=row.fsm_id,
        sop_id=row.sop_id,
        sop_version=row.version,
    )


@router.get(
    "/by-sop/{sop_id}",
    response_model=FsmTopologyResponse,
    summary="按 sop_id 取最近一次编译的 FSM 拓扑",
)
async def get_latest_fsm_for_sop(request: Request, sop_id: str) -> FsmTopologyResponse:
    svc = _persist_or_503(request)
    row = await svc.get_latest_topology_for_sop(sop_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_error_detail(
                "not_found",
                f"不存在 sop_id={sop_id!r} 的已编译 FSM",
            ),
        )
    return FsmTopologyResponse(
        fsm_id=row.fsm_id,
        sop_id=row.sop_id,
        product_id=row.product_id,
        version=row.version,
        expert_video_duration_sec=row.expert_video_duration_sec,
        graph=row.graph,
    )


# ---------------------------------------------------------------------------
# Demo 种子 FSM（绕过数据库，供前端 Real 模式演示）
# ---------------------------------------------------------------------------

_DEMO_FSM_RESPONSE: dict[str, Any] = {
    "fsm_id": "demo-fsm-battery-pack-01",
    "sop_id": "demo-battery-pack-01",
    "product_id": "NCM811-DEMO",
    "version": "NCM811-DEMO-v1.0",
    "expert_video_duration_sec": 50.0,
    "graph": {
        "nodes": {
            "STEP_0": {
                "node_id": "STEP_0",
                "step_id": None,
                "action_type": None,
                "timeout_sec": None,
                "keyframe_path": None,
            },
            "STEP_1": {
                "node_id": "STEP_1",
                "step_id": 1,
                "action_type": "module_placement",
                "timeout_sec": 20.0,
                "keyframe_path": "minio://sop-keyframes/demo/step_1.jpg",
            },
            "STEP_2": {
                "node_id": "STEP_2",
                "step_id": 2,
                "action_type": "busbar_connection",
                "timeout_sec": 25.0,
                "keyframe_path": "minio://sop-keyframes/demo/step_2.jpg",
            },
            "STEP_3": {
                "node_id": "STEP_3",
                "step_id": 3,
                "action_type": "thermal_management",
                "timeout_sec": 15.0,
                "keyframe_path": "minio://sop-keyframes/demo/step_3.jpg",
            },
            "STEP_4": {
                "node_id": "STEP_4",
                "step_id": 4,
                "action_type": "final_inspection",
                "timeout_sec": 20.0,
                "keyframe_path": "minio://sop-keyframes/demo/step_4.jpg",
            },
            "STEP_DONE": {
                "node_id": "STEP_DONE",
                "step_id": None,
                "action_type": None,
                "timeout_sec": None,
                "keyframe_path": None,
            },
        },
        "edges": [
            ["STEP_0", "STEP_1"],
            ["STEP_1", "STEP_2"],
            ["STEP_2", "STEP_3"],
            ["STEP_3", "STEP_4"],
            ["STEP_4", "STEP_DONE"],
        ],
    },
}


@router.get(
    "/demo",
    summary="演示种子 FSM 拓扑（绕过数据库）",
)
async def get_demo_fsm() -> dict[str, Any]:
    """返回硬编码的演示 FSM 拓扑数据，无需 PostgreSQL。"""
    return _DEMO_FSM_RESPONSE


@router.get(
    "/{fsm_id}",
    response_model=FsmTopologyResponse,
    summary="按 fsm_id 获取静态拓扑",
)
async def get_fsm_topology(request: Request, fsm_id: str) -> FsmTopologyResponse:
    svc = _persist_or_503(request)
    row = await svc.get_topology(fsm_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_error_detail("not_found", f"不存在 fsm_id={fsm_id!r}"),
        )
    return FsmTopologyResponse(
        fsm_id=row.fsm_id,
        sop_id=row.sop_id,
        product_id=row.product_id,
        version=row.version,
        expert_video_duration_sec=row.expert_video_duration_sec,
        graph=row.graph,
    )


@router.websocket("/{fsm_id}/stream")
async def fsm_runtime_stream_placeholder(websocket: WebSocket, fsm_id: str) -> None:
    """运行态 WebSocket 占位：建立连接后推送一条 Mock 帧即关闭（T05 可选）。"""
    await websocket.accept()
    await websocket.send_json(
        {
            "type": "mock",
            "fsm_id": fsm_id,
            "note": "sop-fsm T05 placeholder; 后续接入 FSMRunner.snapshot 推送",
        },
    )
    await websocket.close()
