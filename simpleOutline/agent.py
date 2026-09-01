"""OutlineAgent —— 大纲生成智能体。

提供两层能力：
  1. stream_outline()：直接走 LiteLLM 流式生成（可测试、可作 fallback）
  2. build_adk_agent()：用 google.adk 构造 LlmAgent（供 A2A 服务使用）

参考复现计划 6.1：LlmAgent + tools=[DocumentSearch]，动态 Prompt 切换。
"""
import asyncio

import litellm

from create_model import litellm_kwargs, model_name
from prompt import (
    OUTLINE_INSTRUCTION_NO_SEARCH,
    OUTLINE_INSTRUCTION_WITH_SEARCH,
    USER_INPUT_NUMBER,
)
from tools import document_search


def _build_prompt(content: str, language: str) -> str:
    """按输入长度选择带/不带搜索的指令，并拼接参考材料。"""
    with_search = len(content) <= USER_INPUT_NUMBER
    instruction = OUTLINE_INSTRUCTION_WITH_SEARCH if with_search else OUTLINE_INSTRUCTION_NO_SEARCH

    extra = ""
    if with_search:
        try:
            articles = document_search(content, top_n=3)
            if articles:
                material = "\n".join(
                    f"《{a['title']}》\n{a['content'][:500]}" for a in articles if a.get("content")
                )
                if material:
                    extra = f"\n\n参考材料：\n{material}"
        except Exception:  # noqa: BLE001 —— 搜索失败不影响大纲生成
            extra = ""

    return f"{instruction}\n\n语言：{language}\n主题：{content}{extra}"


async def stream_outline(content: str, language: str, provider: str, model: str):
    """异步生成器，逐段 yield 大纲文本（流式）。"""
    prompt = _build_prompt(content, language)
    resp = await litellm.acompletion(
        model=model_name(provider, model),
        messages=[{"role": "user", "content": prompt}],
        stream=True,
        **litellm_kwargs(provider),
    )
    async for chunk in resp:
        delta = chunk.choices[0].delta.content or ""
        if delta:
            yield delta


async def generate_outline(content: str, language: str, provider: str, model: str) -> str:
    """生成完整大纲（非流式拼接），便于测试。"""
    parts = []
    async for delta in stream_outline(content, language, provider, model):
        parts.append(delta)
    return "".join(parts)


def build_adk_agent(provider: str, model: str):
    """用 google.adk 构造 OutlineAgent（LlmAgent）。"""
    from google.adk.agents.llm_agent import LlmAgent  # noqa: PLC0415

    return LlmAgent(
        name="outline_agent",
        model=model_name(provider, model),
        instruction=OUTLINE_INSTRUCTION_WITH_SEARCH,
        tools=[document_search],
    )
