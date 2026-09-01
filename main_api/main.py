"""主 API 服务（网关）—— FastAPI :6800

职责（见复现计划第 8 节）：
  - 统一入口、参数校验
  - 通过 A2A 客户端调用大纲/内容 Agent
  - SSE 流式封装
  - 模板列表 / 静态文件 / 图片代理 / 文件列表转发

骨架已提供 /healthz 与 /templates 占位、/tools/aippt 的 SSE 管道示例，
其余接口为 501 占位，按 TODO 逐步实现。
"""
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

PORT = int(os.getenv("MAIN_API_PORT", "6800"))

app = FastAPI(title="AiPPT 主 API 服务")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
async def healthz():
    return {"ok": True, "service": "main_api"}


@app.get("/templates")
async def templates():
    # TODO: 返回模板列表 [{name, id, cover}]，数据来自 main_api/template/
    return JSONResponse({"templates": []})


@app.post("/tools/aippt_outline")
async def aippt_outline(payload: dict):
    # TODO: 调用 outline_client 流式返回 Markdown 大纲（text/plain）
    # 输入：content / language / model / stream
    return JSONResponse({"error": "TODO: 实现大纲生成接口"}, status_code=501)


@app.post("/tools/aippt_outline_from_file")
async def aippt_outline_from_file(payload: dict):
    # TODO: 上传文件 → personaldb 转 Markdown → 生成大纲
    return JSONResponse({"error": "TODO: 实现文件大纲接口"}, status_code=501)


@app.post("/tools/aippt")
async def aippt(payload: dict):
    """SSE 流式返回逐页 JSON，末尾 data: [DONE]"""

    async def gen():
        # TODO: 调用 content_client 逐页转发 slide_agent 输出
        yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.post("/tools/aippt_by_id")
async def aippt_by_id(payload: dict):
    # TODO: 按文件 id 生成（走知识库检索）
    return JSONResponse({"error": "TODO: 实现按文件生成接口"}, status_code=501)


@app.get("/files/{user_id}")
async def files(user_id: str):
    # TODO: 转发 personaldb /files/{user_id}
    return JSONResponse({"files": []})


@app.get("/proxy")
async def proxy(url: str = ""):
    # TODO: 透明代理外链图片，解决前端跨域加载
    return JSONResponse({"error": "TODO: 实现图片代理"}, status_code=501)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=PORT)
