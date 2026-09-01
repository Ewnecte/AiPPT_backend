"""知识库服务 —— FastAPI + ChromaDB :9100

接口（参考复现计划第 5 节）：
  POST /search           语义检索 Top-K
  POST /upload/          上传文件/URL → 解析 → 分块 → 向量化 → 入库
  GET  /files/{user_id}  列出用户已入库文件
"""
import os

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware

PORT = int(os.getenv("PERSONALDB_PORT", "9100"))

app = FastAPI(title="AiPPT 知识库服务")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
async def healthz():
    return {"ok": True, "service": "personaldb"}


@app.post("/search")
async def search(payload: dict):
    # TODO: Embedding + ChromaDB 语义检索，返回 Top-K（userId/query/topk）
    return {"results": []}


@app.post("/upload/")
async def upload(
    userId: str = Form(...),
    fileId: str = Form(...),
    file: UploadFile = File(None),
    url: str = Form(None),
):
    # TODO: file 与 url 互斥校验
    # → MarkItDown 解析转 Markdown → FastChunker 分块 → Embedding → 写入 ChromaDB
    return {"error": "TODO: 实现上传接口"}


@app.get("/files/{user_id}")
async def files(user_id: str):
    # TODO: 从 ChromaDB metadata 聚合该用户已入库文件
    return {"files": []}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=PORT)
