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
    """Pexels 图片搜索；无 Key 或失败时降级为内置图片池。"""
    api_key = os.getenv("PEXELS_API_KEY", "")
    if not api_key:
        return _fallback_images(count)
    try:
        resp = httpx.get(
            "https://api.pexels.com/v1/search",
            params={"query": query, "per_page": count},
            headers={"Authorization": api_key},
            timeout=30,
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
        return _fallback_images(count)


def _fallback_images(count: int) -> list[dict]:
    """内置图片池占位（可替换为本地图片路径，走 main_api /proxy 代理）。"""
    return [{"url": "", "width": 0, "height": 0, "author": "内置图片池"} for _ in range(count)]


async def document_search(keyword: str, top_n: int = 3) -> list[dict]:
    """微信文章搜索（占位，可复用 simpleOutline/tools.py 的实现）。"""
    raise NotImplementedError("TODO: 复用 simpleOutline 的微信搜索实现")
