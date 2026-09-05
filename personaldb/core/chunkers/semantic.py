"""SemanticChunker：按 Markdown 标题分组，尽量保持语义单元完整。"""
import re

from ..models import Chunk
from .base import BaseChunker


class SemanticChunker(BaseChunker):
    """以「标题 + 其下属内容」作为语义单元，仅当一节超长时才截断。

    与 RecursiveChunker 的区别：Recursive 会在标题和空行两处都切，
    Semantic 只在标题处切，更倾向于把同属一节的多个段落保留在同一块内，
    适合结构清晰、以标题划分主题的文档。
    """

    def split(self, text: str) -> list[Chunk]:
        text = text.strip()
        if not text:
            return []
        sections = re.split(r"\n(?=#{1,6}\s)", text)
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
