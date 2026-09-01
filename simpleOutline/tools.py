"""DocumentSearch 工具 —— 供大纲 Agent 调用，搜索微信文章正文。

同步实现，便于注册为 ADK 工具；异步上下文里可用 asyncio.to_thread 调用。
"""
from weixin_search import get_article_content, sogou_weixin_search


def document_search(keyword: str, top_n: int = 3) -> list[dict]:
    """搜索微信文章，返回 [{title, publish_time, real_url, content}]。"""
    articles = sogou_weixin_search(keyword, top_n)
    results = []
    for a in articles:
        content = ""
        try:
            content = get_article_content(a["real_url"])
        except Exception:  # noqa: BLE001 —— 正文抓取失败不影响其他文章
            pass
        results.append(
            {
                "title": a["title"],
                "publish_time": a.get("publish_time", ""),
                "real_url": a["real_url"],
                "content": content,
            }
        )
    return results
