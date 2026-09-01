"""主 API 服务（网关）—— FastAPI :6800

统一入口：参数校验、转发大纲/内容 Agent、SSE 流式封装、模板/文件/代理。
"""
import os
from pathlib import Path

import httpx
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse

from content_client import A2AContentClientWrapper
from outline_client import A2AOutlineClientWrapper

PORT = int(os.getenv("MAIN_API_PORT", "6800"))
PERSONAL_DB = os.getenv("PERSONAL_DB", "http://127.0.0.1:9100")

app = FastAPI(title="AiPPT 主 API 服务")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

outline_client = A2AOutlineClientWrapper()
content_client = A2AContentClientWrapper()

TEMPLATE_DIR = "./template"
TEMPLATE_NAMES = {
    "template_1": "科技蓝紫",
    "template_2": "商务蓝",
    "template_3": "活力橙",
    "template_4": "清新绿",
}


@app.get("/healthz")
async def healthz():
    return {"ok": True, "service": "main_api"}


@app.get("/templates")
async def templates():
    items = []
    for f in sorted(Path(TEMPLATE_DIR).glob("template_*.json")):
        tid = f.stem
        items.append(
            {
                "name": TEMPLATE_NAMES.get(tid, tid),
                "id": tid,
                "cover": f"/api/data/{tid}.svg",
            }
        )
    return {"data": items}


@app.get("/data/{filename}")
async def data(filename: str):
    file_path = os.path.join(TEMPLATE_DIR, os.path.basename(filename))
    if not os.path.exists(file_path):
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(file_path)


@app.post("/tools/aippt_outline")
async def aippt_outline(payload: dict):
    content = payload.get("content", "")
    if not content:
        return JSONResponse({"error": "content 不能为空"}, status_code=400)
    language = payload.get("language", "中文")
    model = payload.get("model", os.getenv("LLM_MODEL", "qwen-turbo-latest"))

    async def gen():
        async for chunk in outline_client.generate(content, language, model):
            yield chunk

    return StreamingResponse(gen(), media_type="text/plain")


@app.post("/tools/aippt_outline_from_file")
async def aippt_outline_from_file(
    file: UploadFile = File(...),
    userId: str = Form("1"),
    fileId: str = Form("outline_file"),
    language: str = Form("中文"),
):
    """上传文件 → personaldb 转 Markdown → 生成大纲。"""
    content = await file.read()
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{PERSONAL_DB}/upload/",
            files={"file": (file.filename, content)},
            data={"userId": userId, "fileId": fileId},
        )
        resp.raise_for_status()
        markdown = resp.json().get("markdown_content", "")

    model = os.getenv("LLM_MODEL", "qwen-turbo-latest")

    async def gen():
        async for chunk in outline_client.generate(markdown, language, model):
            yield chunk

    return StreamingResponse(gen(), media_type="text/plain")


@app.post("/tools/aippt")
async def aippt(payload: dict):
    markdown = payload.get("content", "")
    if not markdown:
        return JSONResponse({"error": "content 不能为空"}, status_code=400)
    model = payload.get("model", os.getenv("PPT_WRITER_MODEL", "qwen-turbo-latest"))
    metadata = {
        "generateFromUploadedFile": payload.get("generateFromUploadedFile", False),
        "generateFromWebSearch": payload.get("generateFromWebSearch", False),
        "userId": payload.get("userId", "1"),
    }

    async def gen():
        async for line in content_client.generate(markdown, model, metadata):
            if line.startswith("data:"):
                yield f"{line}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.post("/tools/aippt_by_id")
async def aippt_by_id(payload: dict):
    # TODO: 按文件 id 从 personaldb 取 Markdown → 再走逐页生成
    return JSONResponse({"error": "TODO: 实现按文件生成"}, status_code=501)


@app.get("/files/{user_id}")
async def files(user_id: str):
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{PERSONAL_DB}/files/{user_id}")
        resp.raise_for_status()
        return resp.json()


@app.get("/proxy")
async def proxy(url: str = ""):
    """透明代理外链图片，解决前端跨域加载。"""
    if not url:
        return JSONResponse({"error": "url 必填"}, status_code=400)
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        resp = await client.get(url)
    return Response(
        content=resp.content,
        media_type=resp.headers.get("content-type", "image/jpeg"),
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=PORT)
