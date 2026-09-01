"""WritingSystemAgent —— 逐页内容生成系统智能体。

流程（参考复现计划 7.1/7.2）：
  大纲解析 → Slide Schema → 逐页循环（Writer 生成 → Checker 校验 → Controller 推进）
"""
import json

from .sub_agents.ppt_writer.agent import CheckerAgent, ControllerAgent, PPTWriterSubAgent
from .utils import parse_markdown_to_slides


class WritingSystemAgent:
    """把 Markdown 大纲解析为 Slide Schema 并逐页撰写内容。"""

    def __init__(self, provider: str, model: str, max_retries: int = 3):
        self.provider = provider
        self.model = model
        self.writer = PPTWriterSubAgent()
        self.checker = CheckerAgent()
        self.controller = ControllerAgent(max_retries=max_retries)

    async def generate(self, markdown: str, on_slide=None) -> list[dict]:
        outline = parse_markdown_to_slides(markdown)
        results: list[dict] = []
        for slide in outline:
            data = await self._generate_one(slide)
            if data is not None:
                results.append(data)
                if on_slide is not None:
                    await on_slide(data)
        return results

    async def _generate_one(self, slide: dict) -> dict | None:
        """单页生成：Writer 撰写 → Checker 校验 → 失败重试（≤ max_retries）。"""
        slide_type = slide.get("type", "content")
        context = json.dumps(slide, ensure_ascii=False)
        for _ in range(self.controller.max_retries):
            text = await self.writer.write(slide_type, context, self.provider, self.model)
            data = self.checker.check(text)
            if data is not None:
                return data
        return None  # 重试耗尽，跳过该页（不中断整体流程）
