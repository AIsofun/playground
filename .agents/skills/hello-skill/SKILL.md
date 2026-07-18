---
name: hello-skill
description: 练习用的第一个 skill。当用户输入 /hello-skill 或要求打招呼演示时使用。
---

# Hello Skill

这是一个最小可用的 skill 示例。

## 你（Claude）收到这个 skill 时要做的事

1. 向用户问好，并告诉用户当前的工作目录。
2. 如果用户在命令后面带了参数（$ARGUMENTS），把参数原样复述一遍。
3. 用一句话总结这个 skill 演示了什么：SKILL.md 的指令会在调用时注入到对话中，Claude 按其中的步骤执行。
