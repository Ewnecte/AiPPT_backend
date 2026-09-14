"""多 Agent PPT 生成内核（B + E）。

模块划分：
  llm.py             统一 LLM 客户端（真实 litellm / 离线脚本化 FakeLLM），统计 token
  tool_registry.py   工具白名单 + JSON Schema 参数强校验 + 沙箱写文件
  image_safety.py    配图内容安全审核 + 版权来源说明
  orchestrator.py    多 Agent 编排：Planner 决策 → 工具执行 → 观察，含循环熔断
  deck_validate.py   成稿结构校验（PPT 可正常打开/页数与结构合规）
  evaluate.py        ③ 任务级评估：50 个任务跑指标
  ab_compare.py      ⑤ 单 Agent vs 多 Agent 三维对比
  demo_breaker.py    演示桥段：反复重写大纲 → 熔断 + 部分结果
"""

__all__ = ["llm", "tool_registry", "image_safety", "orchestrator", "deck_validate"]
