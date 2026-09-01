"""大纲生成 Agent 服务 —— :10001

TODO: 当前为 FastAPI 骨架，仅提供 /healthz。
真实实现需替换为 A2A Starlette 应用（参考复现计划第 6 节）：
  - AgentCard(capabilities=AgentCapabilities(streaming=OUTLINE_STREAMING))
  - RunConfig(streaming_mode=SSE, max_llm_calls=500)
  - A2AStarletteApplication + Runner
"""
import os

from fastapi import FastAPI

PORT = int(os.getenv("OUTLINE_API_PORT", "10001"))

app = FastAPI(title="AiPPT 大纲生成 Agent")


@app.get("/healthz")
async def healthz():
    return {"ok": True, "service": "simpleOutline"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=PORT)
