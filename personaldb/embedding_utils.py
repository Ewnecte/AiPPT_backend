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

    def __init__(self, provider: str, model: str, api_key: str = ""):
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.api_base = self._resolve_base()

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

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """批量向量化，返回与输入等长的向量列表（异步，避免阻塞事件循环）。"""
        if not texts:
            return []
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
