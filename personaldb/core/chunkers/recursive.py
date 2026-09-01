"""RecursiveChunker：先按标题/段落切分，再对超长段落递归截断。"""
import re

from ..models import Chunk
from .base import BaseChunker


class RecursiveChunker(BaseChunker):
    """优先按 Markdown 标题 / 空行分段，保留语义边界。"""

    def split(self, text: str) -> list[Chunk]:
        text = text.strip()
        if not text:
            return []
        # 先按标题或空行分段
        sections = re.split(r"\n(?=#{1,6}\s)|(?:\r?\n){2,}", text)
        pieces: list[str] = []
        for sec in sections:
            sec = sec.strip()
            if not sec:
                continue
            pieces.extend(self._split_long(sec))
        return self._build(pieces)

    def _split_long(self, text: str) -> list[str]:
        if len(text) <= self.max_chars:
            return [text]
        step = max(self.max_chars - self.overlap, 1)
        out = []
        start = 0
        while start < len(text):
            out.append(text[start : start + self.max_chars])
            if start + self.max_chars >= len(text):
                break
            start += step
        return out
