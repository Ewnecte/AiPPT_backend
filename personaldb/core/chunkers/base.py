"""分块器基类。"""
from abc import ABC, abstractmethod

from ..models import Chunk


class BaseChunker(ABC):
    """所有分块器的基类。"""

    def __init__(self, max_chars: int = 1200, overlap: int = 200):
        self.max_chars = max_chars
        self.overlap = overlap

    @abstractmethod
    def split(self, text: str) -> list[Chunk]:
        """将文本切分为若干 Chunk。"""
        raise NotImplementedError

    def _build(self, pieces: list[str]) -> list[Chunk]:
        """由字符串片段构造带索引的 Chunk 列表。"""
        return [
            Chunk(text=piece.strip(), index=i)
            for i, piece in enumerate(pieces)
            if piece.strip()
        ]
