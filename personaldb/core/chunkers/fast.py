"""FastChunker：固定窗口 + 重叠的快速分块（默认策略）。"""
from ..models import Chunk
from .base import BaseChunker


class FastChunker(BaseChunker):
    """按 max_chars 切分，overlap 重叠，速度优先。"""

    def split(self, text: str) -> list[Chunk]:
        text = text.strip()
        if not text:
            return []
        if len(text) <= self.max_chars:
            return self._build([text])

        pieces: list[str] = []
        step = max(self.max_chars - self.overlap, 1)
        start = 0
        while start < len(text):
            end = min(start + self.max_chars, len(text))
            pieces.append(text[start:end])
            if end >= len(text):
                break
            start += step
        return self._build(pieces)
