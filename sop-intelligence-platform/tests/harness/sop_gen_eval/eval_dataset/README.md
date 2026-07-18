# sop_gen_eval 评测集（Phase 1）

每条样本为一个子目录，需包含：

- `video_clip.mp4` — 专家操作视频片段（Mock 阶段可为占位文件，`MockVideoParser` 不读取磁盘）
- `ground_truth_sop.json` — 人工标注的标准步骤列表，用于计算 Recall（`step_completeness`）与关键帧准确率

## `ground_truth_sop.json` 格式

支持两种结构：

1. JSON 数组，每项字段与 `SOPStep` 评测子集对齐：
   - `action_type`（必填）
   - `video_timestamp`（必填，秒，与 `SOPStep.video_timestamp` 一致）
   - `step_id`（可选；若每条均有，则按 `step_id` 升序再与预测做贪心对齐）

2. 或对象：`{ "steps": [ ... ], "product_id": "可选" }`

指标定义见 `tests/harness/sop_gen_eval/metrics.py`。
