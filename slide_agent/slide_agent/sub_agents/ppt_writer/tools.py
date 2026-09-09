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

    多通道并集，正文统一走 web_fetcher 清洗（去导航/广告，只留正文）：
      1. 搜狗微信 —— 公众号文章，优先尝试抓全文；
      2. Bing 通用网页 —— 补足非微信来源；正文抓取失败时退回搜索摘要；
      3. GitHub 仓库 README —— 仅当前两通道颗粒无收、且查询明显指向代码/
         开源库时兜底，直接取仓库一手资料（普通搜索对这种查询只出教程软文）。
    各候选的正文抓取为并发执行，通道异常自动降级（宁缺毋滥），
    不影响后续生成。
    """
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    from .web_fetcher import fetch_text
    from .weixin_search import bing_search, sogou_weixin_search

    # 反爬/验证页特征：命中说明抓到的是拦截页而不是正文，应丢弃走下一通道
    _BOT_PAGE_MARKERS = (
        "antispider", "请输入验证码", "访问过于频繁", "环境异常", "安全验证",
        "verify you are human", "unusual traffic", "人机验证",
    )

    def _looks_like_bot_page(url: str, content: str) -> bool:
        if "antispider" in url.lower():
            return True
        low = content.lower()
        return any(m in low for m in _BOT_PAGE_MARKERS)

    def _grab_full(a: dict) -> dict | None:
        """抓一篇候选正文；失败/抓到拦截页返回 None（外层决定降级）。"""
        url = a.get("real_url", "")
        if not url:
            return None
        try:
            content = fetch_text(url).strip()
        except Exception:  # noqa: BLE001 —— 网络/解析失败，交由外层降级
            return None
        if len(content) < 80 or _looks_like_bot_page(url, content):
            return None
        return {
            "title": a.get("title", ""),
            "publish_time": a.get("publish_time", ""),
            "real_url": url,
            "content": content,
        }

    def _fetch_batch(cands: list[dict]) -> list[dict]:
        """并发抓取一批候选，返回按原顺序排好的 {cand: got|None} 对齐结果。"""
        if not cands:
            return []
        with ThreadPoolExecutor(max_workers=len(cands)) as ex:
            return list(ex.map(_grab_full, cands))

    def _run() -> list[dict]:
        results: list[dict] = []

        # 通道 1：搜狗微信（对微信生态命中更准）
        wx: list[dict] = []
        try:
            wx = sogou_weixin_search(keyword, top_n)
        except Exception:  # noqa: BLE001 —— 搜狗不可用则跳过
            pass
        for got in _fetch_batch(wx):
            if got:
                results.append(got)

        # 通道 2：Bing 通用网页，补足剩余名额
        if len(results) < top_n:
            bing: list[dict] = []
            try:
                bing = bing_search(keyword, top_n)
            except Exception:  # noqa: BLE001 —— Bing 不可用则跳过
                pass
            for cand, got in zip(bing, _fetch_batch(bing)):
                if got:
                    results.append(got)
                elif cand.get("content", "").strip():  # 抓不到正文退回摘要
                    results.append(
                        {
                            "title": cand.get("title", ""),
                            "publish_time": "",
                            "real_url": cand.get("real_url", ""),
                            "content": cand["content"],
                        }
                    )
                if len(results) >= top_n:
                    break

        # 通道 3：GitHub 仓库 README —— 仅当常规搜索颗粒无收、且查询明显指向
        # 代码/开源库时补充一手资料（无谓命中会白白消耗 GitHub API 配额）
        if not results:
            try:
                from . import github_search
            except Exception:  # noqa: BLE001 —— 模块缺失/依赖异常直接跳过
                github_search = None
            if github_search is not None and github_search.looks_like_repo_query(keyword):
                try:
                    for g in github_search.repo_search(keyword, top_n):
                        results.append(
                            {
                                "title": g.get("title", ""),
                                "publish_time": "",
                                "real_url": g.get("real_url", ""),
                                "content": g.get("content", ""),
                            }
                        )
                except Exception:  # noqa: BLE001 —— GitHub 网络/API 失败静默降级
                    pass

        return results[:top_n]

    # 网络抓取为同步阻塞实现，放到线程池避免阻塞事件循环
    return await asyncio.to_thread(_run)
