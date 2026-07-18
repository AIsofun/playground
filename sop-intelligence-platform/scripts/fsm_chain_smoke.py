#!/usr/bin/env python3
"""Milestone 结案冒烟：内存 SOP → FSM 编译 → Runner + Detector → MATCH 步进。

在项目根目录执行::

    python scripts/fsm_chain_smoke.py

不访问数据库与网络；用于验证 T01–T04 导入链无 ImportError / 类型冲突。
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.services.fsm.compiler import SOPToFSMCompiler  # noqa: E402
from src.services.fsm.detector import ActionDetector  # noqa: E402
from src.services.fsm.runtime import FSMRunner  # noqa: E402
from src.types.sop import (  # noqa: E402
    ActionDetectionVerdict,
    ActionSegment,
    SOPDocument,
    SOPStep,
)


def _minimal_doc() -> SOPDocument:
    pid = f"SMOKE-{uuid.uuid4().hex[:6]}"
    ver = f"{pid}-v1.0"
    return SOPDocument(
        sop_id=str(uuid.uuid4()),
        product_id=pid,
        version=ver,
        steps=[
            SOPStep(
                step_id=1,
                description="取件",
                action_object="工件",
                keyframe_path="minio://sop-keyframes/smoke/step_1.jpg",
                video_timestamp=5.0,
                action_type="pick_part",
                warnings=[],
            ),
            SOPStep(
                step_id=2,
                description="装配",
                action_object="壳体",
                keyframe_path="minio://sop-keyframes/smoke/step_2.jpg",
                video_timestamp=12.0,
                action_type="assemble_shell",
                warnings=[],
            ),
        ],
        total_steps=2,
        created_at=datetime.now(timezone.utc),
        source_video_paths=["minio://sop-videos/smoke/demo.mp4"],
        status="draft",
    )


def main() -> int:
    doc = _minimal_doc()
    graph = SOPToFSMCompiler().compile(doc, expert_video_duration_sec=30.0)
    runner = FSMRunner(graph)
    detector = ActionDetector(conf_low=0.4, conf_high=0.7)

    seg = ActionSegment(
        segment_id=1,
        start_frame=0,
        end_frame=16,
        start_time_sec=0.0,
        end_time_sec=0.5,
        action_class="pick_part",
        confidence=0.92,
        keyframe_index=8,
    )
    node = graph.nodes["STEP_1"]
    verdict = detector.detect(seg, node)
    assert verdict is ActionDetectionVerdict.MATCH, verdict

    runner.handle_event(ActionDetectionVerdict.MATCH)
    ctx = runner.snapshot()
    assert ctx.current_node_id == "STEP_1", ctx.current_node_id

    print("fsm_chain_smoke: OK (compile → runner → detector MATCH → handle_event)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
