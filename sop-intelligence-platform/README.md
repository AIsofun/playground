# SOP 智脑 — 动力电池装配 SOP 智能化平台

> 请参阅 SPEC.md 了解当前任务，AGENTS.md 了解开发规范。

# 确认 Ollama 可达
curl http://192.168.5.102:11434/v1/models

# 确认 .env 已配置（项目根目录）
# VLM_BASE_URL=http://192.168.5.102:11434/v1
# VLM_MODEL_NAME=qwen2.5vl:7b

# 启动后端
uvicorn src.api.main:app --host 0.0.0.0 --port 8000