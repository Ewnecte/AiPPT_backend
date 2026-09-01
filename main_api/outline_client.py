"""大纲客户端 —— 调用 simpleOutline 服务。

当前用 HTTP 直连 simpleOutline /generate（流式），
后续可替换为 A2A 客户端（参考复现计划 8.3）。
"""
import os

import httpx

OUTLINE_API = os.getenv("OUTLINE_API", "http://127.0.0.1:10001")


class A2AOutlineClientWrapper:
    def __init__(self, base_url: str = OUTLINE_API):
        self.base_url = base_url.rstrip("/")

    async def generate(self, content: str, language: str, model: str):
        """流式返回 Markdown 大纲（异步生成器，逐段 yield）。"""
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/generate",
                json={"content": content, "language": language, "model": model},
            ) as resp:
                resp.raise_for_status()
                async for chunk in resp.aiter_text():
                    yield chunk
