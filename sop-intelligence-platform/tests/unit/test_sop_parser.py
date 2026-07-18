"""
tests/unit/test_sop_parser.py
==============================

T03 · MockVideoParser 单元测试（TDD 2.0）

测试策略：
    先编写完整测试用例（红灯），再实现 MockVideoParser（绿灯），
    最后重构保持绿灯——严格遵循 TDD Red→Green→Refactor 循环。

覆盖的测试场景：
    1. parse() 返回列表且元素数量 >= 3
    2. 所有元素均为 ActionSegment 实例，字段类型正确
    3. 列表按 start_time_sec 升序排列（T03 DoD 硬性要求）
    4. confidence 值在 [0.0, 1.0] 范围内
    5. start_time_sec < end_time_sec（时间边界合理）
    6. start_frame < end_frame（帧号边界合理）
    7. segment_id 唯一且从 1 开始递增
    8. parse() 对任意路径输入均不抛出异常（mock 行为）
    9. extract_keyframe() 返回非空 bytes
    10. extract_keyframe() 返回的字节以 JPEG 魔术字节开头（可选强验证）
    11. MockVideoParser 不依赖任何文件系统 I/O（视频路径不需要真实存在）
    12. VideoParser 接口协议：MockVideoParser 满足 VideoParser 鸭子类型

注意：所有测试均基于 MockVideoParser（Phase 1a），不涉及真实 VideoMAE 模型。
"""

from __future__ import annotations

import pytest

from src.types.sop import ActionSegment
from src.services.sop_engine.video_parser import MockVideoParser, VideoParser


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def parser() -> MockVideoParser:
    """构造一个 MockVideoParser 实例，供所有测试复用。"""
    return MockVideoParser()


@pytest.fixture
def segments(parser: MockVideoParser) -> list[ActionSegment]:
    """调用 parse() 获取动作片段列表，供多个测试共享。"""
    return parser.parse("any/path/to/video.mp4")


# ---------------------------------------------------------------------------
# T03 DoD — 核心需求测试
# ---------------------------------------------------------------------------


class TestMockVideoParserParse:
    """测试 MockVideoParser.parse() 方法。"""

    def test_returns_list(self, segments: list[ActionSegment]) -> None:
        """parse() 必须返回一个列表。"""
        assert isinstance(segments, list), "parse() 应返回 list 类型"

    def test_returns_at_least_three_segments(self, segments: list[ActionSegment]) -> None:
        """DoD 要求：返回 >= 3 个 ActionSegment。"""
        assert len(segments) >= 3, (
            f"parse() 应返回至少 3 个 ActionSegment，实际返回 {len(segments)} 个"
        )

    def test_all_elements_are_action_segment(self, segments: list[ActionSegment]) -> None:
        """列表中每个元素都必须是 ActionSegment 实例。"""
        for i, seg in enumerate(segments):
            assert isinstance(seg, ActionSegment), (
                f"第 {i} 个元素应为 ActionSegment，实际类型为 {type(seg)}"
            )

    def test_sorted_by_start_time_sec_ascending(self, segments: list[ActionSegment]) -> None:
        """DoD 核心要求：ActionSegment 列表必须按 start_time_sec 升序排列。"""
        times = [seg.start_time_sec for seg in segments]
        assert times == sorted(times), (
            f"ActionSegment 列表应按 start_time_sec 升序排列，"
            f"实际 start_time_sec 序列为 {times}"
        )

    def test_no_overlapping_start_times(self, segments: list[ActionSegment]) -> None:
        """相邻片段的 start_time_sec 必须严格递增（无重叠）。"""
        for i in range(1, len(segments)):
            assert segments[i].start_time_sec > segments[i - 1].start_time_sec, (
                f"片段 {i} 的 start_time_sec ({segments[i].start_time_sec}) "
                f"应大于前一片段 ({segments[i - 1].start_time_sec})"
            )

    def test_confidence_in_valid_range(self, segments: list[ActionSegment]) -> None:
        """confidence 必须在 [0.0, 1.0] 范围内（Pydantic 验证保证）。"""
        for seg in segments:
            assert 0.0 <= seg.confidence <= 1.0, (
                f"片段 {seg.segment_id} 的 confidence ({seg.confidence}) 超出 [0.0, 1.0]"
            )

    def test_time_boundaries_valid(self, segments: list[ActionSegment]) -> None:
        """每个片段的 start_time_sec 必须严格小于 end_time_sec。"""
        for seg in segments:
            assert seg.start_time_sec < seg.end_time_sec, (
                f"片段 {seg.segment_id}: start_time_sec ({seg.start_time_sec}) "
                f"应 < end_time_sec ({seg.end_time_sec})"
            )

    def test_frame_boundaries_valid(self, segments: list[ActionSegment]) -> None:
        """每个片段的 start_frame 必须严格小于 end_frame。"""
        for seg in segments:
            assert seg.start_frame < seg.end_frame, (
                f"片段 {seg.segment_id}: start_frame ({seg.start_frame}) "
                f"应 < end_frame ({seg.end_frame})"
            )

    def test_segment_ids_are_unique(self, segments: list[ActionSegment]) -> None:
        """所有 segment_id 必须唯一。"""
        ids = [seg.segment_id for seg in segments]
        assert len(ids) == len(set(ids)), (
            f"segment_id 存在重复：{[x for x in ids if ids.count(x) > 1]}"
        )

    def test_segment_ids_start_from_one(self, segments: list[ActionSegment]) -> None:
        """segment_id 应从 1 开始，且按序递增。"""
        ids = sorted(seg.segment_id for seg in segments)
        assert ids[0] == 1, f"最小 segment_id 应为 1，实际为 {ids[0]}"

    def test_action_class_is_nonempty_string(self, segments: list[ActionSegment]) -> None:
        """action_class 必须是非空字符串。"""
        for seg in segments:
            assert isinstance(seg.action_class, str) and len(seg.action_class) > 0, (
                f"片段 {seg.segment_id} 的 action_class 应为非空字符串，"
                f"实际值：{seg.action_class!r}"
            )

    def test_keyframe_index_is_nonnegative(self, segments: list[ActionSegment]) -> None:
        """keyframe_index 必须为非负整数。"""
        for seg in segments:
            assert isinstance(seg.keyframe_index, int) and seg.keyframe_index >= 0, (
                f"片段 {seg.segment_id} 的 keyframe_index ({seg.keyframe_index}) 应为非负整数"
            )

    def test_start_time_sec_is_nonnegative(self, segments: list[ActionSegment]) -> None:
        """start_time_sec 必须为非负浮点数。"""
        for seg in segments:
            assert seg.start_time_sec >= 0.0, (
                f"片段 {seg.segment_id} 的 start_time_sec ({seg.start_time_sec}) 应 >= 0.0"
            )

    def test_accepts_arbitrary_path(self, parser: MockVideoParser) -> None:
        """MockVideoParser 对任意路径均不抛出异常（mock 行为，不读取真实文件）。"""
        arbitrary_paths = [
            "nonexistent/video.mp4",
            "/absolute/path/video.mkv",
            "minio://sop-videos/prod/demo.mp4",
            "",
            "C:\\Windows\\System32\\fake.avi",
        ]
        for path in arbitrary_paths:
            result = parser.parse(path)
            assert isinstance(result, list) and len(result) >= 3, (
                f"路径 {path!r} 应正常返回 >= 3 个片段"
            )

    def test_repeated_calls_return_same_structure(self, parser: MockVideoParser) -> None:
        """多次调用 parse() 应返回结构一致的结果（幂等性）。"""
        result1 = parser.parse("video.mp4")
        result2 = parser.parse("video.mp4")
        assert len(result1) == len(result2), "多次调用 parse() 应返回相同数量的片段"
        for s1, s2 in zip(result1, result2):
            assert s1.segment_id == s2.segment_id
            assert s1.action_class == s2.action_class
            assert s1.start_time_sec == s2.start_time_sec


# ---------------------------------------------------------------------------
# extract_keyframe 测试
# ---------------------------------------------------------------------------


class TestMockVideoParserExtractKeyframe:
    """测试 MockVideoParser.extract_keyframe() 方法。"""

    def test_returns_bytes(self, parser: MockVideoParser) -> None:
        """extract_keyframe() 必须返回 bytes 类型。"""
        result = parser.extract_keyframe("video.mp4", 8)
        assert isinstance(result, bytes), (
            f"extract_keyframe() 应返回 bytes，实际类型：{type(result)}"
        )

    def test_returns_nonempty_bytes(self, parser: MockVideoParser) -> None:
        """返回的 bytes 不得为空。"""
        result = parser.extract_keyframe("video.mp4", 8)
        assert len(result) > 0, "extract_keyframe() 不应返回空 bytes"

    def test_returns_jpeg_magic_bytes(self, parser: MockVideoParser) -> None:
        """返回的 bytes 应以 JPEG 魔术字节 (0xFF 0xD8 0xFF) 开头。"""
        result = parser.extract_keyframe("video.mp4", 0)
        assert result[:3] == b"\xff\xd8\xff", (
            f"extract_keyframe() 应返回有效 JPEG bytes，"
            f"实际开头：{result[:3].hex()}"
        )

    def test_accepts_arbitrary_frame_idx(self, parser: MockVideoParser) -> None:
        """对任意合理帧号均不抛出异常。"""
        for frame_idx in [0, 1, 8, 100, 9999]:
            result = parser.extract_keyframe("video.mp4", frame_idx)
            assert isinstance(result, bytes) and len(result) > 0


# ---------------------------------------------------------------------------
# 接口协议测试 — VideoParser 鸭子类型
# ---------------------------------------------------------------------------


class TestVideoParserInterface:
    """验证 MockVideoParser 满足 VideoParser 接口约定。"""

    def test_mock_is_instance_of_video_parser(self, parser: MockVideoParser) -> None:
        """MockVideoParser 必须是 VideoParser 的子类。"""
        assert isinstance(parser, VideoParser), (
            "MockVideoParser 应继承自 VideoParser"
        )

    def test_has_parse_method(self, parser: MockVideoParser) -> None:
        """MockVideoParser 必须具有 parse 方法。"""
        assert hasattr(parser, "parse") and callable(parser.parse)

    def test_has_extract_keyframe_method(self, parser: MockVideoParser) -> None:
        """MockVideoParser 必须具有 extract_keyframe 方法。"""
        assert hasattr(parser, "extract_keyframe") and callable(parser.extract_keyframe)


# ---------------------------------------------------------------------------
# 分层规则测试 — 禁止依赖 adapters/api 层
# ---------------------------------------------------------------------------


class TestLayeringConstraints:
    """验证 video_parser 模块不违反分层架构约束。"""

    def test_no_adapters_import(self) -> None:
        """video_parser 模块不得 import src.adapters 中的任何模块。"""
        import re

        import src.services.sop_engine.video_parser as vp_module

        source_file = vp_module.__file__
        assert source_file is not None
        with open(source_file, encoding="utf-8") as f:
            source = f.read()

        # 只检测真实的 import 语句，忽略注释和文档字符串中的说明性文本
        import_pattern = re.compile(
            r"^\s*(?:import|from)\s+src\.adapters", re.MULTILINE
        )
        assert not import_pattern.search(source), (
            "video_parser.py 不得 import src.adapters（违反分层规则）"
        )

    def test_no_api_import(self) -> None:
        """video_parser 模块不得 import src.api 中的任何模块。"""
        import re

        import src.services.sop_engine.video_parser as vp_module

        source_file = vp_module.__file__
        assert source_file is not None
        with open(source_file, encoding="utf-8") as f:
            source = f.read()

        # 只检测真实的 import 语句，忽略注释和文档字符串中的说明性文本
        import_pattern = re.compile(
            r"^\s*(?:import|from)\s+src\.api", re.MULTILINE
        )
        assert not import_pattern.search(source), (
            "video_parser.py 不得 import src.api（违反分层规则）"
        )
