"""Embedding 与向量存储封装。

参考复现计划 5.2：
  - EmbeddingModel 多 Provider 抽象（aliyun/doubao/vllm/xinference/ollama）
  - ChromaStore 封装 ChromaDB（collection=user_{id}，cosine 空间）
"""
import os

import chromadb
import httpx


class EmbeddingModel:
    """多 Provider 向量化，统一 OpenAI 兼容 /embeddings 接口。"""

    PROVIDER_BASE_URL = {
        "aliyun": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "doubao": "https://ark.cn-beijing.volces.com/api/v3",
    }

    # provider → API Key 对应的环境变量名（本地模型可无 key）
    PROVIDER_KEY_ENV = {
        "aliyun": "ALI_API_KEY",
        "doubao": "DOUBAO_API_KEY",
        "vllm": "VLLM_API_KEY",
        "xinference": "XINFERENCE_API_KEY",
        "ollama": "OLLAMA_API_KEY",
    }

    def __init__(self, provider: str, model: str, api_key: str = ""):
        self.provider = provider
        self.model = model
        self.api_key = api_key or self._resolve_key()
        self.api_base = self._resolve_base()
        self._cache: dict[str, list[float]] = {}

    def _resolve_base(self) -> str:
        env_base = os.getenv("EMBEDDING_API_BASE", "")
        if env_base:
            return env_base
        if self.provider == "vllm":
            return os.getenv("VLLM_API_URL", "http://127.0.0.1:8000/v1")
        if self.provider == "xinference":
            return os.getenv("XINFERENCE_API_URL", "http://127.0.0.1:9997/v1")
        if self.provider == "ollama":
            return os.getenv("OLLAMA_API_URL", "http://127.0.0.1:11434/v1")
        return self.PROVIDER_BASE_URL.get(self.provider, self.PROVIDER_BASE_URL["aliyun"])

    def _resolve_key(self) -> str:
        """未显式传入 api_key 时，按 provider 从环境变量解析。"""
        env_name = self.PROVIDER_KEY_ENV.get(self.provider, "")
        if env_name:
            return os.getenv(env_name, "")
        return os.getenv("EMBEDDING_API_KEY", "")

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """批量向量化，返回与输入等长的向量列表（异步，避免阻塞事件循环）。

        命中内存缓存直接复用，仅对未命中的文本发起批量请求。
        """
        if not texts:
            return []

        result: list[list[float] | None] = [None] * len(texts)
        miss_idx: list[int] = []
        for i, text in enumerate(texts):
            if text in self._cache:
                result[i] = self._cache[text]
            else:
                miss_idx.append(i)

        if miss_idx:
            miss_texts = [texts[i] for i in miss_idx]
            embeddings = await self._request_embeddings(miss_texts)
            for i, emb in zip(miss_idx, embeddings):
                self._cache[texts[i]] = emb
                result[i] = emb

        return [emb for emb in result if emb is not None]

    async def _request_embeddings(self, texts: list[str]) -> list[list[float]]:
        """调用 OpenAI 兼容 /embeddings 接口，返回与输入等长的向量列表。"""
        payload = {"model": self.model, "input": texts}
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self.api_base.rstrip('/')}/embeddings",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json().get("data", [])
        # 按 index 排序，保证顺序与输入一致
        ordered = sorted(data, key=lambda x: x.get("index", 0))
        return [item["embedding"] for item in ordered]


class ChromaStore:
    """ChromaDB 存储 / 检索封装。"""

    def __init__(self, persist_dir: str = "./chroma_db"):
        self.client = chromadb.PersistentClient(path=persist_dir)

    def get_collection(self, user_id: str):
        return self.client.get_or_create_collection(
            name=f"user_{user_id}",
            metadata={"hnsw:space": "cosine"},
        )

    def add(
        self,
        user_id: str,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict],
    ) -> None:
        self.get_collection(user_id).add(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )

    def search(self, user_id: str, query_embedding: list[float], top_k: int = 3) -> list[dict]:
        col = self.get_collection(user_id)
        res = col.query(query_embeddings=[query_embedding], n_results=top_k)
        docs = (res.get("documents") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]
        results = []
        for i, doc in enumerate(docs):
            meta = metas[i] if i < len(metas) and metas[i] else {}
            results.append(
                {
                    "text": doc,
                    "metadata": meta,
                    "distance": dists[i] if i < len(dists) else None,
                }
            )
        return results

    def list_files(self, user_id: str) -> list[dict]:
        """聚合该用户已入库的文件（按 file_id 去重）。"""
        col = self.get_collection(user_id)
        metadatas = col.get().get("metadatas") or []
        files: dict[str, dict] = {}
        for m in metadatas:
            if not m:
                continue
            fid = m.get("file_id")
            if fid and fid not in files:
                files[fid] = {
                    "file_id": fid,
                    "file_name": m.get("file_name", ""),
                    "file_type": m.get("file_type", ""),
                    "folder_id": m.get("folder_id", ""),
                    "url": m.get("url", ""),
                }
        return list(files.values())

    def delete(self, user_id: str, file_id: str) -> int:
        """删除该用户下某文件的所有分块，返回删除条数。

        先按 file_id 查出 id 再按 id 删（跨 chromadb 版本更稳定）。
        """
        col = self.get_collection(user_id)
        existing = col.get(where={"file_id": file_id})
        ids = existing.get("ids") or []
        if ids:
            col.delete(ids=ids)
        return len(ids)
