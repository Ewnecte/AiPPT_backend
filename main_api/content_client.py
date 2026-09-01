"""内容客户端 —— 调用 slide_agent 服务。

当前用 HTTP 直连 slide_agent /generate（SSE），
后续可替换为 A2A 客户端（参考复现计划 8.3）。
"""
import os

import httpx

CONTENT_API = os.getenv("CONTENT_API", "http://127.0.0.1:10011")


class A2AContentClientWrapper:
    def __init__(self, base_url: str = CONTENT_API):
        self.base_url = base_url.rstrip("/")

    async def generate(self, markdown: str, model: str):
        """SSE 流式返回逐页 JSON（异步生成器，逐行 yield data 行）。"""
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/generate",
                json={"content": markdown, "model": model},
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    yield line
