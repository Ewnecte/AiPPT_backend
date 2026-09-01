"""内容生成 Agent 服务 —— :10011

接口：
  GET  /healthz   健康检查
  POST /generate  SSE 流式返回逐页 Slide JSON，末尾 data: [DONE]
"""
import asyncio
import json
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from slide_agent.agent import WritingSystemAgent

PORT = int(os.getenv("CONTENT_API_PORT", "10011"))

app = FastAPI(title="AiPPT 内容生成 Agent")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
async def healthz():
    return {"ok": True, "service": "slide_agent"}


@app.post("/generate")
async def generate(payload: dict):
    markdown = payload.get("content", "")
    if not markdown:
        return JSONResponse({"error": "content 不能为空"}, status_code=400)

    provider = os.getenv("PPT_WRITER_PROVIDER", "ali")
    model = payload.get("model", os.getenv("PPT_WRITER_MODEL", "qwen-turbo-latest"))
    use_kb = bool(payload.get("generateFromUploadedFile", False))
    user_id = str(payload.get("userId", "1"))
    agent = WritingSystemAgent(provider, model, use_kb=use_kb, user_id=user_id)

    queue: asyncio.Queue = asyncio.Queue()

    async def produce() -> None:
        async def on_slide(data: dict) -> None:
            await queue.put(data)

        await agent.generate(markdown, on_slide)
        await queue.put(None)  # 结束信号

    task = asyncio.create_task(produce())

    async def gen():
        while True:
            item = await queue.get()
            if item is None:
                break
            yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
        await task

    return StreamingResponse(gen(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=PORT)
