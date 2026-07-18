"""将 ``AnnotatedStep`` + ``ActionSegment`` + 关键帧路径编译为 ``SOPDocument``（禁止调用 VLM）。"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError

from src.types.sop import (
    ActionSegment,
    AnnotatedStep,
    SOPDocument,
    SOPStep,
)

from .fallbacks import FALLBACK_ACTION_OBJECT, FALLBACK_STEP_DESCRIPTION

logger = logging.getLogger(__name__)

__all__ = ["SOPCompilationError", "SOPCompiler"]


class SOPCompilationError(Exception):
    """SOP 编译失败：输入不完整或全量校验未通过。"""

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.details: dict[str, Any] = details or {}


class SOPCompiler:
    """将标注步骤与关键帧路径组装为 `SOPDocument`。"""

    def compile(
        self,
        product_id: str,
        annotated_steps: list[AnnotatedStep],
        segments: list[ActionSegment],
        keyframe_paths: dict[int, str],
        source_video_paths: list[str],
        version: str = "v1.0",
    ) -> SOPDocument:
        """
        1. 将 AnnotatedStep 映射为 SOPStep（step_id 按 segment_id 升序从 1 编号）
        2. 组装 SOPDocument（status=\"draft\"）
        3. 调用 Pydantic 全量校验（含往返 ``model_validate(model_dump())``）
        4. 校验失败时抛出 SOPCompilationError，附带失败字段详情

        Args:
            product_id: 产品型号。
            annotated_steps: VLM 标注列表（可与 segments 中 segment_id 交错顺序）。
            segments: VideoMAE 片段列表，按 segment_id 提供 action_class 与时间戳。
            keyframe_paths: ``segment_id -> minio://...`` 路径。
            source_video_paths: 源视频 MinIO 路径列表。
            version: 版本后缀（如 ``v1.0``），或与 product_id 组合的完整版本串。

        Returns:
            通过全量校验的 SOPDocument。

        Raises:
            SOPCompilationError: 输入缺失或与 Schema 不一致。
        """
        if not annotated_steps:
            raise SOPCompilationError(
                "至少需要 1 个 AnnotatedStep 才能生成 SOPDocument",
                details={"annotated_steps": "empty"},
            )

        segment_by_id: dict[int, ActionSegment] = {s.segment_id: s for s in segments}
        sorted_ann = sorted(annotated_steps, key=lambda a: a.segment_id)

        sop_steps: list[SOPStep] = []
        for idx, ann in enumerate(sorted_ann, start=1):
            sid = ann.segment_id
            if sid not in segment_by_id:
                raise SOPCompilationError(
                    f"segment_id={sid} 在 segments 中不存在，无法填充 action_type / video_timestamp",
                    details={"missing_segment_id": sid, "available": list(segment_by_id.keys())},
                )
            if sid not in keyframe_paths:
                raise SOPCompilationError(
                    f"segment_id={sid} 缺少 keyframe_paths 条目",
                    details={"missing_keyframe_for": sid, "paths_keys": list(keyframe_paths.keys())},
                )

            normalized = _normalize_annotated_step(ann)
            seg = segment_by_id[sid]
            path = keyframe_paths[sid].strip()
            if not path:
                raise SOPCompilationError(
                    f"segment_id={sid} 的 keyframe 路径为空",
                    details={"segment_id": sid},
                )

            sop_steps.append(
                SOPStep(
                    step_id=idx,
                    description=normalized.step_description,
                    action_object=normalized.action_object,
                    keyframe_path=path,
                    video_timestamp=seg.start_time_sec,
                    action_type=seg.action_class,
                    warnings=normalized.warnings,
                )
            )

        full_version = _compose_version(product_id, version)
        created = datetime.now(timezone.utc)
        sop_id = str(uuid.uuid4())

        try:
            doc = SOPDocument(
                sop_id=sop_id,
                product_id=product_id,
                version=full_version,
                steps=sop_steps,
                total_steps=len(sop_steps),
                created_at=created,
                source_video_paths=source_video_paths,
                status="draft",
            )
        except ValidationError as exc:
            raise SOPCompilationError(
                "SOPDocument 初始构造未通过 Pydantic 校验",
                details={"errors": exc.errors()},
            ) from exc

        try:
            return SOPDocument.model_validate(doc.model_dump(mode="json"))
        except ValidationError as exc:
            raise SOPCompilationError(
                "SOPDocument 往返全量校验失败",
                details={"errors": exc.errors()},
            ) from exc


def _compose_version(product_id: str, version: str) -> str:
    if version.startswith(product_id):
        return version
    return f"{product_id}-{version}"


def _normalize_annotated_step(step: AnnotatedStep) -> AnnotatedStep:
    """防御性规范化：修正 ``warnings is None``；无法通过 Schema 时按 VLM 降级规则填充。"""
    dumped: dict[str, Any] = step.model_dump()
    if dumped.get("warnings") is None:
        logger.warning(
            "segment_id=%s：AnnotatedStep.warnings 为 None，已修正为 []",
            dumped.get("segment_id"),
        )
        dumped["warnings"] = []

    try:
        return AnnotatedStep.model_validate(dumped)
    except ValidationError as exc:
        sid = dumped.get("segment_id", getattr(step, "segment_id", 0))
        raw = dumped.get("raw_vlm_response", "")
        if not isinstance(raw, str):
            raw = str(raw)
        logger.warning(
            "segment_id=%s：AnnotatedStep 全量校验失败（%s），使用 VLM 非法 JSON 同级降级占位值",
            sid,
            exc.errors(),
        )
        return AnnotatedStep(
            segment_id=int(sid) if sid is not None else 0,
            step_description=FALLBACK_STEP_DESCRIPTION,
            action_object=FALLBACK_ACTION_OBJECT,
            warnings=[],
            raw_vlm_response=raw,
        )
