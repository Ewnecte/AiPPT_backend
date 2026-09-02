"""按 (user_id, file_id) 持久化文件完整 Markdown。

ChromaDB 只存分块与元数据，无法还原完整原文；这里单独落盘一份，
供「按文件 id 生成 PPT」（main_api /tools/aippt_by_id）取回源文档 Markdown。
"""
import json
import os


class DocStore:
    """轻量 JSON 侧车存储，key = (user_id, file_id)。"""

    def __init__(self, base_dir: str = "./docs"):
        self.base_dir = base_dir
        os.makedirs(base_dir, exist_ok=True)

    @staticmethod
    def _safe(part: str) -> str:
        return part.replace(os.sep, "_").replace("..", "_")

    def _path(self, user_id: str, file_id: str) -> str:
        return os.path.join(self.base_dir, f"{self._safe(user_id)}_{self._safe(file_id)}.json")

    def save(
        self,
        user_id: str,
        file_id: str,
        markdown: str,
        file_name: str,
        file_type: str,
        url: str = "",
    ) -> None:
        with open(self._path(user_id, file_id), "w", encoding="utf-8") as f:
            json.dump(
                {
                    "file_id": file_id,
                    "file_name": file_name,
                    "file_type": file_type,
                    "url": url,
                    "markdown_content": markdown,
                },
                f,
                ensure_ascii=False,
            )

    def get(self, user_id: str, file_id: str) -> dict | None:
        path = self._path(user_id, file_id)
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as f:
            return json.load(f)
