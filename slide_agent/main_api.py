"""内容生成 Agent 服务 —— :10011

TODO: 当前为 FastAPI 骨架，仅提供 /healthz。
真实实现需替换为 A2A 应用，show_agent=["ControllerAgent"]（参考复现计划第 7 节）。
"""
import os

from fastapi import FastAPI

PORT = int(os.getenv("CONTENT_API_PORT", "10011"))

app = FastAPI(title="AiPPT 内容生成 Agent")


@app.get("/healthz")
async def healthz():
    return {"ok": True, "service": "slide_agent"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=PORT)
