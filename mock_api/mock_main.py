"""模拟 API —— 无 LLM Key 时的前端联调（参考复现计划第 10 节）

提供假的模板 / 大纲 / 内容，让前端在尚未配置模型 Key 时也能跑通 UI 链路。
启动：python mock_main.py （默认 6801）
前端代理改指向本服务即可联调。
"""
import json
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

PORT = int(os.getenv("MOCK_API_PORT", "6801"))

app = FastAPI(title="AiPPT 模拟 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/templates")
async def templates():
    return {
        "templates": [
            {"name": "科技蓝紫", "id": "template_1", "cover": ""},
            {"name": "商务蓝", "id": "template_2", "cover": ""},
            {"name": "极简深色", "id": "template_3", "cover": ""},
        ]
    }


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


@app.post("/tools/aippt")
async def aippt(payload: dict):
    slides = [
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

    async def gen():
        for s in slides:
            yield f"data: {json.dumps(s, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=PORT)
