"""配图检索底层实现：Pexels 优先，无 Key/失败时降级为 picsum 占位图。

返回统一结构：{url, source, author, title, query}
由 image_safety 负责审核与版权说明，本模块只负责“取图”。
"""
from __future__ import annotations

import os

import httpx


def _fallback(query: str, count: int) -> list[dict]:
    return [
        {
            "url": f"https://picsum.photos/seed/{abs(hash(query)) % 10_000}-{i}/1280/720",
            "source": "picsum",
            "author": "picsum.photos",
            "title": f"{query}（占位图）",
            "query": query,
        }
        for i in range(count)
    ]


async def search_images(query: str, count: int = 2) -> list[dict]:
    api_key = os.getenv("PEXELS_API_KEY", "")
    if not api_key:
        return _fallback(query, count)
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                "https://api.pexels.com/v1/search",
                params={"query": query, "per_page": count, "orientation": "landscape"},
                headers={"Authorization": api_key},
            )
            resp.raise_for_status()
            photos = resp.json().get("photos", [])
        out = []
        for p in photos[:count]:
            out.append(
                {
                    "url": p["src"].get("large2x") or p["src"].get("large") or p["src"].get("original", ""),
                    "source": "pexels",
                    "author": p.get("photographer", ""),
                    "title": p.get("alt") or f"{query}",
                    "query": query,
                }
            )
        return out or _fallback(query, count)
    except Exception:  # noqa: BLE001 —— 外部图库失败降级
        return _fallback(query, count)
