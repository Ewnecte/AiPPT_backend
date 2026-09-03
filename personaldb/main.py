"""知识库服务 —— FastAPI + ChromaDB :9100

接口：
  POST /search            语义检索 Top-K（userId/query/topk）
  POST /upload/           上传文件/URL → 解析 → 分块 → 向量化 → 入库
  POST /vectorize/text    纯文本向量化
  GET  /files/{user_id}   列出用户已入库文件
  GET  /healthz           健康检查

依赖顺序：本服务是 slide_agent / main_api 的底层依赖，应最先启动。
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# 统一加载 backend/.env（对齐复现计划 8.3），须在读取任何 env 之前执行
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core.doc_store import DocStore
from core.document_processor import DocumentProcessor
from core.file_cache_manager import FileCacheManager
from embedding_utils import ChromaStore, EmbeddingModel
from utils.logger import get_logger
from utils.validators import validate_upload

logger = get_logger("personaldb")

PORT = int(os.getenv("PERSONALDB_PORT", "9100"))

app = FastAPI(title="AiPPT 知识库服务")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局单例（启动时初始化一次）
embedder = EmbeddingModel(
    os.getenv("EMBEDDING_PROVIDER", "aliyun"),
    os.getenv("EMBEDDING_MODEL", "text-embedding-v2"),
    os.getenv("ALI_API_KEY", ""),
)
store = ChromaStore(os.getenv("CHROMA_DIR", "./chroma_db"))
cache = FileCacheManager()
doc_store = DocStore(os.getenv("DOCS_DIR", "./docs"))
processor = DocumentProcessor(
    os.getenv("CHUNK_STRATEGY", "fast"),
    int(os.getenv("CHUNK_MAX_CHARS", "1200")),
    int(os.getenv("CHUNK_OVERLAP", "200")),
)


@app.get("/healthz")
async def healthz():
    return {"ok": True, "service": "personaldb"}


@app.post("/search")
async def search(payload: dict):
    user_id = str(payload.get("userId", ""))
    query = payload.get("query", "")
    top_k = int(payload.get("topk", 3))
    if not user_id or not query:
        return JSONResponse({"error": "userId/query 为必填项"}, status_code=400)

    vec = (await embedder.embed([query]))[0]
    results = store.search(user_id, vec, top_k)
    return {"results": results}


@app.post("/vectorize/text")
async def vectorize_text(payload: dict):
    texts = payload.get("texts", [])
    if not texts:
        return JSONResponse({"error": "texts 不能为空"}, status_code=400)
    return {"embeddings": await embedder.embed(texts)}


@app.post("/upload/")
async def upload(
    userId: str = Form(...),
    fileId: str = Form(...),
    file: UploadFile = File(None),
    url: str = Form(None),
):
    try:
        validate_upload(userId, fileId, file is not None, bool(url))
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    content: bytes | None = None
    if file is not None:
        content = await file.read()
        file_name = file.filename or "upload"
        cached = cache.get(content)
        if cached:
            # 缓存命中也要落一份按 (user_id, file_id) 的 Markdown，供按文件生成
            doc_store.save(
                userId,
                fileId,
                cached.get("markdown_content", ""),
                cached.get("file_name", file_name),
                cached.get("file_type", ""),
                cached.get("url", ""),
            )
            return cached
        parsed = processor.process_bytes(content, file_name)
    else:
        parsed = processor.process_url(url)

    result = await _store(userId, fileId, parsed)

    if content is not None:
        cache.set(content, result)
    return result


@app.get("/files/{user_id}")
async def files(user_id: str):
    return {"files": store.list_files(user_id)}


@app.get("/file/{user_id}/{file_id}")
async def get_file_markdown(user_id: str, file_id: str):
    """按 (user_id, file_id) 返回已入库文件的完整 Markdown（供按文件生成 PPT）。"""
    doc = doc_store.get(user_id, file_id)
    if doc is None:
        return JSONResponse({"error": "file not found"}, status_code=404)
    return doc


async def _store(user_id: str, file_id: str, parsed) -> dict:
    """分块 → 向量化 → 写入 ChromaDB，并落盘完整 Markdown。"""
    # 无论是否产生分块，都按 (user_id, file_id) 持久化源文档 Markdown
    doc_store.save(
        user_id,
        file_id,
        parsed.markdown,
        parsed.file_name,
        parsed.file_type,
        parsed.url,
    )

    chunks = parsed.chunks
    if not chunks:
        return {
            "file_id": file_id,
            "file_name": parsed.file_name,
            "file_type": parsed.file_type,
            "chunks": 0,
            "markdown_content": parsed.markdown,
        }

    ids = [f"{file_id}_{c.index}" for c in chunks]
    embeddings = await embedder.embed([c.text for c in chunks])
    metadatas = [
        {
            "file_id": file_id,
            "user_id": user_id,
            "file_name": parsed.file_name,
            "file_type": parsed.file_type,
            "folder_id": "",
            "url": parsed.url,
        }
        for _ in chunks
    ]
    store.add(user_id, ids, embeddings, [c.text for c in chunks], metadatas)
    logger.info("文件 %s 入库完成：%d 块", parsed.file_name, len(chunks))

    return {
        "file_id": file_id,
        "file_name": parsed.file_name,
        "file_type": parsed.file_type,
        "chunks": len(chunks),
        "markdown_content": parsed.markdown,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=PORT)
