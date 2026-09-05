"""ParagraphChunker：按空行分段，保留自然段落边界。"""
import re

from ..models import Chunk
from .base import BaseChunker


class ParagraphChunker(BaseChunker):
    """按空行分段；超长段落再按固定窗口截断。"""

    def split(self, text: str) -> list[Chunk]:
        text = text.strip()
        if not text:
            return []
        sections = [s.strip() for s in re.split(r"\n\s*\n", text) if s.strip()]
        pieces: list[str] = []
        for sec in sections:
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
