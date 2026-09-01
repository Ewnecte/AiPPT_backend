"""LiteLLM 模型工厂 —— 统一封装多家供应商（参考复现计划 6.1/7.1）。"""
import os

# provider → LiteLLM 前缀（OpenAI 兼容供应商统一走 openai/ 前缀 + 自定义 base_url）
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

# OpenAI 兼容供应商的 base_url
PROVIDER_BASE = {
    "ali": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "silicon": "https://api.siliconflow.cn/v1",
    "modelscope": "https://api-inference.modelscope.cn/v1",
    "doubao": "https://ark.cn-beijing.volces.com/api/v3",
    "glm": "https://open.bigmodel.cn/api/paas/v4",
}

# provider → API Key 对应的环境变量名
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
    """把 provider + model 拼成 LiteLLM 可识别的模型名。"""
    if "/" in model:
        return model
    return f"{PROVIDER_PREFIX.get(provider, '')}{model}"


def litellm_kwargs(provider: str) -> dict:
    """按 provider 返回传给 litellm 的额外参数（base_url / api_key）。"""
    kwargs: dict = {}
    base = PROVIDER_BASE.get(provider)
    if base:
        kwargs["api_base"] = base
    key_env = PROVIDER_KEY_ENV.get(provider)
    key = os.getenv(key_env or "", "")
    if key:
        kwargs["api_key"] = key
    return kwargs
