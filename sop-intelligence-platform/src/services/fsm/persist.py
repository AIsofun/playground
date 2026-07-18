"""将 ``SOPDocument`` 编译为 ``FSMGraph`` 并写入 PostgreSQL（编排层）。"""

from __future__ import annotations

from src.adapters.storage.postgres_client import FsmGraphRow, PostgresFsmGraphsClient, PostgresSopVersionsClient
from src.services.fsm.compiler import SOPToFSMCompiler
from src.types.fsm import FSMGraph
from src.types.sop import SOPDocument

__all__ = ["FsmGraphPersistService", "SopNotFoundForFsmError"]


class SopNotFoundForFsmError(Exception):
    """按 ``sop_id`` 未找到 SOP 快照，无法编译 FSM。"""

    def __init__(self, sop_id: str) -> None:
        self.sop_id = sop_id
        super().__init__(f"sop_id not found: {sop_id!r}")


def default_expert_video_duration_sec(doc: SOPDocument) -> float:
    """当调用方未显式传入专家视频时长时，用各步时间戳上界作保守估计（秒）。"""
    mt = max((s.video_timestamp for s in doc.steps), default=0.0)
    return max(1.0, float(mt))


class FsmGraphPersistService:
    """读 ``sop_versions`` → ``SOPToFSMCompiler`` → 写 ``fsm_graphs``。"""

    def __init__(
        self,
        sop_pg: PostgresSopVersionsClient,
        fsm_pg: PostgresFsmGraphsClient,
        compiler: SOPToFSMCompiler | None = None,
    ) -> None:
        self._sop = sop_pg
        self._fsm = fsm_pg
        self._compiler = compiler or SOPToFSMCompiler()

    async def compile_and_store(
        self,
        sop_id: str,
        *,
        expert_video_duration_sec: float | None = None,
    ) -> tuple[str, FSMGraph]:
        doc = await self._sop.get_sop_by_id(sop_id)
        if doc is None:
            raise SopNotFoundForFsmError(sop_id)
        duration = (
            float(expert_video_duration_sec)
            if expert_video_duration_sec is not None
            else default_expert_video_duration_sec(doc)
        )
        graph = self._compiler.compile(doc, expert_video_duration_sec=duration)
        fsm_id = await self._fsm.insert_graph(
            sop_id=doc.sop_id,
            product_id=doc.product_id,
            version=doc.version,
            expert_video_duration_sec=duration,
            graph=graph,
        )
        return fsm_id, graph

    async def get_topology(self, fsm_id: str) -> FsmGraphRow | None:
        return await self._fsm.get_by_fsm_id(fsm_id)

    async def get_latest_topology_for_sop(self, sop_id: str) -> FsmGraphRow | None:
        return await self._fsm.get_latest_by_sop_id(sop_id)
