"""内容 Agent 工具集：知识库检索 + Pexels 配图。"""
import os

import httpx

PERSONAL_DB = os.getenv("PERSONAL_DB", "http://127.0.0.1:9100")


async def knowledge_base_search(query: str, top_k: int = 3, user_id: str = "1") -> list[dict]:
    """调 personaldb 语义检索，返回 Top-K 结果（[{text, metadata, distance}]）。"""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{PERSONAL_DB}/search",
            json={"userId": user_id, "query": query, "topk": top_k},
        )
        resp.raise_for_status()
        return resp.json().get("results", [])


async def search_image(query: str, count: int = 1) -> list[dict]:
    """Pexels 图片搜索；无 Key 或失败时降级为 picsum 占位图。"""
    api_key = os.getenv("PEXELS_API_KEY", "")
    if not api_key:
        return _fallback_images(count, query)
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                "https://api.pexels.com/v1/search",
                params={"query": query, "per_page": count},
                headers={"Authorization": api_key},
            )
        resp.raise_for_status()
        photos = resp.json().get("photos", [])
        return [
            {
                "url": p["src"]["large"],
                "width": p["width"],
                "height": p["height"],
                "author": p.get("photographer", ""),
            }
            for p in photos
        ]
    except Exception:  # noqa: BLE001 —— 外部图片 API 失败降级
        return _fallback_images(count, query)


def _fallback_images(count: int, seed: str = "ppt") -> list[dict]:
    """无 Pexels Key 时降级为 picsum 占位图（真实图片、无需鉴权）。"""
    return [
        {
            "url": f"https://picsum.photos/seed/{seed}-{i}/800/600",
            "width": 800,
            "height": 600,
            "author": "picsum",
        }
        for i in range(count)
    ]


async def inject_images(data: dict) -> dict:
    """为 kind=image 的 items 填充图片 URL（Pexels / picsum 占位）。"""
    d = data.get("data")
    items = d.get("items") if isinstance(d, dict) else None
    if not isinstance(items, list):
        return data
    for it in items:
        if isinstance(it, dict) and it.get("kind") == "image" and not it.get("url"):
            query = it.get("title") or it.get("text") or "business"
            urls = await search_image(query, count=1)
            if urls:
                it["url"] = urls[0]["url"]
    return data


async def document_search(keyword: str, top_n: int = 3) -> list[dict]:
    """联网搜索，返回 [{title, publish_time, real_url, content}]。

    优先搜狗微信（抓公众号正文）；搜狗通道不稳定（空结果 / 正文抓不到）时
    自动降级为 Bing 网页搜索（title + 摘要，不抓正文）。
    """
    import asyncio

    from .weixin_search import bing_search, get_article_content, sogou_weixin_search

    def _run() -> list[dict]:
        try:
            results = []
            for a in sogou_weixin_search(keyword, top_n):
                content = ""
                try:
                    content = get_article_content(a["real_url"])
                except Exception:  # noqa: BLE001 —— 正文抓取失败不影响其他文章
                    pass
                if not content:
                    continue
                results.append(
                    {
                        "title": a["title"],
                        "publish_time": a.get("publish_time", ""),
                        "real_url": a["real_url"],
                        "content": content,
                    }
                )
            if results:
                return results
        except Exception:  # noqa: BLE001 —— 搜狗不可用则降级
            pass
        # 兜底：Bing 网页搜索（标题 + 搜索摘要）
        try:
            return bing_search(keyword, top_n)
        except Exception:  # noqa: BLE001
            return []

    # 网络抓取为同步阻塞实现，放到线程池避免阻塞事件循环
    return await asyncio.to_thread(_run)
