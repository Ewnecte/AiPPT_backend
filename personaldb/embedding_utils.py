"""EmbeddingModel + ChromaDB 封装 —— TODO

参考复现计划第 5.2 节：
  - EmbeddingModel：多 Provider（aliyun/doubao/vllm/xinference/ollama），
    统一返回 {"data":[{"embedding":[...]}]}
  - ChromaDB：collection = user_{user_id}，hnsw:space=cosine
  - cache_decorator：按 MD5 缓存文件解析结果
"""


class EmbeddingModel:
    """多 Provider 向量化抽象。"""

    def __init__(self, provider: str, model: str, api_key: str):
        self.provider = provider
        self.model = model
        self.api_key = api_key

    def embed(self, texts: list[str]) -> list[list[float]]:
        """批量向量化，返回向量列表。"""
        raise NotImplementedError("TODO: 实现多 Provider 向量化")


class ChromaStore:
    """ChromaDB 存储/检索封装。"""

    def __init__(self, collection: str):
        self.collection = collection
        # TODO: 初始化 chromadb.PersistentClient + get_or_create_collection

    def add(self, ids, embeddings, documents, metadatas):
        raise NotImplementedError("TODO: 写入向量")

    def search(self, query_embedding, top_k: int):
        raise NotImplementedError("TODO: 相似度检索")
