"""文档处理流水线：文件/URL → Markdown → 分块。

只负责文本侧的处理，向量化与入库由 main.py 编排（保持职责单一）。
"""
import os

from utils.file_handler import download_url, save_upload
from utils.logger import get_logger

from .chunkers import get_chunker
from .markitdown_converter import convert_to_markdown
from .models import ParsedDocument

logger = get_logger("personaldb.document_processor")


class DocumentProcessor:
    """文件类型映射、文本提取、分块策略选择。"""

    def __init__(self, chunk_strategy: str = "fast", max_chars: int = 1200, overlap: int = 200):
        self.chunk_strategy = chunk_strategy
        self.max_chars = max_chars
        self.overlap = overlap

    def process_bytes(self, content: bytes, file_name: str, url: str = "") -> ParsedDocument:
        path = save_upload(content, file_name)
        return self._process(path, file_name, url=url)

    def process_url(self, url: str) -> ParsedDocument:
        path = download_url(url)
        file_name = os.path.basename(url.split("?")[0]) or "download"
        return self._process(path, file_name, url=url)

    def _process(self, path: str, file_name: str, url: str = "") -> ParsedDocument:
        file_type = os.path.splitext(file_name)[1].lstrip(".").lower()
        markdown = convert_to_markdown(path)
        chunker = get_chunker(self.chunk_strategy, self.max_chars, self.overlap)
        chunks = chunker.split(markdown)
        logger.info("解析 %s → %d 块（策略=%s）", file_name, len(chunks), self.chunk_strategy)
        return ParsedDocument(
            markdown=markdown,
            chunks=chunks,
            file_name=file_name,
            file_type=file_type,
            url=url,
        )
