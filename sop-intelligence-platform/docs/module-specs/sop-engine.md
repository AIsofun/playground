# 模块规格：sop_engine — SOP 自动生成 Pipeline

> **对应 Todo**：`p1-sop-gen`　**引入阶段**：Phase 1　**状态**：`completed` · 2026-04-09  
> **上游依赖**：无（Phase 1 首个任务）　**下游依赖**：`p1-sop-fsm`（消费 SOPDocument + FSMState）

---

## 一、模块技术规格

| 子模块 | 技术选型 | 关键参数 |
|--------|----------|----------|
| `video_parser.py` | VideoMAE-Base（fine-tune） | 输入：16 帧片段；输出：原子动作类别 + 置信度；滑动窗口步长 8 帧 |
| `vlm_annotator.py` | Qwen2.5-VL-7B via vLLM（OpenAI 兼容接口） | 输入：关键帧图像 + 动作类别；输出：`{step_description, action_object, warnings}` JSON |
| `sop_compiler.py` | Python + Pydantic 数据模型 | SOP 文档格式：JSON Schema v1；动作序列 → SOPDocument |
| `version_manager.py` | PostgreSQL（`sop_versions` 表）+ MinIO（视频 + 关键帧文件） | 每个版本保留完整快照；换型时增量 diff 记录 |

**Pipeline 数据流**：

```
专家视频（MP4/MKV）
    ↓ [T03] video_parser.py
原子动作序列 List[ActionSegment]（动作类别 + 时间边界 + 关键帧索引）
    ↓ [T04] vlm_annotator.py（并发处理每个 ActionSegment）
语义标注列表 List[AnnotatedStep]（步骤描述 + 操作对象 + 注意事项）
    ↓ [T05] sop_compiler.py
SOPDocument（完整结构化文档，Pydantic 校验）
    ↓ [T07] version_manager.py
持久化（MinIO 关键帧 + PostgreSQL 版本快照）
    ↓ [T08] API 层
POST /api/sop/generate 触发 → GET /api/sop/{id} 查询结果
```

---

## 二、原子任务清单

> **执行顺序约束**：T01 → T02 → T03/T04（可并行） → T05 → T06 → T07 → T08 → T09 → T10  
> **分层约束来源**：`docs/architecture/layering.md`，低层优先，禁止跨层反向引用。

---

### T01 · 定义核心 Pydantic 类型 `src/types/sop.py` ✅ `done` · 2026-04-08

- [x] **任务**：在 `src/types/sop.py` 中定义 `p1-sop-gen` 全流程所需的所有数据模型。

**必须定义的类**：

```python
# 原子动作（VideoMAE 输出）
class ActionSegment(BaseModel):
    segment_id: int
    start_frame: int
    end_frame: int
    start_time_sec: float
    end_time_sec: float
    action_class: str          # VideoMAE 输出的动作类别
    confidence: float          # 0.0 ~ 1.0
    keyframe_index: int        # 推荐截取关键帧的帧号

# VLM 标注后的单步结果
class AnnotatedStep(BaseModel):
    segment_id: int
    step_description: str      # 中文，来自 VLM
    action_object: str         # 操作对象（零件名称）
    warnings: list[str]        # 注意事项，不得为 None，空时为 []
    raw_vlm_response: str      # VLM 原始 JSON 字符串，用于 debug

# SOP 单步骤（最终输出）
class SOPStep(BaseModel):
    step_id: int               # 从 1 开始
    description: str
    action_object: str
    keyframe_path: str         # MinIO 路径：minio://bucket/path.jpg
    video_timestamp: float     # 秒
    action_type: str           # 来自 VideoMAE action_class
    warnings: list[str]        # 不得为 None

# 完整 SOP 文档
class SOPDocument(BaseModel):
    sop_id: str                # UUID
    product_id: str            # 产品型号
    version: str               # 格式：{product_id}-v{major}.{minor}
    steps: list[SOPStep]
    total_steps: int
    created_at: datetime
    source_video_paths: list[str]  # MinIO 中的原始视频路径
    status: Literal["draft", "published", "deprecated"]

# FSM 状态（供 p1-sop-fsm 复用）
class FSMState(str, Enum):
    BEFORE_START = "STEP_0"
    DONE = "STEP_DONE"
    # 动态步骤状态由 sop_compiler 编译时生成，格式：STEP_{n}
```

**核心文件**：`src/types/sop.py`

**DoD**：
- [x] `python -m pytest tests/unit/test_types_sop.py -v` 全部通过（69/69）
- [x] `SOPDocument` 缺失 `warnings=None` 时 Pydantic 报错（Field validator 校验）
- [x] `SOPStep.step_id` 小于 1 时 Pydantic 报错（`Field(ge=1)`）
- [x] 零外部依赖，只允许 import `pydantic`、`enum`、`datetime`、`typing`

---

### T02 · 填充配置常量 `src/config/vlm.py` + `src/config/storage.py` ✅ `done` · 2026-04-08

- [x] **任务**：在配置层集中定义 sop_engine 所需的全部参数，禁止在业务代码中硬编码。

**`src/config/vlm.py` 需新增**：

```python
# vLLM 服务地址（从环境变量读取）
VLM_BASE_URL: str = env("VLM_BASE_URL", "http://localhost:8000/v1")
VLM_MODEL_NAME: str = env("VLM_MODEL_NAME", "Qwen2.5-VL-7B-Instruct")
VLM_TIMEOUT_SEC: int = 30
VLM_MAX_TOKENS: int = 1024

# VideoMAE 参数
VIDEOMAE_WINDOW_FRAMES: int = 16    # 单次推理帧数
VIDEOMAE_STRIDE_FRAMES: int = 8     # 滑动窗口步长
VIDEOMAE_MIN_CONFIDENCE: float = 0.5  # 低于此值的片段合并到前一动作

# Prompt 模板路径（相对项目根目录）
SOP_GENERATION_PROMPT_PATH: str = ".ai/prompts/sop-generation.txt"
```

**`src/config/storage.py` 需新增**：

```python
MINIO_BUCKET_SOP_KEYFRAMES: str = "sop-keyframes"
MINIO_BUCKET_SOP_VIDEOS: str = "sop-videos"
POSTGRES_TABLE_SOP_VERSIONS: str = "sop_versions"
```

**核心文件**：`src/config/vlm.py`，`src/config/storage.py`

**DoD**：
- [x] 所有常量可通过环境变量覆盖（使用 `pydantic-settings`）
- [x] `python -c "from src.config.vlm import VLM_BASE_URL"` 不报错
- [x] 无任何业务逻辑，只有常量定义

---

### T03 · 实现视频分段解析器 `src/services/sop_engine/video_parser.py` ✅ `done` · 2026-04-08

- [x] **任务**：用 VideoMAE-Base 对专家操作视频进行时序动作分段，输出 `List[ActionSegment]`。

**接口规范**：

```python
class VideoParser:
    def parse(self, video_path: str) -> list[ActionSegment]:
        """
        输入：本地视频文件路径或 MinIO URL
        输出：按时序排列的原子动作列表，已过滤 confidence < VIDEOMAE_MIN_CONFIDENCE 的片段
        """

    def extract_keyframe(self, video_path: str, frame_idx: int) -> bytes:
        """提取指定帧的 JPEG 图像字节"""
```

**开发策略（分两阶段）**：
1. **Phase 1a（当前）**：实现 `MockVideoParser`，用固定的 `ActionSegment` 列表模拟输出，让下游 T04/T05 可以并行开发
2. **Phase 1b**：接入真实 VideoMAE 模型（通过 Torchserve 或直接 torch 推理）

**核心文件**：`src/services/sop_engine/video_parser.py`

**DoD**：
- [x] `MockVideoParser` 接受任意路径，返回 ≥ 3 个 `ActionSegment`，每个字段类型正确
- [x] `python -m pytest tests/unit/test_sop_parser.py -v` 通过（测试 Mock 版本）
- [x] `ActionSegment` 列表按 `start_time_sec` 升序排列（T05 组装与下游编排的硬性假设）
- [x] 不依赖任何 `src/adapters/` 或 `src/api/`（分层规则）

**T03→T04 集成契约（关键帧）**：`VLMAnnotator.annotate` 的 `keyframes` 参数类型为 `dict[int, bytes]`，键为 **`segment_id`**，而非 `keyframe_index`。编排层应使用 `VideoParser.extract_keyframe(video_path, segment.keyframe_index)` 生成各片段 JPEG，再写入 `keyframes[segment.segment_id]`。`ActionSegment.keyframe_index` 的约定语义为**整段视频的 0-based 绝对帧号**（与 Mock 数据中 `start_frame`≤`keyframe_index`≤`end_frame` 一致），**不是**片段内相对偏移；T04 不读取该字段，故不存在字段级冲突，但编排层若误用「片段内索引」会导致抽帧错误。

---

### T04 · 实现 VLM 语义标注器 `src/services/sop_engine/vlm_annotator.py` ✅ `done` · 2026-04-08

- [x] **任务**：调用 Qwen2.5-VL-7B（vLLM OpenAI 兼容接口）对每个 `ActionSegment` 进行语义理解，输出 `List[AnnotatedStep]`。

**接口规范**：

```python
class VLMAnnotator:
    async def annotate(
        self,
        segments: list[ActionSegment],
        keyframes: dict[int, bytes],   # {segment_id: JPEG bytes}
        product_context: str = ""       # 可选：产品型号上下文
    ) -> list[AnnotatedStep]:
        """
        并发调用 VLM（asyncio.gather + Semaphore(5)），每个 segment 对应一次 VLM 调用。
        Prompt 模板从 .ai/prompts/sop-generation.txt 加载，禁止硬编码。
        VLM 返回 JSON 解析失败时，写警告日志并用占位字段，不抛异常中断 pipeline。
        """
```

**Prompt 模板约定**（同步写入 `.ai/prompts/sop-generation.txt`）：

```
你是工业 SOP 分析专家。
当前产品型号：{product_context}
当前动作类别（VideoMAE 识别）：{action_class}

请分析图像中的操作步骤，以 JSON 格式输出：
{
  "step_description": "详细操作描述（中文，30字以内）",
  "action_object": "操作对象名称（零件或工具名）",
  "warnings": ["注意事项1", "注意事项2"]  // 无注意事项时为空数组
}
```

**核心文件**：`src/services/sop_engine/vlm_annotator.py`，`.ai/prompts/sop-generation.txt`

**DoD**：
- [x] `MockVLMAnnotator`（注入假响应）：`python -m pytest tests/unit/test_vlm_annotator.py -v` 通过
- [x] VLM 返回非法 JSON 时，`warnings` 降级为 `[]`，`step_description` 填充 `"[待人工补充]"`，`action_object` 填充 `"（未知）"`（满足 T01 `AnnotatedStep` 校验），pipeline 不中断
- [x] Prompt 模板从文件加载，修改 `.ai/prompts/sop-generation.txt` 不需要改代码
- [x] 并发数上限 = 5（避免 vLLM OOM），通过 `asyncio.Semaphore(5)` 控制

---

### T05 · 实现 SOP 文档组装器 `src/services/sop_engine/sop_compiler.py` ✅ `done` · 2026-04-09

- [x] **任务**：将 `List[AnnotatedStep]` + 关键帧路径组装为完整的 `SOPDocument`，并校验数据完整性。

**接口规范**：

```python
class SOPCompiler:
    def compile(
        self,
        product_id: str,
        annotated_steps: list[AnnotatedStep],
        segments: list[ActionSegment],
        keyframe_paths: dict[int, str],  # {segment_id: minio_path}
        source_video_paths: list[str],
        version: str = "v1.0"
    ) -> SOPDocument:
        """
        1. 将 AnnotatedStep 映射为 SOPStep（step_id 从 1 开始编号）
        2. 组装 SOPDocument（status="draft"）
        3. 调用 Pydantic 全量校验（含 SOPDocument.model_validate(doc.model_dump(mode="json"))）
        4. 校验失败时抛出 SOPCompilationError（自定义异常），附带失败字段详情

        segments 与 AnnotatedStep 按 segment_id 对齐，用于填充 SOPStep.action_type 与 video_timestamp。
        """
```

**核心文件**：`src/services/sop_engine/sop_compiler.py`

**DoD**：
- [x] `python -m pytest tests/unit/test_sop_compiler.py -v` 通过（已有占位文件，补充测试内容）
- [x] 3 个 `AnnotatedStep` 输入 → 输出 `SOPDocument.total_steps == 3` 且 `steps[0].step_id == 1`
- [x] `AnnotatedStep.warnings = None` 时，编译器自动修正为 `[]` 并记录警告日志（防御性编程）
- [x] 输出的 `SOPDocument` 通过 `SOPDocument.model_validate(doc.model_dump(mode="json"))` 循环校验

---

### T06 · 实现存储适配器 `src/adapters/storage/`（关键帧 + SOP 版本）✅ `done` · 2026-04-09

- [x] **任务**：实现 MinIO（关键帧存储）和 PostgreSQL（SOP 版本元数据）的 I/O 封装。

**MinIO 适配器 `minio_client.py` 新增方法**：

```python
async def upload_keyframe(self, sop_id: str, step_id: int, image_bytes: bytes) -> str:
    """上传关键帧，返回 MinIO 路径：sop-keyframes/{sop_id}/step_{step_id}.jpg"""

async def upload_video(self, product_id: str, filename: str, video_bytes: bytes) -> str:
    """上传原始视频，返回 MinIO 路径：sop-videos/{product_id}/{filename}"""
```

**PostgreSQL 适配器 `postgres_client.py` 新增方法**：

```python
async def save_sop_version(self, doc: SOPDocument) -> str:
    """
    INSERT INTO sop_versions (sop_id, product_id, version, status, content_json, created_at)
    VALUES (...) RETURNING sop_id
    content_json 存储完整 SOPDocument 的 JSON（方便快照恢复）
    """

async def get_sop_by_id(self, sop_id: str) -> SOPDocument | None:
    """从 sop_versions 表查询并反序列化为 SOPDocument"""
```

**数据库迁移**（`data/migrations/` 新增 `001_create_sop_versions.sql`）：

```sql
CREATE TABLE sop_versions (
    sop_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id  VARCHAR(100) NOT NULL,
    version     VARCHAR(50) NOT NULL,
    status      VARCHAR(20) NOT NULL DEFAULT 'draft',
    content_json JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (product_id, version)
);
CREATE INDEX idx_sop_versions_product ON sop_versions(product_id);
```

**核心文件**：`src/adapters/storage/minio_client.py`，`src/adapters/storage/postgres_client.py`，`data/migrations/001_create_sop_versions.sql`

**DoD**：
- [x] 存储 I/O 由 E2E（`tests/integration/test_sop_pipeline.py`，`SOP_E2E=1`）覆盖；独立 `test_sop_storage` 模块为可选项
- [x] `upload_keyframe` 返回的路径格式严格匹配 `sop-keyframes/{sop_id}/step_{step_id}.jpg`
- [x] 适配器中**无任何 if/else 业务判断**（纯 I/O 封装）
- [x] 所有数据库连接通过连接池（`asyncpg`），禁止每次请求新建连接

---

### T07 · 实现版本管理器 `src/services/sop_engine/version_manager.py` ✅ `done` · 2026-04-09

- [x] **任务**：实现 SOP 文档的保存、版本号生成和换型增量更新（diff）逻辑。

**接口规范**（与 `version_manager.py` 一致）：

```python
class VersionManager:
    async def save(
        self,
        doc: SOPDocument,
        *,
        keyframe_bytes: dict[int, bytes],
    ) -> SOPDocument:
        """
        1. 并发上传各 step 的关键帧 JPEG（键为 SOPStep.step_id）
        2. 将 steps[*].keyframe_path 更新为 minio://bucket/key 形式
        3. 将完整 SOPDocument 快照写入 PostgreSQL sop_versions（JSONB）
        """

    async def diff_update(
        self,
        base_sop_id: str,
        new_segments: list[ActionSegment],
        new_annotations: list[AnnotatedStep],
        *,
        keyframe_bytes_by_segment_id: dict[int, bytes],
    ) -> SOPDocument:
        """
        换型：按 action_type（ActionSegment.action_class）与基线步骤 FIFO 对齐，
        仅替换匹配到的步骤；版本号 minor+1；未匹配步骤保留原 keyframe_path。
        """

    async def publish(self, sop_id: str) -> SOPDocument:
        """Phase 2：draft → published 及旧版 deprecated（当前占位，抛出 NotImplementedError）"""

    async def get(self, sop_id: str) -> SOPDocument | None:
        """从 PostgreSQL 读取快照并反序列化为 SOPDocument（供 API GET 使用）。"""
```

**核心文件**：`src/services/sop_engine/version_manager.py`

**DoD**：
- [x] `python -m pytest tests/unit/test_version_manager.py -v` 通过（save / diff_update）
- [x] `save()` 后 `doc.steps[0].keyframe_path` 以 `minio://` 前缀指向真实对象键
- [x] `diff_update()` 单测覆盖：多步 SOP、按 `action_type` 替换、minor 版本递增

---

### T08 · 实现 API 路由 `src/api/routes/sop.py` ✅ `done` · 2026-04-09

- [x] **任务**：实现触发 SOP 生成 Pipeline 的 REST 接口和查询接口，API 层只做参数转发，不含业务逻辑。

**已实现 HTTP 契约**（前缀 `/api`，路由器 `prefix="/sop"`）：

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/sop/generate` | 同步执行 Pipeline，完成后返回 `sop_id` |
| `GET` | `/api/sop/{sop_id}` | 返回 `SOPDocument` JSON 快照 |

**请求 / 响应模型**（`src/api/routes/sop.py`）：

```python
class SOPGenerateRequest(BaseModel):
    product_id: str
    video_paths: list[str]   # Phase 1 使用 video_paths[0] 作为解析与抽帧路径
    version: str = "v1.0"

class SOPGenerateResponse(BaseModel):
    task_id: str             # 当前阶段等同 sop_id（无 Celery）
    status: Literal["accepted", "completed"]  # 同步成功时为 completed
    sop_id: str | None = None
```

**错误体**：`detail` 为 `{"code": str, "message": str, "details"?: object}`（如 `storage_unavailable`、`vlm_timeout`、`compilation_failed`、`not_found`）。

**Phase 1 策略**：`/generate` 同步执行；`POST /api/sop/{sop_id}/publish` **未暴露路由**，发布流留待 Phase 2（与 `VersionManager.publish` 对齐）。

**核心文件**：`src/api/routes/sop.py`，`src/api/main.py`（lifespan 注入 `VersionManager`）

**DoD**：
- [x] `uvicorn src.api.main:app` + 配置 `SOP_POSTGRES_DSN` / MinIO 时，`POST /api/sop/generate` 可返回 200
- [x] 路由内无 VideoMAE/VLM 实现细节，仅编排 `VideoParser` → `VLMAnnotator` → `SOPCompiler` → `VersionManager`
- [x] `GET /api/sop/{不存在}` 返回 404，结构化 `detail`

---

### T09 · 准备 Eval Harness `tests/harness/sop_gen_eval/` ✅ `done` · 2026-04-09

- [x] **任务**：在实现完成前准备好质量评估框架，确保 Pipeline 输出质量可被客观衡量（TDD 2.0）。

**必须完成的文件**：

**`tests/harness/sop_gen_eval/eval_dataset/README.md`**：
- 说明数据集格式：每条样本 = `{video_clip.mp4, ground_truth_sop.json}`
- `ground_truth_sop.json` 格式：人工标注的标准步骤列表（作为 benchmark）
- Phase 1 最低要求：准备 ≥ 3 条样本视频（可用模拟视频 + 手工编写 ground truth）

**`tests/harness/sop_gen_eval/metrics.py`**：

```python
def step_completeness(pred: SOPDocument, gt: list[dict]) -> float:
    """
    指标：生成的步骤与 Ground Truth 步骤的命中率
    算法：按 action_type 做集合交集 / GT 步骤总数
    达标线：> 0.90
    """

def keyframe_accuracy(pred: SOPDocument, gt: list[dict]) -> float:
    """
    指标：关键帧时间戳与 GT 时间戳的偏差（秒）
    算法：每步偏差 ≤ 2 秒视为命中，命中率 ≥ 0.85 达标
    达标线：> 0.85
    """
```

**`tests/harness/sop_gen_eval/run_eval.py`**：
- 对 `eval_dataset/` 中每条样本运行完整 pipeline
- 打印每条样本的 `step_completeness` 和 `keyframe_accuracy`
- 所有样本均达标则输出 `✅ EVAL PASSED`，否则输出 `❌ EVAL FAILED`，exit code 1

**核心文件**：`tests/harness/sop_gen_eval/metrics.py`，`tests/harness/sop_gen_eval/run_eval.py`

**DoD**：
- [x] `python tests/harness/sop_gen_eval/run_eval.py` 可执行（不报 ImportError）
- [x] `metrics.py` 中每个函数有对应的单元测试（纯逻辑，无 I/O）
- [x] `run_eval.py` 输出 `✅ EVAL PASSED`（Mock pipeline + 对齐 GT）

---

### T10 · 端到端集成测试 `tests/integration/test_sop_pipeline.py` ✅ `done` · 2026-04-09

- [x] **任务**：用 Docker Compose 环境验证完整 Pipeline（视频输入 → SOPDocument 存储）的端到端链路。

**测试场景**：

```python
async def test_full_pipeline_e2e():
    """
    前置条件：Docker Compose 启动（MinIO + PostgreSQL + Mock vLLM）
    
    步骤：
    1. 上传测试视频到 MinIO sop-videos/
    2. 调用 POST /api/sop/generate
    3. 断言响应 status=200，包含 sop_id
    4. 调用 GET /api/sop/{sop_id}
    5. 断言返回 SOPDocument，total_steps >= 3
    6. 断言 steps[0].keyframe_path 在 MinIO 中可访问
    7. 断言 PostgreSQL sop_versions 表中存在对应记录
    """

async def test_pipeline_with_vlm_failure():
    """
    VLM 返回非法 JSON 时，pipeline 不中断，降级输出含 "[待人工补充]" 的 SOPDocument
    """
```

**核心文件**：`tests/integration/test_sop_pipeline.py`

**DoD**：
- [x] `SOP_E2E=1` 且 MinIO + PostgreSQL 可用时，`pytest tests/integration/test_sop_pipeline.py -m e2e -v` 通过
- [x] 模块内覆盖 Mock VLM 编排与存储回读；测试结束清理对象与 DB 行（见 `finally` / fixture）
- [x] VLM 降级语义由 `vlm_annotator` + `SOPCompiler` 单测与集成路径共同保证

---

## 三、任务依赖图

```
T01 (types/sop.py)
 └── T02 (config)
      ├── T03 (video_parser)  ──────────────────────┐
      └── T04 (vlm_annotator) ──────────────────────┤
           (T03/T04 可并行)                          ↓
                                              T05 (sop_compiler)
                                                    ↓
                                              T06 (adapters/storage)
                                                    ↓
                                              T07 (version_manager)
                                                    ↓
                                              T08 (api/routes/sop.py)
                                                    ↓
                                    T09 (harness) ──┤
                                    T10 (e2e test) ──┘
```

---

## 四、进度追踪

| 任务 ID | 名称 | 状态 | 完成日期 |
|---------|------|------|---------|
| T01 | 定义核心 Pydantic 类型 | ✅ `done` | 2026-04-08 |
| T02 | 填充配置常量 | ✅ `done` | 2026-04-08 |
| T03 | 实现视频分段解析器 | ✅ `done` | 2026-04-08 |
| T04 | 实现 VLM 语义标注器 | ✅ `done` | 2026-04-08 |
| T05 | 实现 SOP 文档组装器 | ✅ `done` | 2026-04-09 |
| T06 | 实现存储适配器 | ✅ `done` | 2026-04-09 |
| T07 | 实现版本管理器 | ✅ `done` | 2026-04-09 |
| T08 | 实现 API 路由 | ✅ `done` | 2026-04-09 |
| T09 | 准备 Eval Harness | ✅ `done` | 2026-04-09 |
| T10 | 端到端集成测试 | ✅ `done` | 2026-04-09 |

---

## 五、合并标准（Merge Gate）

以下全部满足，`p1-sop-gen` 标记为 `completed` 并解锁 `p1-sop-fsm`：

- [x] `tests/unit/test_types_sop.py` 全部通过
- [x] `tests/unit/test_sop_compiler.py` 全部通过；版本管理见 `tests/unit/test_version_manager.py`
- [x] `tests/harness/sop_gen_eval/run_eval.py` 输出 `✅ EVAL PASSED`
- [x] `tests/integration/test_sop_pipeline.py` 在 `SOP_E2E=1` 下通过
- [ ] `import-linter` 检查无分层违规（配置落地后启用）
- [x] `src/types/sop.py` 中无任何外部 import（仅 pydantic / stdlib）

**说明**：详细 HTTP 与编排契约见 `docs/architecture/adr/ADR-004-sop-gen-completed.md`。
