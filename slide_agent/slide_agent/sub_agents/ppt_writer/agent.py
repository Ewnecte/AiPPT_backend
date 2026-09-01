"""Writer / Checker / Controller 子 Agent。

参考复现计划 7.2（多智能体循环核心）：
  PPTWriterSubAgent (LlmAgent) → CheckerAgent (规则校验) → ControllerAgent (推进/重试)
"""
import litellm

from ...create_model import litellm_kwargs, model_name
from .prompt import prompt_mapper
from .utils import parse_slide


class PPTWriterSubAgent:
    """按页面类型 Prompt 生成/扩写 JSON（LlmAgent）。"""

    def __init__(self, tools: list | None = None):
        self.tools = tools or []  # KnowledgeBaseSearch / SearchImage 待接入

    async def write(self, slide_type: str, context: str, provider: str, model: str) -> str:
        prompt = prompt_mapper(slide_type) + f"\n主题/上下文：{context}"
        resp = await litellm.acompletion(
            model=model_name(provider, model),
            messages=[{"role": "user", "content": prompt}],
            stream=False,  # 非流式，避免 JSON 粘连（CONTENT_STREAMING=false）
            **litellm_kwargs(provider),
        )
        return resp.choices[0].message.content or ""


class CheckerAgent:
    """规则校验 JSON，不调用 LLM。"""

    @staticmethod
    def check(text: str) -> dict | None:
        return parse_slide(text)


class ControllerAgent:
    """推进/重试控制。"""

    def __init__(self, max_retries: int = 3, max_iterations: int = 200):
        self.max_retries = max_retries
        self.max_iterations = max_iterations
