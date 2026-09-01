"""MarkItDown 转换：各类文件 → Markdown。"""
import os

from markitdown import MarkItDown


def convert_to_markdown(file_path: str) -> str:
    """将文件转换为 Markdown 文本。

    支持 PDF/Word/PPT/Excel/图片/音频等（由 MarkItDown 能力决定）。
    若 MarkItDown 不可用，回退为纯文本读取（.txt/.md）。
    """
    try:
        md = MarkItDown()
        result = md.convert(file_path)
        return result.text_content or ""
    except Exception as e:  # noqa: BLE001 —— 回退纯文本
        ext = os.path.splitext(file_path)[1].lower()
        if ext in {".txt", ".md", ".markdown", ".json", ".csv"}:
            with open(file_path, encoding="utf-8", errors="ignore") as f:
                return f.read()
        raise RuntimeError(f"文件解析失败：{e}") from e
