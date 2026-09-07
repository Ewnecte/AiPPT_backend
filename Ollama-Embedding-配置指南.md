# Ollama Embedding 配置指南（RAG 向量化）

> 适用范围：AiPPT 后端（`backend/`）。文档针对 Windows 编写，macOS / Linux 命令已一并给出。
> 目的：让组员无需 DeepSeek / 阿里等外部 embedding Key，用**本地免费的 Ollama** 把「上传文档 → 分块 → 向量化 → ChromaDB → 生成时检索」这条 RAG 链路跑起来。

---

## 1. 为什么需要 Ollama？

RAG 的「向量化」环节需要一个 **embedding 模型**，而：

- **DeepSeek 官方 API 没有 embedding 模型**（只有对话类：`deepseek-v4-flash` / `deepseek-v4-pro` / `vision-exp`），实测 `GET /models` 也只返回这三个。
- 本项目向量化模块 `backend/personaldb/embedding_utils.py` 是多 Provider 设计，支持 `aliyun / doubao / vllm / xinference / ollama`。
- 本项目默认配置已切到 **ollama + bge-m3**（免费、本地运行、中文效果好、1024 维）。

```
上传文档 → MarkItDown 解析 → 分块 → ollama(bge-m3) 向量化 → ChromaDB 存储(user_{userId})
PPT 逐页生成时 → 按页面标题语义检索 top3 → 拼进 prompt → 大模型生成
```

---

## 2. 安装 Ollama

### 2.1 Windows（推荐 winget，或官网安装包）

```powershell
# 方式一：winget（已在本仓库验证，v0.33.3）
winget install -e --id Ollama.Ollama --accept-source-agreements --accept-package-agreements --disable-interactivity

# 方式二：官网下载安装
#   https://ollama.com/download  （OllamaSetup.exe，双击安装即可）
```

安装完成后，Ollama 一般会自动启动并在托盘常驻（服务监听 `127.0.0.1:11434`）。
如果没起来，手动启动：

```powershell
ollama serve          # 前台运行；或打开“Ollama”应用（会自动 serve）
```

### 2.2 macOS

```bash
brew install ollama
brew services start ollama   # 或前台 ollama serve
```

### 2.3 Linux

```bash
curl -fsSL https://ollama.com/install.sh | sh
# systemd 服务默认自动启动；手动：ollama serve
```

### 2.4 验证服务与安装位置

```powershell
# 查看已安装模型（应为空或已有模型）
curl http://127.0.0.1:11434/api/tags

# Windows 安装目录参考
$env:LOCALAPPDATA\Programs\Ollama\ollama.exe
```

---

## 3. 拉取 embedding 模型（必须）

RAG 用的模型推荐 **bge-m3**（多语言、中文效果好，1024 维，体积约 1.2GB，CPU 即可推理）：

```powershell
ollama pull bge-m3
```

如追求更小体积可用 `nomic-embed-text`（约 274MB，768 维，英文场景为主）：

```powershell
ollama pull nomic-embed-text
```

> 注意：这里拉的是 **embedding** 模型，用来做向量化，**不是**生成大纲/PPT 的大模型。
> 对话/生成模型仍走 DeepSeek 等（见 `backend/.env` 的 `MODEL_PROVIDER` / `PPT_WRITER_MODEL` 等）。

拉取完成检查：

```powershell
curl http://127.0.0.1:11434/api/tags
# 应能看到 bge-m3:latest

# 直接调 OpenAI 兼容接口做个冒烟测试，应返回 1024 维向量
curl http://127.0.0.1:11434/v1/embeddings `
  -H "Content-Type: application/json" `
  -d '{\"model\":\"bge-m3\",\"input\":[\"你好，测试向量\"]}'
```

---

## 4. 修改 backend/.env（关键）

打开 `backend/.env`，把 embedding 相关项设置如下：

```ini
# ---- 向量化（RAG embedding）----
EMBEDDING_PROVIDER=ollama
EMBEDDING_MODEL=bge-m3
EMBEDDING_API_BASE=
# 本地 Ollama 服务地址（OpenAI 兼容 /v1）
OLLAMA_API_URL=http://127.0.0.1:11434/v1
```

要点：

- `EMBEDDING_API_BASE` **留空**即可：代码会按 provider 解析，`ollama` 自动取 `OLLAMA_API_URL`。
- 若想换回云端（阿里等），改成 `EMBEDDING_PROVIDER=aliyun`、`EMBEDDING_MODEL=text-embedding-v2` 并配置 `ALI_API_KEY`，**不要同时提交 API Key 到 git**。
- 代码位置：`backend/personaldb/embedding_utils.py`（`EmbeddingModel._resolve_base()` / `_resolve_key()`）。

---

## 5. 重启 personaldb 使配置生效

`personaldb` 在**进程启动时**读取 `.env` 并创建 embedder，改配置后必须重启它：

```bash
cd backend
python start_backend.py        # 一键重启全部（推荐）
```

或单独重启：

```bash
# 先停掉占用 9100 的旧进程，再启动
cd backend/personaldb && python main.py
```

> ⚠️ 常见坑：**端口 9100 被占用**
> 报错形如 `[error] 端口 9100 已被占用（personaldb）` 时，说明已有一个 personaldb 实例在跑
> （可能来自另一个终端或之前的手动启动）。请先停掉它再启动，避免两个实例抢端口。
> 排查：`netstat -ano | findstr :9100` → 按 PID 结束对应 python 进程，
> 或直接重启终端里原本跑后端的那个窗口。

---

## 6. 验证 RAG 全链路（组员自查用）

启动后端后，用一条 curl 即可验证「上传 → 入库（分块+向量化）→ 检索」：

```powershell
# 1) 准备一个测试文档（内容随意，建议含一段独特的话便于检索验证）
# 2) 上传入库（应返回 chunks > 0，说明向量化成功；若返回 500/401 请检查第 3/4 步）
curl -s -F "file=@D:\test\rag_demo.txt" -F "userId=user_demo" -F "fileId=file_demo001" http://127.0.0.1:9100/upload/

# 3) 语义检索（query 用文档里的一句话，应能召回对应片段）
curl -s -X POST http://127.0.0.1:9100/search `
  -H "Content-Type: application/json" `
  -d '{"userId":"user_demo","query":"文档里的某个关键词","topk":3}'

# 4) 清理测试文件
curl -s -X DELETE http://127.0.0.1:9100/file/user_demo/file_demo001
```

前端联动验证（RAG 真正生效的入口）：

1. 首页「大纲生成」选 **📄 上传文档** → 得到 `fileId`；
2. 走完大纲编辑 → 模板选择；
3. 模板页「信息来源」选 **上传资料**；
4. 「生成演示文稿」→ PPT 生成页会走 `/tools/aippt_by_id` → 每页按标题检索知识库 top3 注入后生成。

---

## 7. 常见问题（FAQ）

| 现象 | 原因 / 解决 |
| --- | --- |
| `ollama` 命令不存在 | 未安装或未加入 PATH；Windows 重新打开终端，或用安装目录完整路径调用 |
| 11434 连不上 | Ollama 没在运行：`ollama serve` 或打开 Ollama 应用 |
| 上传返回 chunks=0 | 文档没解析出文本（空文件/扫描件），与 embedding 无关，属正常 |
| 上传返回 500 / embedding 报错 | `EMBEDDING_PROVIDER/MODEL` 不对，或模型未 `ollama pull`；改完 `.env` 记得重启 personaldb |
| 首次向量化很慢 | 模型首次加载到内存需要几秒，之后有缓存会变快 |
| 内存/CPU 要求 | bge-m3 约 1.2GB 模型，普通 CPU 笔记本即可推理，无需 GPU |
| 想换 embedding 供应商 | 支持 aliyun/doubao/vllm/xinference/ollama，见 `embedding_utils.py`；换云端需自行配 Key（勿提交 git） |

---

## 8. 参考链接

- Ollama 官网下载：<https://ollama.com/download>
- Ollama 模型库（bge-m3）：<https://ollama.com/library/bge-m3>
- Ollama API（OpenAI 兼容）：<http://127.0.0.1:11434/v1>（本地）
- 知识库代码：`backend/personaldb/`（main.py / embedding_utils.py / core/chunkers）
- 检索注入代码：`backend/slide_agent/slide_agent/agent.py`（`_generate_one`）、`sub_agents/ppt_writer/tools.py`（`knowledge_base_search`）

---

## 附：当前仓库里的实际生效配置（2026 已设置）

```
EMBEDDING_PROVIDER=ollama
EMBEDDING_MODEL=bge-m3
EMBEDDING_API_BASE=
OLLAMA_API_URL=http://127.0.0.1:11434/v1
```

组员新机器只需完成 **第 2、3、5 节**（安装 → pull bge-m3 → 重启后端）即可开始联调，无需申请任何 embedding API Key。
