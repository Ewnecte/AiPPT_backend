"""分块器。"""
from .base import BaseChunker
from .fast import FastChunker
from .recursive import RecursiveChunker
from .paragraph import ParagraphChunker
from .hybrid import HybridChunker
from .semantic import SemanticChunker

__all__ = [
    "BaseChunker",
    "FastChunker",
    "RecursiveChunker",
    "ParagraphChunker",
    "HybridChunker",
    "SemanticChunker",
]

_STRATEGY_MAP = {
    "fast": FastChunker,
    "recursive": RecursiveChunker,
    "paragraph": ParagraphChunker,
    "hybrid": HybridChunker,
    "semantic": SemanticChunker,
}


def get_chunker(strategy: str, max_chars: int = 1200, overlap: int = 200) -> BaseChunker:
    """按策略名构造分块器；未知策略回落到 fast。"""
    cls = _STRATEGY_MAP.get(strategy, FastChunker)
    return cls(max_chars=max_chars, overlap=overlap)
