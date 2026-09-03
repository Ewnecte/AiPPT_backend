"""模拟 API —— 无 LLM Key 时的前端联调（参考复现计划第 10 节）

提供假的模板 / 大纲 / 内容，让前端在尚未配置模型 Key 时也能跑通 UI 链路。
启动：python mock_main.py （默认 6801）
前端代理改指向本服务即可联调。

接口与 main_api 保持一致（返回结构、路径、封面图均对齐）：
  GET  /healthz                     健康检查
  GET  /templates                   模板列表（{"data": [...]}）
  GET  /data/{filename}             模板封面 SVG
  POST /tools/aippt_outline         流式大纲（text/plain）
  POST /tools/aippt                 流式逐页 JSON（SSE，末尾 [DONE]）
  POST /tools/aippt_by_id           按文件 id 生成（SSE，模拟）
  GET  /files/{user_id}             文件列表（空）
  GET  /proxy                       外链图片代理
"""
import json
import os

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse

PORT = int(os.getenv("MOCK_API_PORT", "6801"))

app = FastAPI(title="AiPPT 模拟 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 与 main_api/template 的四套模板对齐（名称 / 配色 / id 一致）
TEMPLATES = [
    {"name": "科技蓝紫", "id": "template_1", "c1": "#667eea", "c2": "#764ba2"},
    {"name": "商务蓝", "id": "template_2", "c1": "#0ea5e9", "c2": "#6366f1"},
    {"name": "活力橙", "id": "template_3", "c1": "#f97316", "c2": "#ef4444"},
    {"name": "清新绿", "id": "template_4", "c1": "#10b981", "c2": "#14b8a6"},
]

_COVERS = {t["id"]: t for t in TEMPLATES}


def _svg_cover(tpl: dict) -> str:
    """生成与 main_api 封面风格一致的 SVG 缩略图。"""
    name, c1, c2 = tpl["name"], tpl["c1"], tpl["c2"]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="480" height="270" viewBox="0 0 480 270">
  <defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="{c1}"/><stop offset="1" stop-color="{c2}"/>
  </linearGradient></defs>
  <rect width="480" height="270" fill="url(#g)"/>
  <rect x="32" y="40" width="6" height="36" rx="3" fill="#fff" opacity="0.9"/>
  <text x="52" y="68" font-family="sans-serif" font-size="28" font-weight="bold" fill="#fff">{name}</text>
  <rect x="32" y="130" width="210" height="12" rx="6" fill="#fff" opacity="0.85"/>
  <rect x="32" y="152" width="140" height="12" rx="6" fill="#fff" opacity="0.55"/>
</svg>'''


@app.get("/healthz")
async def healthz():
    return {"ok": True, "service": "mock_api"}


@app.get("/templates")
async def templates():
    items = [
        {"name": t["name"], "id": t["id"], "cover": f"/api/data/{t['id']}.svg"}
        for t in TEMPLATES
    ]
    return {"data": items}


@app.get("/data/{filename}")
async def data(filename: str):
    tid = filename.rsplit(".", 1)[0]
    tpl = _COVERS.get(tid)
    if tpl is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    return Response(_svg_cover(tpl), media_type="image/svg+xml")


@app.post("/tools/aippt_outline")
async def outline(payload: dict):
    content = payload.get("content", "示例主题")
    md = (
        f"# {content}\n\n"
        "## 一、背景概述\n"
        "### 1.1 定义与分类\n- 要点一\n- 要点二\n\n"
        "## 二、核心分析\n"
        "### 2.1 现状\n- 要点一\n- 要点二\n\n"
        "## 三、结论\n"
        "### 3.1 建议\n- 要点一\n"
    )
    return StreamingResponse(iter([md]), media_type="text/plain")


def _mock_slides() -> list[dict]:
    return [
        {"type": "cover", "data": {"title": "示例标题", "text": "示例副标题"}},
        {"type": "contents", "data": {"items": ["一、背景概述", "二、核心分析", "三、结论"]}},
        {
            "type": "content",
            "data": {
                "title": "核心分析",
                "items": [
                    {"title": "要点一", "text": "这是模拟内容，用于前端联调。"},
                    {"title": "要点二", "text": "替换为真实 Agent 输出后即可。"},
                ],
            },
        },
        {"type": "end", "data": {}},
    ]


@app.post("/tools/aippt")
async def aippt(payload: dict):
    slides = _mock_slides()

    async def gen():
        for s in slides:
            yield f"data: {json.dumps(s, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.post("/tools/aippt_by_id")
async def aippt_by_id(payload: dict):
    slides = _mock_slides()

    async def gen():
        for s in slides:
            yield f"data: {json.dumps(s, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/files/{user_id}")
async def files(user_id: str):
    return {"files": []}


@app.get("/proxy")
async def proxy(url: str = ""):
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
