"""LiteLLM 模型工厂（与 simpleOutline 同构，服务独立）。"""
import os

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
    "local": "",
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
