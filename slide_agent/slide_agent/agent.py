"""WritingSystemAgent（SequentialAgent）—— TODO

参考复现计划第 7 节：
  - before_agent_callback：校验大纲 → parse_markdown_to_slides → outline_json
  - 内部串起 PPTGeneratorLoopAgent（LoopAgent）
"""


class WritingSystemAgent:
    """逐页内容生成系统智能体（占位，待用 google.adk 实现）"""

    def __init__(self):
        # TODO: 用 SequentialAgent + LoopAgent 构造
        pass

    async def generate(self, markdown: str, metadata: dict):
        """将 Markdown 大纲解析为 Slide Schema 并逐页撰写内容。"""
        raise NotImplementedError("TODO: 实现 WritingSystemAgent")
