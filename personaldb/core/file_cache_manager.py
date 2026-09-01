"""文件解析结果缓存：按内容 MD5 缓存，避免重复处理同一文件。"""
import hashlib
import json
import os


class FileCacheManager:
    def __init__(self, cache_dir: str = "./cache"):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

    @staticmethod
    def _md5(content: bytes) -> str:
        return hashlib.md5(content).hexdigest()

    def get(self, content: bytes) -> dict | None:
        path = os.path.join(self.cache_dir, f"{self._md5(content)}.json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        return None

    def set(self, content: bytes, value: dict) -> None:
        path = os.path.join(self.cache_dir, f"{self._md5(content)}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False)
