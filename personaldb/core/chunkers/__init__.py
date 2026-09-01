"""分块器。"""
from .base import BaseChunker
from .fast import FastChunker
from .recursive import RecursiveChunker

__all__ = ["BaseChunker", "FastChunker", "RecursiveChunker"]


def get_chunker(strategy: str, max_chars: int = 1200, overlap: int = 200) -> BaseChunker:
    """按策略名构造分块器。"""
    if strategy == "recursive":
        return RecursiveChunker(max_chars=max_chars, overlap=overlap)
    return FastChunker(max_chars=max_chars, overlap=overlap)
