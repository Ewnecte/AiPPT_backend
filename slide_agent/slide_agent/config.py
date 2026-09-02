"""内容生成模型配置（对齐复现计划 7.3）。

从环境变量读取，缺省回落 ali / qwen-turbo-latest。
Writer 与 Checker 可配置不同模型；Checker 当前为规则校验（不调 LLM），
其配置预留，供后续接入 LLM 校对时使用。
"""
import os


def _build(provider_env: str, model_env: str) -> dict:
    return {
        "provider": os.getenv(provider_env, "ali"),
        "model": os.getenv(model_env, "qwen-turbo-latest"),
    }


PPT_WRITER_AGENT_CONFIG = _build("PPT_WRITER_PROVIDER", "PPT_WRITER_MODEL")
PPT_CHECKER_AGENT_CONFIG = _build("PPT_CHECKER_PROVIDER", "PPT_CHECKER_MODEL")
