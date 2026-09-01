"""Markdown 大纲 → Slide Schema 解析。

映射规则（参考复现计划 7.2）：
  #   → cover（标题）
  ##  → contents 项 + transition（章节页）
  ### → content（内容页）
  -   → content 页的 items
  末尾补 end
"""


def parse_markdown_to_slides(markdown: str) -> list[dict]:
    """把 Markdown 大纲解析为 Slide Schema 列表。"""
    lines = [l.rstrip() for l in markdown.splitlines() if l.strip()]
    title = ""
    contents: list[str] = []
    body: list[dict] = []
    current_content: dict | None = None

    def flush() -> None:
        nonlocal current_content
        if current_content is not None and current_content.get("items"):
            body.append({"type": "content", "data": current_content})
        current_content = None

    for line in lines:
        if line.startswith("# "):
            title = line[2:].strip()
        elif line.startswith("## "):
            flush()
            sec = line[3:].strip()
            contents.append(sec)
            body.append({"type": "transition", "data": {"title": sec}})
        elif line.startswith("### "):
            flush()
            current_content = {"title": line[4:].strip(), "items": []}
        elif line.startswith("- ") and current_content is not None:
            current_content["items"].append({"title": line[2:].strip(), "text": ""})
    flush()

    result: list[dict] = [{"type": "cover", "data": {"title": title or "未命名"}}]
    if contents:
        result.append({"type": "contents", "data": {"items": contents}})
    result.extend(body)
    result.append({"type": "end", "data": {}})
    return result
