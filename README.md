# 后端（你负责）

四个服务 + 一个模拟 API，骨架已就绪，按《复现实施计划》阶段二~五逐服务实现。

## 服务清单

| 服务 | 目录 | 端口 | 框架 | 状态 |
| ---- | ---- | ---- | ---- | ---- |
| 知识库 personaldb | `personaldb/` | 9100 | FastAPI + ChromaDB | 骨架 |
| 大纲 simpleOutline | `simpleOutline/` | 10001 | ADK + A2A（LlmAgent） | 骨架 |
| 内容 slide_agent | `slide_agent/` | 10011 | ADK + A2A（SequentialAgent/LoopAgent） | 骨架 |
| 主 API main_api | `main_api/` | 6800 | FastAPI + SSE | 骨架 |
| 模拟 mock_api | `mock_api/` | 自定义 | FastAPI | 骨架 |

## 实现顺序（建议）

1. **personaldb**（阶段二）—— 先做，因为 slide_agent 依赖它
   - `POST /upload/`、`POST /search`、`GET /files/{user_id}`
   - MarkItDown 解析 → FastChunker 分块 → Embedding → ChromaDB
2. **simpleOutline**（阶段三）—— LlmAgent + DocumentSearch，流式输出 Markdown 大纲
3. **slide_agent**（阶段四）—— 核心：Writer/Checker/Controller 循环，逐页 JSON
4. **main_api**（阶段五）—— 网关：A2A 客户端封装 + SSE 流式 + 模板接口
5. **mock_api**（阶段七）—— 无 Key 联调前端

## 启动

```bash
cd backend
pip install -r requirements.txt

# 一键启动
python start_backend.py

# 或逐个（按依赖顺序）
cd personaldb   && python main.py        # 9100
cd simpleOutline && python main_api.py    # 10001
cd slide_agent   && python main_api.py    # 10011
cd main_api      && python main.py        # 6800
```

## 关键坑位（来自复现计划）

- `google-adk` / `a2a-sdk` 接口版本敏感，锁定 `google-adk==1.5.0`、`a2a-sdk==0.2.10`。
- 内容生成 `CONTENT_STREAMING=false`（LLM 非流式），避免 JSON 粘连。
- `PERSONAL_DB`（注意拼写，不是 `PERSONENAL_DB`）。
- 上传文件 `file` 与 `url` 互斥；`collection = user_{user_id}`，`hnsw:space=cosine`。
