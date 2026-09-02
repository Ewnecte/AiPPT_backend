"""大纲生成 Agent 服务 —— :10001

当前提供可直接运行的 FastAPI 版本：
  GET  /healthz            健康检查
  POST /generate           流式生成 Markdown 大纲（text/plain）

生产环境需升级为 A2A Starlette 服务（见文件末尾说明），
核心生成逻辑已抽到 agent.stream_outline()，可复用。
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# 统一加载 backend/.env（对齐复现计划 8.3），须在读取任何 env 之前执行
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from agent import stream_outline

PORT = int(os.getenv("OUTLINE_API_PORT", "10001"))

app = FastAPI(title="AiPPT 大纲生成 Agent")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
async def healthz():
    return {"ok": True, "service": "simpleOutline"}


@app.post("/generate")
async def generate(payload: dict):
    content = payload.get("content", "")
    if not content:
        return JSONResponse({"error": "content 不能为空"}, status_code=400)

    language = payload.get("language", "中文")
    provider = os.getenv("MODEL_PROVIDER", "ali")
    model = payload.get("model", os.getenv("LLM_MODEL", "qwen-turbo-latest"))

    async def gen():
        async for delta in stream_outline(content, language, provider, model):
            yield delta

    return StreamingResponse(gen(), media_type="text/plain")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=PORT)


# ============================================================================
# A2A 升级说明（生产版）
# ============================================================================
# 参考复现计划 6.1，将上面 FastAPI 替换为 A2A Starlette 应用：
#
#   from a2a.server.apps import A2AStarletteApplication
#   from a2a.types import AgentCapabilities, AgentCard, AgentSkill
#   from a2a.utils.constants import MIME_TYPE_TEXT
#   from adk_agent_executor import ADKAgentExecutor
#   from agent import build_adk_agent
#
#   capabilities = AgentCapabilities(streaming=True)
#   skill = AgentSkill(id="outline", name="大纲生成", description="生成 Markdown 大纲",
#                      tags=["outline"], examples=[])
#   card = AgentCard(name="AiPPT 大纲 Agent", description="...", url="http://127.0.0.1:10001",
#                    version="1.0.0", capabilities=capabilities, skills=[skill])
#   server = A2AStarletteApplication(build_adk_agent(...), card, ...)
#   uvicorn.run(server.build(), host="127.0.0.1", port=PORT)
#
# 注意：a2a-sdk 0.2.x 与 google-adk 1.5.0 的接口需与安装版本对齐。
