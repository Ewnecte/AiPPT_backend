"""页面类型 Prompt + prompt_mapper（参考复现计划 7.2）。"""

_SLIDE_FORMAT = {
    "cover": '{"type": "cover", "data": {"title": "标题", "text": "副标题"}}',
    "contents": '{"type": "contents", "data": {"items": ["章节1", "章节2"]}}',
    "transition": '{"type": "transition", "data": {"title": "章节标题", "text": "过渡语"}}',
    "content": '{"type": "content", "data": {"title": "页面标题", "items": [{"title": "要点标题", "text": "要点正文"}]}}',
    "end": '{"type": "end", "data": {}}',
}

_DEFAULT_FORMAT = _SLIDE_FORMAT["content"]


def prompt_mapper(slide_type: str) -> str:
    """按页面类型返回撰写 Prompt。"""
    fmt = _SLIDE_FORMAT.get(slide_type, _DEFAULT_FORMAT)
    return (
        "你是专业的 PPT 内容撰写助手。请根据给定页面类型与主题，扩写该页内容。\n"
        "严格要求：\n"
        "1. 只输出一个 JSON 对象，不要代码块围栏、不要任何解释或前后缀\n"
        "2. 每项正文 60~120 字，内容详实、有条理\n"
        f"3. 页面类型：{slide_type}\n"
        f"4. JSON 结构：{fmt}\n"
    )
