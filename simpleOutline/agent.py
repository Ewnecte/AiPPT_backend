"""OutlineAgent（LlmAgent）—— TODO

参考复现计划第 6 节：
  - tools=[DocumentSearch]
  - 动态指令：按输入长度选择 WITH_SEARCH / NO_SEARCH（见 prompt.py）
  - after_tool_callback 把文章写入 metadata["tool_document_ids"]
"""
from typing import Optional


class OutlineAgent:
    """大纲生成智能体（占位，待用 google.adk 实现）"""

    def __init__(self, model: str, tools: Optional[list] = None):
        self.model = model
        self.tools = tools or []
        # TODO: 用 google.adk.agents.llm_agent.LlmAgent 构造真正的 Agent

    async def generate(self, content: str, language: str):
        """根据输入流式生成 Markdown 大纲。"""
        raise NotImplementedError("TODO: 实现大纲生成逻辑")
