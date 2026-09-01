"""DocumentSearch 工具 —— TODO

参考复现计划第 6.1 节：
  sogou_weixin_search(keyword) → 结果列表
  → get_real_url(链接) → get_article_content(真实URL)
  → 返回 [{title, publish_time, real_url, content}]，默认前 3 篇
"""


async def document_search(keyword: str, top_n: int = 3) -> list[dict]:
    """搜索微信文章正文，供大纲 Agent 扩充内容。"""
    raise NotImplementedError("TODO: 实现微信文章搜索工具")
