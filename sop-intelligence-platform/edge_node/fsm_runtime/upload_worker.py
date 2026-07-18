"""UNCERTAIN 帧 gRPC 上送：独立线程消费队列，主线程仅 ``put_nowait``。

禁止在主线程调用本模块中的 ``_upload_one``；与 ``edge_node/AGENTS.md`` 第二节一致。
"""

from __future__ import annotations

import logging
import queue
import threading
from dataclasses import dataclass
from typing import Iterator

import grpc

from edge_node.proto_gen import frame_upload_pb2
from edge_node.proto_gen.frame_upload_pb2_grpc import FrameUploadServiceStub

_LOG = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class UncertainUploadJob:
    """一条待上送的 UNCERTAIN 帧（主线程构造，上传线程只读）。"""

    workstation_id: str
    sop_id: str
    sop_step: int
    captured_at_iso: str
    edge_confidence: float
    frame_jpeg: bytes
    fsm_state: str | None = None


def _chunk_messages(job: UncertainUploadJob) -> Iterator[frame_upload_pb2.FrameUploadChunk]:
    md = frame_upload_pb2.UncertainFrameMetadata(
        workstation_id=job.workstation_id,
        sop_id=job.sop_id,
        sop_step=int(job.sop_step),
        captured_at=job.captured_at_iso,
        edge_confidence=float(job.edge_confidence),
        edge_level=frame_upload_pb2.UNCERTAIN,
    )
    if job.fsm_state:
        md.fsm_state = job.fsm_state
    c0 = frame_upload_pb2.FrameUploadChunk()
    c0.metadata.CopyFrom(md)
    yield c0
    buf = job.frame_jpeg
    step = 64 * 1024
    for i in range(0, len(buf), step):
        c = frame_upload_pb2.FrameUploadChunk()
        c.jpeg_chunk = bytes(buf[i : i + step])
        yield c


def _upload_one(target: str, job: UncertainUploadJob, *, deadline_sec: float) -> None:
    channel = grpc.insecure_channel(target)
    try:
        stub = FrameUploadServiceStub(channel)
        stub.UploadUncertainFrame(_chunk_messages(job), timeout=float(deadline_sec))
    finally:
        channel.close()


class UncertainGrpcUploader:
    """后台线程消费 ``UncertainUploadJob`` 队列并调用 gRPC（同步 stub，阻塞仅限该线程）。"""

    def __init__(
        self,
        grpc_target: str,
        *,
        max_queue: int = 64,
        deadline_sec: float = 2.0,
    ) -> None:
        self._target = grpc_target.strip()
        self._deadline = float(deadline_sec)
        self._q: queue.Queue[UncertainUploadJob | None] = queue.Queue(maxsize=max_queue)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="edge-uncertain-uploader", daemon=True)
        self._thread.start()

    def stop(self, *, join_timeout: float = 5.0) -> None:
        self._stop.set()
        try:
            self._q.put_nowait(None)
        except queue.Full:
            pass
        if self._thread is not None:
            self._thread.join(timeout=join_timeout)
            self._thread = None

    def enqueue(self, job: UncertainUploadJob) -> bool:
        """主线程/推理路径调用：非阻塞；队列满则丢弃并返回 ``False``。"""
        if self._stop.is_set():
            return False
        try:
            self._q.put_nowait(job)
            return True
        except queue.Full:
            _LOG.warning("UNCERTAIN 上送队列已满，丢弃帧 workstation=%s", job.workstation_id)
            return False

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                item = self._q.get(timeout=0.25)
            except queue.Empty:
                continue
            if item is None:
                break
            try:
                _upload_one(self._target, item, deadline_sec=self._deadline)
            except Exception:
                _LOG.exception("gRPC UNCERTAIN 帧上送失败 target=%s", self._target)
