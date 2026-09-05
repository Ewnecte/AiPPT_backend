"""HybridChunker：先按标题分段，段内超长再按段落细分，兼顾语义与长度。"""
import re

from ..models import Chunk
from .base import BaseChunker


class HybridChunker(BaseChunker):
    """先按 Markdown 标题切分；段内超长时再按空行细分，最后窗口截断。"""

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
            pieces.extend(self._split_section(sec))
        return self._build(pieces)

    def _split_section(self, text: str) -> list[str]:
        if len(text) <= self.max_chars:
            return [text]
        # 超长：先按空行细分，再把小段合并回不超过 max_chars 的块
        paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        out: list[str] = []
        buf = ""
        for p in paras:
            candidate = f"{buf}\n\n{p}" if buf else p
            if len(candidate) <= self.max_chars:
                buf = candidate
            else:
                if buf:
                    out.append(buf)
                if len(p) <= self.max_chars:
                    buf = p
                else:
                    # 单段仍超长，窗口截断
                    out.extend(self._split_long(p))
                    buf = ""
        if buf:
            out.append(buf)
        return out

    def _split_long(self, text: str) -> list[str]:
        step = max(self.max_chars - self.overlap, 1)
        out = []
        start = 0
        while start < len(text):
            out.append(text[start : start + self.max_chars])
            if start + self.max_chars >= len(text):
                break
            start += step
        return out
