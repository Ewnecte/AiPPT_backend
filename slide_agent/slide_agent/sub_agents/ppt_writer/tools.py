"""内容 Agent 工具集 —— TODO

参考复现计划第 7.1 节：
  - SearchImage        (Pexels 配图)
  - DocumentSearch     (微信文章搜索)
  - KnowledgeBaseSearch(personaldb 检索)
"""


async def search_image(query: str, count: int = 1):
    raise NotImplementedError("TODO: Pexels 图片搜索")


async def document_search(keyword: str, top_n: int = 3):
    raise NotImplementedError("TODO: 微信文章搜索")


async def knowledge_base_search(query: str, top_k: int = 3):
    raise NotImplementedError("TODO: personaldb 知识库检索")
