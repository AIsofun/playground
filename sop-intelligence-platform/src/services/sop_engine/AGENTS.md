# AGENTS.md — sop_engine 子模块专属规则

> **覆盖范围**：本文件约束仅适用于 `src/services/sop_engine/` 目录下的所有代码修改。  
> 全局规则请见根目录 `AGENTS.md`，本文件是对全局规则的**补充和细化**，不替代全局规则。

---

## 一、模块职责边界

`sop_engine/` 是整个系统的**入口核心**，负责将专家操作视频转化为结构化 SOP 文档和 FSM 状态机。

```
video_parser.py     ← VideoMAE 动作分段（输入：视频片段，输出：原子动作序列 + 置信度）
vlm_annotator.py    ← Qwen2.5-VL-7B 语义理解（输入：关键帧 + 动作类别，输出：JSON 步骤描述）
sop_compiler.py     ← 组装 SOPDocument + 编译 Python transitions FSM
version_manager.py  ← SOP 版本 diff、快照存储（PostgreSQL + MinIO）
```

**禁止**：本模块不处理实时视频流，只处理**离线专家录制视频**。

---

## 二、VLM Prompt 修改规则（强制）

修改任何 VLM 调用的 Prompt 时，必须按以下顺序操作：

```
1. 修改 .ai/prompts/sop-generation.txt（Prompt 模板的版本化存储）
2. 在 tests/harness/sop_gen_eval/ 中准备对应的 eval_dataset（若行为变化）
3. 运行 tests/harness/sop_gen_eval/run_eval.py
4. 确认：步骤完整性 > 0.90，关键帧准确率 > 0.85
5. 在 commit message 中注明 "prompt: update sop-generation.txt"
```

**禁止**：在 `vlm_annotator.py` 中硬编码 Prompt，必须从 `.ai/prompts/` 加载模板文件。

---

## 三、SOP 文档格式约束

输出的 `SOPDocument` 必须严格遵循 `src/types/sop.py` 中定义的 Schema：

```python
# 每个 SOPStep 必须包含以下字段（不得为空）：
step_id: int           # 步骤编号（从 1 开始）
description: str       # 操作描述（中文，来自 VLM 输出）
keyframe_path: str     # 关键帧在 MinIO 中的路径
video_timestamp: float # 对应视频时间戳（秒）
action_type: str       # 动作类别（来自 VideoMAE）
warnings: list[str]    # 注意事项（可为空列表，不得为 None）
```

**FSM 编译规则**：
- FSM 状态名 = `f"STEP_{step_id}"`
- 初始状态 = `"STEP_0"`（工序开始前）
- 终止状态 = `"STEP_DONE"`
- 每个步骤超时阈值默认 300 秒，可在 `src/config/` 中覆盖

---

## 四、版本管理规则

- 每个 SOP 版本在 PostgreSQL `sop_versions` 表保留**完整快照**，不得覆盖历史版本
- 换型（产品型号变更）时：只录制差异片段，调用 `version_manager.diff_update()` 做增量更新
- 版本号格式：`{product_id}-v{major}.{minor}`，major 变更 = 整体重录，minor 变更 = 增量更新

---

## 五、禁止行为清单

- ❌ 在 `sop_compiler.py` 中调用 VLM API（VLM 调用只在 `vlm_annotator.py`）
- ❌ 在 `video_parser.py` 中直接写 MinIO（文件存储只在 `version_manager.py`）
- ❌ 输出 `SOPDocument` 时 `warnings` 字段为 `None`（必须为空列表）
- ❌ 修改 FSM 状态定义而不同步更新 `src/types/sop.py` 中的 `FSMState` 枚举
