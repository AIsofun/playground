"""
SOP 引擎领域类型定义 — src/types/sop.py
=========================================

定义 p1-sop-gen 全流程所需的所有 Pydantic 数据模型：

    ActionSegment   — VideoMAE 输出的原子动作片段
    AnnotatedStep   — VLM 语义标注后的单步结果
    SOPStep         — SOP 最终输出的单步骤
    SOPDocument     — 完整的 SOP 文档
    FSMState               — FSM 状态枚举（供 p1-sop-fsm 复用）
    ActionDetectionVerdict — 实时动作与 FSM 期望的判定枚举（供合规 / FSM 对齐）

架构约束（来自 docs/architecture/layering.md）：
    - 仅允许依赖 pydantic、enum、datetime、typing（标准库）
    - 禁止任何外部 I/O 或非标准库 import
    - 所有公开符号必须有 docstring
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# ActionSegment — VideoMAE 原子动作片段
# ---------------------------------------------------------------------------


class ActionSegment(BaseModel):
    """VideoMAE 模型输出的原子动作片段。

    代表视频中一段连续的操作动作，包含时间边界、动作类别、
    置信度和推荐关键帧索引。

    约束：
        confidence 必须在 [0.0, 1.0] 范围内。
        start_time_sec 必须严格小于 end_time_sec。
        start_frame 必须严格小于 end_frame。

    示例：
        >>> seg = ActionSegment(
        ...     segment_id=1,
        ...     start_frame=0,
        ...     end_frame=16,
        ...     start_time_sec=0.0,
        ...     end_time_sec=0.53,
        ...     action_class="pick_up_bolt",
        ...     confidence=0.92,
        ...     keyframe_index=8,
        ... )
    """

    segment_id: int = Field(..., description="片段唯一编号，从 1 开始")
    start_frame: int = Field(..., ge=0, description="起始帧号（含）")
    end_frame: int = Field(..., ge=0, description="结束帧号（含）")
    start_time_sec: float = Field(..., ge=0.0, description="起始时间（秒）")
    end_time_sec: float = Field(..., ge=0.0, description="结束时间（秒）")
    action_class: str = Field(..., min_length=1, description="VideoMAE 识别的动作类别")
    confidence: float = Field(..., ge=0.0, le=1.0, description="动作置信度，范围 [0.0, 1.0]")
    keyframe_index: int = Field(..., ge=0, description="推荐截取关键帧的帧号")

    @field_validator("end_frame")
    @classmethod
    def _end_frame_after_start(cls, v: int, info: object) -> int:
        """end_frame 必须严格大于 start_frame。"""
        start = getattr(info, "data", {}).get("start_frame")
        if start is not None and v <= start:
            raise ValueError(
                f"end_frame ({v}) 必须严格大于 start_frame ({start})"
            )
        return v

    @field_validator("end_time_sec")
    @classmethod
    def _end_time_after_start(cls, v: float, info: object) -> float:
        """end_time_sec 必须严格大于 start_time_sec。"""
        start = getattr(info, "data", {}).get("start_time_sec")
        if start is not None and v <= start:
            raise ValueError(
                f"end_time_sec ({v}) 必须严格大于 start_time_sec ({start})"
            )
        return v


# ---------------------------------------------------------------------------
# AnnotatedStep — VLM 语义标注后的单步结果
# ---------------------------------------------------------------------------


class AnnotatedStep(BaseModel):
    """VLM（Qwen2.5-VL-7B）对单个 ActionSegment 进行语义理解后的输出。

    每个 AnnotatedStep 对应一个 ActionSegment，包含中文步骤描述、
    操作对象和注意事项列表。

    约束：
        warnings 不得为 None，无注意事项时使用空列表 []。
        raw_vlm_response 保留 VLM 原始 JSON 字符串，用于 debug。

    示例：
        >>> step = AnnotatedStep(
        ...     segment_id=1,
        ...     step_description="用扳手拧紧螺栓至规定扭矩",
        ...     action_object="M8螺栓",
        ...     warnings=["注意扭矩不超过 25N·m"],
        ...     raw_vlm_response='{"step_description": "...", ...}',
        ... )
    """

    segment_id: int = Field(..., description="对应 ActionSegment 的编号")
    step_description: str = Field(..., min_length=1, description="中文操作步骤描述，来自 VLM 输出")
    action_object: str = Field(..., min_length=1, description="操作对象（零件或工具名称）")
    warnings: list[str] = Field(
        default_factory=list,
        description="注意事项列表，无注意事项时为空列表，不得为 None",
    )
    raw_vlm_response: str = Field(..., description="VLM 原始 JSON 响应字符串，用于 debug")


# ---------------------------------------------------------------------------
# SOPStep — SOP 最终输出的单步骤
# ---------------------------------------------------------------------------


class SOPStep(BaseModel):
    """SOP 文档中的单个执行步骤（最终输出）。

    由 SOPCompiler 将 AnnotatedStep + 关键帧路径组装而成，
    代表 SOP 文档的一个具体操作步骤。

    约束：
        step_id 从 1 开始，必须 >= 1。
        warnings 不得为 None，无注意事项时使用空列表 []。
        keyframe_path 为 MinIO 路径，格式：minio://bucket/path.jpg。

    示例：
        >>> sop_step = SOPStep(
        ...     step_id=1,
        ...     description="用扳手拧紧螺栓至规定扭矩",
        ...     action_object="M8螺栓",
        ...     keyframe_path="minio://sop-keyframes/abc/step_1.jpg",
        ...     video_timestamp=1.5,
        ...     action_type="tighten_bolt",
        ...     warnings=["注意扭矩不超过 25N·m"],
        ... )
    """

    step_id: int = Field(..., ge=1, description="步骤编号，从 1 开始")
    description: str = Field(..., min_length=1, description="操作步骤描述（中文）")
    action_object: str = Field(..., min_length=1, description="操作对象名称（零件或工具）")
    keyframe_path: str = Field(..., min_length=1, description="MinIO 关键帧路径，格式：minio://bucket/path.jpg")
    video_timestamp: float = Field(..., ge=0.0, description="对应视频时间戳（秒）")
    action_type: str = Field(..., min_length=1, description="动作类别，来自 VideoMAE action_class")
    warnings: list[str] = Field(
        default_factory=list,
        description="注意事项列表，不得为 None",
    )


# ---------------------------------------------------------------------------
# SOPDocument — 完整 SOP 文档
# ---------------------------------------------------------------------------


class SOPDocument(BaseModel):
    """完整的 SOP（标准操作程序）文档。

    由 SOPCompiler 组装，包含所有步骤和文档元数据。
    每个 SOPDocument 在 PostgreSQL sop_versions 表中保留完整快照。

    约束：
        sop_id 为 UUID 字符串。
        version 格式：{product_id}-v{major}.{minor}，如 PROD-001-v1.0。
        status 只能是 "draft"、"published"、"deprecated" 之一。
        total_steps 必须与 steps 列表长度一致。

    示例：
        >>> doc = SOPDocument(
        ...     sop_id="550e8400-e29b-41d4-a716-446655440000",
        ...     product_id="PROD-001",
        ...     version="PROD-001-v1.0",
        ...     steps=[...],
        ...     total_steps=3,
        ...     created_at=datetime.utcnow(),
        ...     source_video_paths=["minio://sop-videos/PROD-001/demo.mp4"],
        ...     status="draft",
        ... )
    """

    sop_id: str = Field(..., min_length=1, description="文档唯一标识（UUID）")
    product_id: str = Field(..., min_length=1, description="产品型号")
    version: str = Field(..., min_length=1, description="版本号，格式：{product_id}-v{major}.{minor}")
    steps: list[SOPStep] = Field(..., min_length=1, description="有序步骤列表，至少 1 个")
    total_steps: int = Field(..., ge=1, description="步骤总数，必须与 steps 列表长度一致")
    created_at: datetime = Field(..., description="文档创建时间（UTC）")
    source_video_paths: list[str] = Field(
        ...,
        min_length=1,
        description="MinIO 中原始视频文件路径列表",
    )
    status: Literal["draft", "published", "deprecated"] = Field(
        default="draft",
        description="文档状态：draft（草稿）/ published（已发布）/ deprecated（已弃用）",
    )

    @field_validator("total_steps")
    @classmethod
    def _total_steps_matches_list(cls, v: int, info: object) -> int:
        """total_steps 必须与 steps 列表实际长度一致。"""
        steps = getattr(info, "data", {}).get("steps")
        if steps is not None and v != len(steps):
            raise ValueError(
                f"total_steps ({v}) 与 steps 列表长度 ({len(steps)}) 不一致，"
                "请确保 total_steps == len(steps)"
            )
        return v


# ---------------------------------------------------------------------------
# ActionDetectionVerdict — 动作观测 vs FSM 期望
# ---------------------------------------------------------------------------


class ActionDetectionVerdict(str, enum.Enum):
    """将 VideoMAE 输出的 `ActionSegment` 与当前 `FSMNode.action_type` 对齐时的判定。

    与 `src/config/vlm.py` 中 ``CONF_LOW`` / ``CONF_HIGH`` 配合使用：低置信度观测
    不得直接记为匹配（工业现场抗干扰）。

    值：
        MATCH:      置信度达到高阈且动作类别与期望一致。
        MISMATCH:   置信度达到可采纳下阈，但动作类别与期望不一致。
        UNCERTAIN:  置信度不足、或期望动作处于未定义边界（如起止节点）。
    """

    MATCH = "MATCH"
    MISMATCH = "MISMATCH"
    UNCERTAIN = "UNCERTAIN"


# ---------------------------------------------------------------------------
# FSMState — FSM 状态枚举
# ---------------------------------------------------------------------------


class FSMState(str, enum.Enum):
    """SOP 执行 FSM（有限状态机）的基础状态枚举。

    动态步骤状态（如 STEP_1、STEP_2 等）由 sop_compiler 在运行时
    动态生成，格式为 STEP_{n}（n 为步骤编号）。

    值：
        BEFORE_START: 工序开始前的初始状态，对应 FSM 状态名 "STEP_0"。
        DONE:         工序完成后的终止状态，对应 FSM 状态名 "STEP_DONE"。

    示例：
        >>> state = FSMState.BEFORE_START
        >>> assert state.value == "STEP_0"
    """

    BEFORE_START = "STEP_0"
    DONE = "STEP_DONE"
