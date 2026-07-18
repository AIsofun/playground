"""视频分段：VideoParser 协议与多种实现（Mock / Demo / FFmpeg）。"""

from __future__ import annotations

import abc
import logging
import subprocess
import tempfile
from pathlib import Path

from src.types.sop import ActionSegment

from .fallbacks import MINIMAL_JPEG_BYTES

logger = logging.getLogger(__name__)


class VideoParser(abc.ABC):
    @abc.abstractmethod
    def parse(self, video_path: str) -> list[ActionSegment]:
        """返回按 ``start_time_sec`` 升序的 ``ActionSegment`` 列表。"""

    @abc.abstractmethod
    def extract_keyframe(self, video_path: str, frame_idx: int) -> bytes:
        """返回 JPEG 字节（应以 ``FF D8 FF`` 开头）。"""


_MOCK_SEGMENTS_DATA: list[dict[str, object]] = [
    {
        "segment_id": 1,
        "start_frame": 0,
        "end_frame": 16,
        "start_time_sec": 0.0,
        "end_time_sec": 0.53,
        "action_class": "pick_up_bolt",
        "confidence": 0.94,
        "keyframe_index": 8,
    },
    {
        "segment_id": 2,
        "start_frame": 16,
        "end_frame": 48,
        "start_time_sec": 0.53,
        "end_time_sec": 1.60,
        "action_class": "align_component",
        "confidence": 0.87,
        "keyframe_index": 32,
    },
    {
        "segment_id": 3,
        "start_frame": 48,
        "end_frame": 80,
        "start_time_sec": 1.60,
        "end_time_sec": 2.67,
        "action_class": "tighten_bolt",
        "confidence": 0.91,
        "keyframe_index": 64,
    },
    {
        "segment_id": 4,
        "start_frame": 80,
        "end_frame": 112,
        "start_time_sec": 2.67,
        "end_time_sec": 3.73,
        "action_class": "inspect_connection",
        "confidence": 0.78,
        "keyframe_index": 96,
    },
    {
        "segment_id": 5,
        "start_frame": 112,
        "end_frame": 144,
        "start_time_sec": 3.73,
        "end_time_sec": 4.80,
        "action_class": "place_component",
        "confidence": 0.85,
        "keyframe_index": 128,
    },
]


class MockVideoParser(VideoParser):
    """返回固定 5 段动作；不读磁盘；关键帧为占位 JPEG。"""

    def parse(self, video_path: str) -> list[ActionSegment]:  # noqa: ARG002
        segments = [ActionSegment(**data) for data in _MOCK_SEGMENTS_DATA]
        return sorted(segments, key=lambda seg: seg.start_time_sec)

    def extract_keyframe(self, video_path: str, frame_idx: int) -> bytes:  # noqa: ARG002
        return MINIMAL_JPEG_BYTES


# ---------------------------------------------------------------------------
# Demo 视频解析（规则分段 — 匹配电池包装配 4 步骤）
# ---------------------------------------------------------------------------

_DEMO_SEGMENTS_DATA: list[dict[str, object]] = [
    {
        "segment_id": 1,
        "start_frame": 0,
        "end_frame": 90,
        "start_time_sec": 0.0,
        "end_time_sec": 3.0,
        "action_class": "module_placement",
        "confidence": 0.95,
        "keyframe_index": 90,
    },
    {
        "segment_id": 2,
        "start_frame": 540,
        "end_frame": 780,
        "start_time_sec": 18.0,
        "end_time_sec": 26.0,
        "action_class": "busbar_connection",
        "confidence": 0.92,
        "keyframe_index": 660,
    },
    {
        "segment_id": 3,
        "start_frame": 810,
        "end_frame": 840,
        "start_time_sec": 27.0,
        "end_time_sec": 28.0,
        "action_class": "thermal_management",
        "confidence": 0.88,
        "keyframe_index": 825,
    },
    {
        "segment_id": 4,
        "start_frame": 1200,
        "end_frame": 1260,
        "start_time_sec": 40.0,
        "end_time_sec": 42.0,
        "action_class": "final_inspection",
        "confidence": 0.90,
        "keyframe_index": 1230,
    },
]


class DemoVideoParser(VideoParser):
    """规则分段：返回电池包装配 4 步骤硬编码片段，配合 FFmpeg 抽帧。

    当 ``use_ffmpeg=True`` 且系统有 ffmpeg 时使用真实抽帧，否则回退占位 JPEG。
    """

    def __init__(self, *, use_ffmpeg: bool = True) -> None:
        self._use_ffmpeg = use_ffmpeg

    def parse(self, video_path: str) -> list[ActionSegment]:  # noqa: ARG002
        segments = [ActionSegment(**data) for data in _DEMO_SEGMENTS_DATA]
        return sorted(segments, key=lambda seg: seg.start_time_sec)

    def extract_keyframe(self, video_path: str, frame_idx: int) -> bytes:
        if self._use_ffmpeg:
            return ffmpeg_extract_frame(video_path, frame_idx, fps=30)
        return MINIMAL_JPEG_BYTES


# ---------------------------------------------------------------------------
# FFmpeg 关键帧提取工具函数
# ---------------------------------------------------------------------------


def ffmpeg_extract_frame(video_path: str, frame_idx: int, *, fps: int = 30) -> bytes:
    """用 FFmpeg 从视频中提取指定帧号的 JPEG 字节。

    如果 FFmpeg 不可用或提取失败，回退到占位 JPEG。
    """
    timestamp = frame_idx / fps
    try:
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp_path = tmp.name

        cmd = [
            "ffmpeg",
            "-ss", f"{timestamp:.3f}",
            "-i", video_path,
            "-frames:v", "1",
            "-q:v", "2",
            "-y",
            tmp_path,
        ]
        result = subprocess.run(  # noqa: S603
            cmd,
            capture_output=True,
            timeout=10,
        )
        if result.returncode != 0:
            logger.warning("FFmpeg 抽帧失败 (rc=%d): %s", result.returncode, result.stderr[:200])
            return MINIMAL_JPEG_BYTES

        frame_bytes = Path(tmp_path).read_bytes()
        Path(tmp_path).unlink(missing_ok=True)

        if not frame_bytes or not frame_bytes[:3] == b"\xff\xd8\xff":
            logger.warning("FFmpeg 输出非有效 JPEG，回退占位图")
            return MINIMAL_JPEG_BYTES

        return frame_bytes
    except FileNotFoundError:
        logger.warning("FFmpeg 未安装，回退占位 JPEG")
        return MINIMAL_JPEG_BYTES
    except subprocess.TimeoutExpired:
        logger.warning("FFmpeg 抽帧超时，回退占位 JPEG")
        return MINIMAL_JPEG_BYTES
    except Exception:
        logger.exception("FFmpeg 抽帧异常")
        return MINIMAL_JPEG_BYTES
