"""数据模型定义。"""
from dataclasses import dataclass, field
from enum import Enum


class ChunkStrategy(str, Enum):
    """分块策略（参考复现计划 5.1）。"""

    FAST = "fast"
    RECURSIVE = "recursive"
    # 以下策略留待后续扩展
    SEMANTIC = "semantic"
    PARAGRAPH = "paragraph"
    HYBRID = "hybrid"


@dataclass
class Chunk:
    """一个文本块。"""

    text: str
    index: int
    metadata: dict = field(default_factory=dict)


@dataclass
class ParsedDocument:
    """解析结果：原文 Markdown + 分块 + 元信息。"""

    markdown: str
    chunks: list[Chunk]
    file_name: str
    file_type: str
    url: str = ""
