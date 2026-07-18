"""SOP 生成与查询路由（T08）：编排 VideoParser → VLMAnnotator → SOPCompiler → VersionManager。"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from src.config.vlm import get_vlm_settings
from src.services.sop_engine.sop_compiler import SOPCompilationError, SOPCompiler
from src.services.sop_engine.video_parser import MockVideoParser, VideoParser
from src.services.sop_engine.vlm_annotator import VLMAnnotator
from src.services.sop_engine.version_manager import VersionManager
from src.types.sop import SOPDocument

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sop", tags=["sop"])

# ---------------------------------------------------------------------------
# 请求 / 响应模型（与 docs/module-specs/sop-engine.md T08 一致）
# ---------------------------------------------------------------------------


class SOPGenerateRequest(BaseModel):
    """POST /generate 请求体。"""

    product_id: str = Field(..., min_length=1, description="产品型号")
    video_paths: list[str] = Field(
        ...,
        min_length=1,
        description="MinIO 等存储中的源视频路径列表；Phase 1 使用首条路径做解析与抽帧",
    )
    version: str = Field(default="v1.0", min_length=1, description="版本后缀，如 v1.0")


class SOPGenerateResponse(BaseModel):
    """Phase 1 同步完成：task_id 与 sop_id 相同（无 Celery）。"""

    task_id: str = Field(..., description="任务标识；当前阶段等同 sop_id")
    status: Literal["accepted", "completed"] = Field(
        ...,
        description="同步流水线完成时为 completed",
    )
    sop_id: str | None = Field(default=None, description="成功写入后的 SOP 主键")


def _error_detail(
    code: str,
    message: str,
    *,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """统一错误体，便于客户端解析。"""
    body: dict[str, Any] = {"code": code, "message": message}
    if extra:
        body["details"] = extra
    return body


def _video_parser() -> VideoParser:
    """Phase 1a：使用 MockVideoParser；后续可换为 VideoMAEParser。"""
    return MockVideoParser()


def _vlm_annotator() -> VLMAnnotator:
    s = get_vlm_settings()
    return VLMAnnotator(
        vlm_base_url=s.VLM_BASE_URL,
        vlm_model=s.VLM_MODEL_NAME,
        timeout_sec=s.VLM_TIMEOUT_SEC,
        max_tokens=s.VLM_MAX_TOKENS,
    )


def _compiler() -> SOPCompiler:
    return SOPCompiler()


def _get_version_manager(request: Request) -> VersionManager | None:
    return getattr(request.app.state, "version_manager", None)


def _vlm_total_timeout_sec(num_segments: int) -> float:
    """整段 annotate 的上限：每片段上限叠加并设下限，避免无限等待。"""
    s = get_vlm_settings()
    per = float(s.VLM_TIMEOUT_SEC)
    return max(90.0, per * max(1, num_segments) + 15.0)


@router.post(
    "/generate",
    response_model=SOPGenerateResponse,
    summary="从视频路径生成 SOP 并持久化",
)
async def generate_sop(
    request: Request,
    body: SOPGenerateRequest,
) -> SOPGenerateResponse:
    """编排：解析视频 → VLM 标注 → 编译文档 → 版本管理持久化。"""
    vm = _get_version_manager(request)
    if vm is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_error_detail(
                "storage_unavailable",
                "未配置 SOP_POSTGRES_DSN 或存储后端未初始化，无法保存 SOP",
            ),
        )

    parser = _video_parser()
    annotator = _vlm_annotator()
    compiler = _compiler()

    primary_video = body.video_paths[0].strip()
    if not primary_video:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_error_detail("invalid_video_path", "video_paths[0] 不能为空"),
        )

    # 1) VideoParser
    segments = parser.parse(primary_video)
    if not segments:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_error_detail("parse_empty", "视频解析未产生任何动作片段"),
        )

    # 关键帧：键为 segment_id（T03→T04 契约）
    keyframes: dict[int, bytes] = {}
    for seg in segments:
        keyframes[seg.segment_id] = parser.extract_keyframe(
            primary_video, seg.keyframe_index
        )

    # 2) VLMAnnotator（整体超时）
    segment_ids_ordered = sorted(s.segment_id for s in segments)
    try:
        annotated = await asyncio.wait_for(
            annotator.annotate(
                segments,
                keyframes,
                product_context=body.product_id,
            ),
            timeout=_vlm_total_timeout_sec(len(segments)),
        )
    except asyncio.TimeoutError:
        logger.warning("VLM annotate 整体超时（segments=%d）", len(segments))
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=_error_detail(
                "vlm_timeout",
                "VLM 语义标注阶段整体超时，请稍后重试或检查 vLLM 服务负载",
                extra={"segment_count": len(segments)},
            ),
        ) from None

    if not annotated:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_error_detail("annotate_empty", "VLM 未返回任何标注步骤"),
        )

    # 编译前占位路径（真实路径由 VersionManager.save 写入）
    placeholder_paths = {
        sid: f"minio://sop-keyframes/pending/{uuid.uuid4()}/seg_{sid}.jpg"
        for sid in segment_ids_ordered
    }

    try:
        doc = compiler.compile(
            product_id=body.product_id,
            annotated_steps=annotated,
            segments=segments,
            keyframe_paths=placeholder_paths,
            source_video_paths=list(body.video_paths),
            version=body.version,
        )
    except SOPCompilationError as exc:
        logger.info("SOP 编译失败：%s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_error_detail(
                "compilation_failed",
                str(exc),
                extra=getattr(exc, "details", None),
            ),
        ) from exc

    # SOPCompiler 按 segment_id 升序产出 step_id=1..n；关键帧字典键为 segment_id，save() 要求 step_id
    sorted_segs = sorted(segments, key=lambda s: s.segment_id)
    try:
        keyframe_bytes_by_step: dict[int, bytes] = {
            st.step_id: keyframes[seg.segment_id]
            for st, seg in zip(doc.steps, sorted_segs, strict=True)
        }
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_error_detail(
                "internal_segment_mismatch",
                "编译步骤数与视频分段数不一致",
            ),
        ) from exc

    try:
        saved = await vm.save(doc, keyframe_bytes=keyframe_bytes_by_step)
    except Exception as exc:
        logger.exception("VersionManager.save 失败")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_error_detail(
                "persist_failed",
                "关键帧上传或数据库写入失败",
                extra={"reason": str(exc)},
            ),
        ) from exc

    return SOPGenerateResponse(
        task_id=saved.sop_id,
        status="completed",
        sop_id=saved.sop_id,
    )


# ---------------------------------------------------------------------------
# Demo 种子路由（绕过数据库，供前端 Real 模式演示）
# ---------------------------------------------------------------------------

_DEMO_SOP_RESPONSE: dict[str, Any] = {
    "sop_id": "demo-battery-pack-01",
    "product_id": "NCM811-DEMO",
    "version": "v1.0",
    "demo_video_src": "/demo-sop-guide.mp4",
    "assumed_fps": 30,
    "steps": [
        {
            "step_id": 1,
            "action_type": "module_placement",
            "keyframe_index": 90,
            "keyframe_time_sec": 3,
            "title": "底壳放置与模组入位",
            "bullets": [
                "确认底壳二维码与工单一致",
                "模组导向销完全对准后再轻压入位",
                "检查模组四角与底壳卡槽贴合无翘起",
            ],
            "safety_note": "佩戴绝缘手套，禁止金属饰品接触极柱",
        },
        {
            "step_id": 2,
            "action_type": "busbar_connection",
            "keyframe_index": 660,
            "keyframe_time_sec": 22,
            "title": "母排连接与紧固",
            "bullets": [
                "母排对位后先手拧两圈确认螺纹咬合",
                "使用扭矩扳手按对角顺序紧固，额定扭矩 12 N·m",
                "回拉确认无松动，目视检查螺栓标记线对齐",
            ],
            "safety_note": "断电挂牌后方可操作高压母排，严禁带电作业",
        },
        {
            "step_id": 3,
            "action_type": "thermal_management",
            "keyframe_index": 825,
            "keyframe_time_sec": 27.5,
            "title": "热管理系统连接",
            "bullets": [
                "冷却管路快插接头插入至听到咔嗒声",
                "检查密封圈无破损、无外露",
                "接通后目视确认无滴漏",
            ],
            "safety_note": "确认冷却液阀门处于关闭状态后再操作",
        },
        {
            "step_id": 4,
            "action_type": "final_inspection",
            "keyframe_index": 1230,
            "keyframe_time_sec": 41,
            "title": "顶盖密封与最终质检",
            "bullets": [
                "沿密封槽均匀涂抹密封胶，厚度 0.5mm 以内",
                "顶盖就位后对角顺序锁紧固定螺栓",
                "关键螺栓标记线入镜拍照，上传 MES 存档",
            ],
            "safety_note": "涂胶后须在 10 分钟内完成合盖，超时需重新涂胶",
        },
    ],
}


@router.get(
    "/demo",
    summary="演示种子 SOP（绕过数据库）",
)
async def get_demo_sop() -> dict[str, Any]:
    """返回硬编码的演示 SOP 数据，无需 PostgreSQL。"""
    return _DEMO_SOP_RESPONSE


@router.get(
    "/{sop_id}",
    response_model=SOPDocument,
    summary="按 ID 查询 SOP 文档快照",
)
async def get_sop(
    request: Request,
    sop_id: str,
) -> SOPDocument:
    """读取 ``sop_versions`` 中的 JSON 快照；不存在返回 404 JSON。"""
    vm = _get_version_manager(request)
    if vm is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_error_detail(
                "storage_unavailable",
                "未配置 SOP_POSTGRES_DSN，无法查询 SOP",
            ),
        )

    doc = await vm.get(sop_id)
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_error_detail(
                "not_found",
                f"不存在 sop_id={sop_id!r} 的 SOP 文档",
            ),
        )
    return doc
