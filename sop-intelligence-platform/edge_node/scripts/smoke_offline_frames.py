#!/usr/bin/env python3
"""离线/模拟帧循环 smoke：主路径只做分档 + ``put_nowait``，gRPC 仅在 ``--grpc`` 时由后台线程执行。

用法（仓库根目录，已安装 ``edge_node/requirements.txt``）::

    python edge_node/scripts/smoke_offline_frames.py
    python edge_node/scripts/smoke_offline_frames.py --grpc --grpc-target 127.0.0.1:50051

说明见 ``edge_node/README.md``。
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# 仓库根加入 sys.path，保证 ``import edge_node`` 可用
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from edge_node.fsm_runtime import (  # noqa: E402
    ComplianceBand,
    UncertainGrpcUploader,
    UncertainUploadJob,
    classify_edge_score,
)

_LOG = logging.getLogger("smoke")


def _tiny_jpeg() -> bytes:
    """极小微型 JPEG 头 +填充，仅作载荷占位（非有效图像）。"""
    return b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00" + b"\xff\xd9"


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    p = argparse.ArgumentParser(description="edge_node 离线帧 smoke")
    p.add_argument("--frames", type=int, default=40, help="模拟帧数")
    p.add_argument("--grpc", action="store_true", help="启用后台 gRPC 上送线程")
    p.add_argument("--grpc-target", default="127.0.0.1:50051", help="FrameUploadService 地址 host:port")
    p.add_argument("--workstation-id", default="smoke-ws-01")
    p.add_argument("--sop-id", default="00000000-0000-4000-8000-000000000099")
    args = p.parse_args()

    uploader: UncertainGrpcUploader | None = None
    if args.grpc:
        uploader = UncertainGrpcUploader(args.grpc_target, max_queue=32, deadline_sec=2.0)
        uploader.start()
        _LOG.info("已启动 UNCERTAIN gRPC 上送线程 → %s", args.grpc_target)

    counts: dict[ComplianceBand, int] = {b: 0 for b in ComplianceBand}
    uncertain_enqueued = 0

    for i in range(args.frames):
        # 扫过阈值两侧，制造 UNCERTAIN / VIOLATION / COMPLIANT 混合
        score = 0.28 + (i % 12) * 0.04
        crit = i % 17 == 0
        band = classify_edge_score(score, critical_rule_triggered=crit)
        counts[band] += 1

        if band is ComplianceBand.UNCERTAIN and uploader is not None:
            job = UncertainUploadJob(
                workstation_id=args.workstation_id,
                sop_id=args.sop_id,
                sop_step=i % 5,
                captured_at_iso=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
                edge_confidence=float(score),
                frame_jpeg=_tiny_jpeg(),
                fsm_state="SMOKE_STATE",
            )
            if uploader.enqueue(job):
                uncertain_enqueued += 1

        # 主路径不做阻塞 I/O
        time.sleep(0.001)

    if uploader is not None:
        uploader.stop(join_timeout=5.0)

    _LOG.info("分档计数: %s", {k.value: v for k, v in counts.items()})
    if args.grpc:
        _LOG.info("UNCERTAIN 入队成功条数: %s", uncertain_enqueued)
    else:
        _LOG.info("未启用 --grpc；仅验证分档逻辑（零网络）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
