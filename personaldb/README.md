# personaldb 知识库服务（:9100）

文件上传/URL → 解析（MarkItDown）→ 分块（FastChunker）→ 向量化（多 Provider）→ 存入 ChromaDB → 语义检索。

## 接口

| 方法 | 路径 | 说明 |
| ---- | ---- | ---- |
| GET  | `/healthz` | 健康检查 |
| POST | `/search` | 语义检索，body `{userId, query, topk}` |
| POST | `/upload/` | multipart：`userId`/`fileId` + `file` 或 `url`（互斥） |
| POST | `/vectorize/text` | 纯文本向量化，body `{texts: [...]}` |
| GET  | `/files/{user_id}` | 列出用户已入库文件 |

## 配置（env_template / 根 .env）

```bash
EMBEDDING_PROVIDER=aliyun     # aliyun/doubao/vllm/xinference/ollama
EMBEDDING_MODEL=text-embedding-v2
ALI_API_KEY=sk-xxx
CHROMA_DIR=./chroma_db
CHUNK_STRATEGY=fast           # fast/recursive
```

## 启动与验证

```bash
cd backend/personaldb
pip install -r ../requirements.txt
python main.py                 # 127.0.0.1:9100

# 上传文本文件并检索
curl -F "userId=1" -F "fileId=100" -F "file=@test.md" http://127.0.0.1:9100/upload/
curl -X POST http://127.0.0.1:9100/search -H "Content-Type: application/json" \
     -d '{"userId":"1","query":"测试查询","topk":3}'
curl http://127.0.0.1:9100/files/1
```

## 关键实现点

- **多 Provider 向量化**：统一走 OpenAI 兼容 `/embeddings`，`EMBEDDING_API_BASE` 可覆盖 base_url。
- **用户隔离**：`collection = user_{user_id}`，`hnsw:space=cosine`。
- **元数据**：`file_id/user_id/file_name/folder_id/file_type/url`，chunk id = `{file_id}_{index}`。
- **缓存**：按文件内容 MD5 缓存解析结果，重传同一文件直接返回。
- **互斥校验**：`file` 与 `url` 二选一。
