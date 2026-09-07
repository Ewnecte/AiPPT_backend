"""WritingSystemAgent —— 逐页内容生成系统智能体。

流程（参考复现计划 7.1/7.2）：
  大纲解析 → Slide Schema → 逐页循环（Writer 生成 → Checker 校验 → Controller 推进）
可选增强：
  - use_kb=True：每页生成前先检索个人知识库（personaldb）注入参考内容；
  - use_web=True：按整个大纲的章节标题异步预取联网搜索（微信文章）材料，
    每页生成前把对应标题命中的文章标题/正文片段注入上下文（失败静默降级）。
"""
import asyncio
import json
import logging

from .sub_agents.ppt_writer.agent import CheckerAgent, ControllerAgent, PPTWriterSubAgent
from .sub_agents.ppt_writer.tools import document_search, inject_images, knowledge_base_search
from .utils import parse_markdown_to_slides

logger = logging.getLogger(__name__)

# 联网搜索并发上限（网络 IO 放线程池 + 信号量限流，避免一次性打爆外部搜索）
_WEB_SEMAPHORE = asyncio.Semaphore(4)
_WEB_QUERY_LIMIT = 8  # 一次生成最多预取的查询数（超出取前几章）
_WEB_ARTICLE_PER_QUERY = 2  # 每个查询保留的文章数
_WEB_ARTICLE_PREFIX = 400  # 每篇文章注入的正文前缀长度
_WEB_TOTAL_LIMIT = 2000  # 每页注入的联网材料总长度上限


class WritingSystemAgent:
    """把 Markdown 大纲解析为 Slide Schema 并逐页撰写内容。"""

    def __init__(
        self,
        provider: str,
        model: str,
        max_retries: int = 3,
        use_kb: bool = False,
        use_web: bool = False,
        user_id: str = "1",
        use_chart: bool = False,
    ):
        self.provider = provider
        self.model = model
        self.use_kb = use_kb
        self.use_web = use_web
        self.user_id = user_id
        self.use_chart = use_chart
        self.writer = PPTWriterSubAgent()
        self.checker = CheckerAgent()
        self.controller = ControllerAgent(max_retries=max_retries)
        # 联网材料缓存：query(title) -> 拼好的参考文本，逐页生成时直接取
        self._web_cache: dict[str, str] = {}

    async def generate(self, markdown: str, on_slide=None) -> list[dict]:
        outline = parse_markdown_to_slides(markdown)
        if self.use_web:
            await self._prefetch_web(outline)
        results: list[dict] = []
        for slide in outline:
            data = await self._generate_one(slide)
            if data is not None:
                results.append(data)
                if on_slide is not None:
                    await on_slide(data)
        return results

    # ------------------------------------------------------------ 联网搜索
    @staticmethod
    def _page_query(slide: dict) -> str:
        """从一页里抽出用于搜索的查询词（页面标题，无则跳过）。"""
        return str(((slide.get("data") or {}).get("title") or "")).strip()

    async def _prefetch_web(self, outline: list[dict]) -> None:
        """按大纲各页标题并行预取联网材料，缓存到 self._web_cache。

        只取前 _WEB_QUERY_LIMIT 个不重复标题；网络/解析失败自动跳过，
        不阻塞、不影响后续生成（宁缺毋滥）。
        """
        queries: list[str] = []
        seen: set[str] = set()
        for slide in outline:
            q = self._page_query(slide)
            if q and q not in seen and len(queries) < _WEB_QUERY_LIMIT:
                seen.add(q)
                queries.append(q)
        if not queries:
            return

        async def fetch(q: str) -> tuple[str, str]:
            try:
                async with _WEB_SEMAPHORE:
                    articles = await asyncio.wait_for(
                        document_search(q, top_n=_WEB_ARTICLE_PER_QUERY), timeout=12
                    )
                return q, self._format_material(q, articles)
            except Exception as e:  # noqa: BLE001 —— 搜索失败不影响生成
                logger.info("联网搜索失败（已跳过）：%s -> %s", q, e)
                return q, ""

        results = await asyncio.gather(*(fetch(q) for q in queries))
        self._web_cache = dict(results)
        hit = sum(1 for _, m in results if m)
        if hit:
            logger.info("联网搜索完成：%d/%d 个标题命中材料", hit, len(queries))

    def _format_material(self, query: str, articles: list[dict]) -> str:
        """把搜索结果拼成「标题(链接)+正文片段」文本，供 Writer 参考。"""
        parts: list[str] = []
        for a in articles:
            content = (a.get("content") or "").strip()[:_WEB_ARTICLE_PREFIX]
            if not content:
                continue
            title = (a.get("title") or "").strip()
            url = (a.get("real_url") or "").strip()
            head = f"《{title}》" + (f"（{url}）" if url else "")
            parts.append(f"{head}\n{content}")
        if not parts:
            return ""
        joined = "\n\n".join(parts)
        if len(joined) > _WEB_TOTAL_LIMIT:
            joined = joined[:_WEB_TOTAL_LIMIT]
        return f"（关于「{query}」的联网搜索结果）\n{joined}"

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

        if self.use_web:
            material = self._web_cache.get(self._page_query(slide), "")
            if material:
                context += f"\n\n联网搜索参考内容：\n{material}"

        for _ in range(self.controller.max_retries):
            try:
                text = await self.writer.write(
                    slide_type, context, self.provider, self.model, self.use_chart
                )
            except Exception as e:  # noqa: BLE001 —— LLM/网络失败视为本轮失败，重试下一轮
                logger.warning("页面 %s 生成失败，重试：%s", slide_type, e)
                continue
            data = self.checker.check(text)
            if data is not None:
                await inject_images(data)  # 为 kind=image 的 items 填充图片 URL
                return data
        logger.warning("页面 %s 重试耗尽，跳过", slide_type)
        return None  # 重试耗尽，跳过该页（不中断整体流程）
