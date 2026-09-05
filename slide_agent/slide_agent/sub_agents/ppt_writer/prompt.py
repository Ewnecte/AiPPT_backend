"""页面类型 Prompt + prompt_mapper（参考复现计划 7.2）。"""

_SLIDE_FORMAT = {
    "cover": '{"type": "cover", "data": {"title": "标题", "text": "副标题"}}',
    "contents": '{"type": "contents", "data": {"items": ["章节1", "章节2"]}}',
    "transition": '{"type": "transition", "data": {"title": "章节标题", "text": "过渡语"}}',
    "content": '{"type": "content", "data": {"title": "页面标题", "items": [{"title": "要点标题", "text": "要点正文"}]}}',
    "end": '{"type": "end", "data": {}}',
}

# content 页 items 的三种形态（对齐 frontend/src/types/AIPPT.ts 的 ContentItem）
_CONTENT_ITEMS_HINT = (
    "items 的每个元素可选三种形态：\n"
    '  纯文本：{"title": "要点标题", "text": "要点正文（60~120字）"}\n'
    '  图表：{"title": "图表标题", "text": "一句话说明", "kind": "chart", '
    '"chartType": "bar", "labels": ["A", "B", "C", "D"], '
    '"series": [{"name": "系列", "data": [12, 23, 34, 45]}]}\n'
    '  图片：{"title": "图片标题", "text": "说明", "kind": "image", "url": ""}'
)


def prompt_mapper(slide_type: str, use_chart: bool = False) -> str:
    """按页面类型返回撰写 Prompt。"""
    fmt = _SLIDE_FORMAT.get(slide_type, _SLIDE_FORMAT["content"])
    lines = [
        "你是专业的 PPT 内容撰写助手。请根据给定页面类型与主题，扩写该页内容。",
        "严格要求：",
        "1. 只输出一个 JSON 对象，不要代码块围栏、不要任何解释或前后缀",
        "2. 每项正文 60~120 字，内容详实、有条理",
        f"3. 页面类型：{slide_type}",
        f"4. JSON 结构：{fmt}",
    ]
    if slide_type == "content":
        lines.append(f"5. items 元素形态：{_CONTENT_ITEMS_HINT}")
        if use_chart:
            lines.append(
                "6. 当主题涉及趋势/对比/占比等数据时，至少使用 1 个 kind=chart 的图表项"
                "（chartType 从 line/bar/pie/column/ring/area/radar 中选，labels 4~8 个，"
                "series 1~2 个）；图片项 url 留空字符串即可。"
            )
    return "\n".join(lines)
