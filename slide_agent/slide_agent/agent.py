"""WritingSystemAgent —— 逐页内容生成系统智能体。

流程（参考复现计划 7.1/7.2）：
  大纲解析 → Slide Schema → 逐页循环（Writer 生成 → Checker 校验 → Controller 推进）
可选：use_kb=True 时，每页生成前先检索知识库（personaldb）注入参考内容。
"""
import json
import logging

from .sub_agents.ppt_writer.agent import CheckerAgent, ControllerAgent, PPTWriterSubAgent
from .sub_agents.ppt_writer.tools import knowledge_base_search
from .utils import parse_markdown_to_slides

logger = logging.getLogger(__name__)


class WritingSystemAgent:
    """把 Markdown 大纲解析为 Slide Schema 并逐页撰写内容。"""

    def __init__(
        self,
        provider: str,
        model: str,
        max_retries: int = 3,
        use_kb: bool = False,
        user_id: str = "1",
    ):
        self.provider = provider
        self.model = model
        self.use_kb = use_kb
        self.user_id = user_id
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

        if self.use_kb:
            query = (slide.get("data") or {}).get("title", "") or slide_type
            try:
                results = await knowledge_base_search(query, top_k=3, user_id=self.user_id)
                if results:
                    kb_text = "\n".join(r.get("text", "")[:500] for r in results)
                    context += f"\n\n知识库参考内容：\n{kb_text}"
            except Exception:  # noqa: BLE001 —— 知识库不可用不影响生成
                pass

        for _ in range(self.controller.max_retries):
            try:
                text = await self.writer.write(slide_type, context, self.provider, self.model)
            except Exception as e:  # noqa: BLE001 —— LLM/网络失败视为本轮失败，重试下一轮
                logger.warning("页面 %s 生成失败，重试：%s", slide_type, e)
                continue
            data = self.checker.check(text)
            if data is not None:
                return data
        logger.warning("页面 %s 重试耗尽，跳过", slide_type)
        return None  # 重试耗尽，跳过该页（不中断整体流程）
