"""统一 LLM 客户端：真实调用（litellm）+ 离线脚本化（FakeLLM），并统一统计 token。

真实模式读取 backend/.env：
  - 大纲/文案默认用 MODEL_PROVIDER + LLM_MODEL（与后端其它服务一致）
  - 记录每次调用的 prompt/completion token，供熔断的 token 预算与成本核算使用
离线模式（FakeLLM）：不联网、确定性输出，用于演示桥段、CI 冒烟与 50 任务评估的可复现跑法。
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------- provider 映射
PROVIDER_PREFIX = {
    "google": "gemini/",
    "openai": "openai/",
    "claude": "anthropic/",
    "deepseek": "deepseek/",
    "ali": "openai/",
    "silicon": "openai/",
    "modelscope": "openai/",
    "doubao": "openai/",
    "glm": "openai/",
    "vllm": "openai/",
    "ollama": "ollama/",
}
PROVIDER_BASE = {
    "ali": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "silicon": "https://api.siliconflow.cn/v1",
    "modelscope": "https://api-inference.modelscope.cn/v1",
    "doubao": "https://ark.cn-beijing.volces.com/api/v3",
    "glm": "https://open.bigmodel.cn/api/paas/v4",
}
PROVIDER_KEY_ENV = {
    "google": "GOOGLE_API_KEY",
    "openai": "OPENAI_API_KEY",
    "claude": "CLAUDE_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "ali": "ALI_API_KEY",
    "silicon": "SILICON_API_KEY",
    "modelscope": "MODELSCOPE_API_KEY",
    "doubao": "DOUBAO_API_KEY",
    "glm": "GLM_API_KEY",
}


def model_name(provider: str, model: str) -> str:
    if "/" in model:
        return model
    return f"{PROVIDER_PREFIX.get(provider, '')}{model}"


def litellm_kwargs(provider: str) -> dict:
    kwargs: dict = {}
    base = PROVIDER_BASE.get(provider)
    if base:
        kwargs["api_base"] = base
    key_env = PROVIDER_KEY_ENV.get(provider)
    key = os.getenv(key_env or "", "")
    if key:
        kwargs["api_key"] = key
    return kwargs


# ---------------------------------------------------------------- 成本核算
# 默认单价（元 / 千 token），可用环境变量覆盖；用于「平均成本 元/份」指标
PRICE_INPUT_PER_1K = float(os.getenv("PRICE_INPUT_PER_1K", "0.001"))
PRICE_OUTPUT_PER_1K = float(os.getenv("PRICE_OUTPUT_PER_1K", "0.002"))


def cost_yuan(prompt_tokens: int, completion_tokens: int) -> float:
    return round(
        prompt_tokens / 1000 * PRICE_INPUT_PER_1K + completion_tokens / 1000 * PRICE_OUTPUT_PER_1K,
        6,
    )


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    calls: int = 0
    by_agent: dict[str, int] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    @property
    def cost(self) -> float:
        return cost_yuan(self.prompt_tokens, self.completion_tokens)

    def add(self, prompt: int, completion: int, agent: str = "") -> None:
        self.prompt_tokens += prompt
        self.completion_tokens += completion
        self.calls += 1
        if agent:
            self.by_agent[agent] = self.by_agent.get(agent, 0) + prompt + completion

    def as_dict(self) -> dict:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "calls": self.calls,
            "cost_yuan": self.cost,
            "by_agent": self.by_agent,
        }


class LLMClient:
    """真实 LLM 客户端（litellm）。"""

    def __init__(self, provider: str | None = None, model: str | None = None):
        self.provider = provider or os.getenv("MODEL_PROVIDER", "deepseek")
        self.model = model or os.getenv("LLM_MODEL", "deepseek-chat")

    async def chat(
        self,
        messages: list[dict],
        *,
        agent: str = "",
        usage: Usage | None = None,
        json_mode: bool = False,
        temperature: float = 0.4,
        max_tokens: int | None = None,
    ) -> str:
        import litellm  # 延迟导入，离线/未安装时也能用 FakeLLM

        kwargs: dict[str, Any] = {
            "model": model_name(self.provider, self.model),
            "messages": messages,
            "temperature": temperature,
            **litellm_kwargs(self.provider),
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        if max_tokens:
            kwargs["max_tokens"] = max_tokens
        resp = await litellm.acompletion(**kwargs)
        text = (resp.choices[0].message.content or "").strip()
        if usage is not None:
            u = getattr(resp, "usage", None)
            p = int(getattr(u, "prompt_tokens", 0) or 0)
            c = int(getattr(u, "completion_tokens", 0) or 0)
            if p == 0 and c == 0:  # 兜底估算，保证预算/成本仍有数
                p = sum(len(str(m.get("content", ""))) for m in messages) // 2
                c = len(text) // 2
            usage.add(p, c, agent)
        return text


class FakeLLM:
    """离线脚本化 LLM：确定性输出，用于演示/评估的可复现跑法。

    行为：
      - 规划（Planner）调用：按 script 列表依次返回决策；script 用尽后返回 finish
      - 其它调用（写大纲/文案）：返回结构化占位文本，token 用量按字符数估算
    """

    def __init__(self, script: list[dict] | None = None, provider: str = "fake", model: str = "fake"):
        self.script = list(script or [])
        self.provider = provider
        self.model = model
        self.plan_calls = 0

    async def chat(
        self,
        messages: list[dict],
        *,
        agent: str = "",
        usage: Usage | None = None,
        json_mode: bool = False,
        temperature: float = 0.4,
        max_tokens: int | None = None,
    ) -> str:
        prompt_chars = sum(len(str(m.get("content", ""))) for m in messages)
        if agent == "planner":
            idx = self.plan_calls
            self.plan_calls += 1
            decision = self.script[idx] if idx < len(self.script) else {"tool": "finish", "args": {}}
            text = json.dumps(decision, ensure_ascii=False)
        elif agent == "outline":
            topic = _extract_topic(messages)
            text = _fake_outline(topic)
        elif agent == "copy":
            text = (
                "本页围绕主题给出要点：背景与现状、关键挑战、解决思路、落地步骤、"
                "预期收益与风险控制，并给出可执行的行动建议。"
            )
        else:
            text = "OK"
        if usage is not None:
            usage.add(prompt_chars // 2, len(text) // 2, agent)
        return text


def _extract_topic(messages: list[dict]) -> str:
    for m in reversed(messages):
        content = str(m.get("content", ""))
        mt = re.search(r"主题[:：]\s*(.+)", content)
        if mt:
            return mt.group(1).strip().splitlines()[0][:60]
    return "AI 大模型行业趋势报告"


def _fake_outline(topic: str) -> str:
    parts = [
        f"# {topic}",
        "",
        "## 一、行业背景与现状",
        "- 市场规模持续增长",
        "- 政策与资本双重驱动",
        "",
        "## 二、核心技术与能力",
        "- 多模态与长上下文",
        "- 推理成本持续下降",
        "",
        "## 三、典型应用场景",
        "- 办公与内容创作",
        "- 教育与医疗",
        "",
        "## 四、竞争格局与挑战",
        "- 头部厂商集中度提升",
        "- 数据与合规风险",
        "",
        "## 五、趋势与行动建议",
        "- Agent 工作流成为主流",
        "- 优先落地高价值场景",
    ]
    return "\n".join(parts)
