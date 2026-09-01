"""Writer / Checker / Controller + LoopAgent —— TODO

参考复现计划第 7.2 节（多智能体循环核心）：
  LoopAgent(max_iterations=200)
    ├─ PPTWriterSubAgent  (LlmAgent, tools=[KnowledgeBaseSearch, SearchImage])
    ├─ CheckerAgent       (规则校验 JSON，不调 LLM)
    └─ ControllerAgent    (通过→推进页码；失败→重试≤3次→跳过；末页→escalate 终止)
"""


class PPTWriterSubAgent:
    """按页面类型 Prompt 生成/扩写 JSON（LlmAgent）。"""
    def __init__(self):
        pass


class CheckerAgent:
    """规则校验 JSON（截取 → json.loads → validate_slide），不调用 LLM。"""
    def __init__(self):
        pass


class ControllerAgent:
    """推进/重试控制。"""
    def __init__(self):
        pass
