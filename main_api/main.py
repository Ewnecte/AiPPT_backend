"""主 API 服务（网关）—— FastAPI :6800

统一入口：参数校验、转发大纲/内容 Agent、SSE 流式封装、模板/文件/代理。
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# 统一加载 backend/.env（对齐复现计划 8.3），须在 import 各 client 之前执行
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

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
    """按已上传文件的 id 生成 PPT：取回源文档 Markdown → 逐页生成（走知识库检索）。"""
    file_id = str(payload.get("fileId", ""))
    user_id = str(payload.get("userId", "1"))
    if not file_id:
        return JSONResponse({"error": "fileId 不能为空"}, status_code=400)

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{PERSONAL_DB}/file/{user_id}/{file_id}")
        if resp.status_code == 404:
            return JSONResponse({"error": "文件不存在或未入库"}, status_code=404)
        resp.raise_for_status()
        markdown = resp.json().get("markdown_content", "")

    if not markdown:
        return JSONResponse({"error": "文件内容为空"}, status_code=400)

    model = payload.get("model", os.getenv("PPT_WRITER_MODEL", "qwen-turbo-latest"))
    metadata = {
        "generateFromUploadedFile": True,  # 触发 slide_agent 知识库检索增强
        "generateFromWebSearch": False,
        "userId": user_id,
    }

    async def gen():
        async for line in content_client.generate(markdown, model, metadata):
            if line.startswith("data:"):
                yield f"{line}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/files/{user_id}")
async def files(user_id: str):
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{PERSONAL_DB}/files/{user_id}")
        resp.raise_for_status()
        return resp.json()


@app.post("/files/upload")
async def kb_upload(
    userId: str = Form("1"),
    fileId: str = Form(...),
    file: UploadFile = File(None),
    url: str = Form(None),
):
    """知识库文件/URL 入库（透传 personaldb POST /upload/）。file 与 url 必须二选一。"""
    if (file is None) == (not url):
        return JSONResponse({"error": "file 与 url 必须且只能提供其中一个"}, status_code=400)
    data = {"userId": userId, "fileId": fileId}
    if url:
        data["url"] = url
    content = await file.read() if file is not None else None
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{PERSONAL_DB}/upload/",
            files=(
                {"file": (file.filename or "upload", content)} if content is not None else None
            ),
            data=data,
        )
    if resp.status_code >= 400:
        try:
            return JSONResponse(resp.json(), status_code=resp.status_code)
        except Exception:
            return Response(content=resp.content, status_code=resp.status_code, media_type="application/json")
    return resp.json()


@app.get("/file/{user_id}/{file_id}")
async def kb_file_detail(user_id: str, file_id: str):
    """读取已入库文件（含完整 Markdown 内容），供前端预览/内容展示。"""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{PERSONAL_DB}/file/{user_id}/{file_id}")
        if resp.status_code == 404:
            return JSONResponse({"error": "文件不存在或未入库"}, status_code=404)
        resp.raise_for_status()
        return resp.json()


@app.delete("/file/{user_id}/{file_id}")
async def kb_file_delete(user_id: str, file_id: str):
    """删除已入库文件（Chroma 分块 + 完整原文），透传 personaldb。"""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.delete(f"{PERSONAL_DB}/file/{user_id}/{file_id}")
        if resp.status_code == 404:
            return JSONResponse({"error": "文件不存在或未入库"}, status_code=404)
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


# ============================================================================
# 多 Agent PPT 生成（B + E）：工具白名单 + Schema 校验 + 熔断 + token 看板
# ============================================================================
import asyncio  # noqa: E402
import json  # noqa: E402
import sys  # noqa: E402

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

try:  # 依赖缺失（如未装 litellm）时不影响网关其它接口
    from multi_agent.llm import FakeLLM, LLMClient  # noqa: E402
    from multi_agent.orchestrator import Limits, MultiAgentOrchestrator  # noqa: E402
    from multi_agent.tool_registry import SANDBOX_DIR, WHITELIST, tool_catalog_text  # noqa: E402

    AGENT_OK = True
    AGENT_IMPORT_ERROR = ""
except Exception as _e:  # noqa: BLE001
    AGENT_OK = False
    AGENT_IMPORT_ERROR = f"{type(_e).__name__}: {_e}"


@app.get("/tools/agent_info")
async def agent_info():
    """多 Agent 能力说明：白名单工具 + Schema（供前端/演示展示）。"""
    if not AGENT_OK:
        return JSONResponse({"ok": False, "error": AGENT_IMPORT_ERROR}, status_code=503)
    return {
        "ok": True,
        "tools": sorted(WHITELIST),
        "catalog": tool_catalog_text(),
        "sandbox_dir": str(SANDBOX_DIR),
        "limits": Limits().as_dict(),
    }


@app.get("/tools/agent_files")
async def agent_files(prefix: str = ""):
    """列出沙箱内已落盘产物（演示时展示“写入文件”结果）。"""
    if not AGENT_OK:
        return JSONResponse({"ok": False, "error": AGENT_IMPORT_ERROR}, status_code=503)
    base = SANDBOX_DIR
    files = []
    if base.exists():
        for p in sorted(base.rglob("*")):
            if p.is_file():
                rel = str(p.relative_to(base)).replace("\\", "/")
                if prefix and not rel.startswith(prefix.strip("/")):
                    continue
                files.append({"path": rel, "bytes": p.stat().st_size, "mtime": int(p.stat().st_mtime)})
    return {"ok": True, "sandbox_dir": str(base), "files": files[-200:]}


@app.post("/tools/agent_run")
async def agent_run(payload: dict):
    """SSE 流式运行多 Agent 任务：step / plan / loop_detected / breaker / artifact / done。

    body: {task, mode: auto|real|fake, maxSteps?, maxTokens?, timeoutS?, sandboxPrefix?, script?}
    """
    if not AGENT_OK:
        return JSONResponse({"ok": False, "error": AGENT_IMPORT_ERROR}, status_code=503)
    task = str(payload.get("task") or "").strip()
    if not task:
        return JSONResponse({"error": "task 不能为空"}, status_code=400)

    limits = Limits(
        max_steps=int(payload.get("maxSteps") or 10),
        max_tokens=int(payload.get("maxTokens") or 40000),
        timeout_s=float(payload.get("timeoutS") or 180),
    )
    mode = str(payload.get("mode") or "auto")
    script = payload.get("script") if isinstance(payload.get("script"), list) else None
    sandbox_prefix = str(payload.get("sandboxPrefix") or "web")

    queue: asyncio.Queue = asyncio.Queue()

    async def on_event(ev: dict) -> None:
        await queue.put(ev)

    async def produce() -> None:
        try:
            llm = FakeLLM(script=script) if mode == "fake" else LLMClient()
            orch = MultiAgentOrchestrator(
                task, llm=llm, limits=limits, on_event=on_event, sandbox_prefix=sandbox_prefix
            )
            result = await orch.run()
            await queue.put({"type": "result", "data": result.as_dict()})
        except Exception as e:  # noqa: BLE001
            await queue.put({"type": "error", "message": f"{type(e).__name__}: {e}"})
        finally:
            await queue.put(None)

    task_obj = asyncio.create_task(produce())

    async def gen():
        while True:
            item = await queue.get()
            if item is None:
                break
            yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
        await task_obj

    return StreamingResponse(gen(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=PORT)
