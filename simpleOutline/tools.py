"""DocumentSearch 工具 —— 供大纲 Agent 调用（同步），四通道联网检索。

与 slide_agent/sub_agents/ppt_writer/tools.py 的 document_search 保持镜像
（本文件为同步版，便于直接调用 / 注册为 ADK 工具）：
  1. 搜狗微信 —— 公众号文章，优先尝试抓全文；
  2. Bing 通用网页 —— 补足非微信来源；正文抓取失败时退回搜索摘要；
  3. GitHub 仓库 README —— 常规搜索颗粒无收、且查询明显指向代码/开源库
     时兜底，取仓库一手资料；
  4. 官网/文档站 —— 前三通道都空、且查询明显在找单一产品/框架的官方
     资料时，猜官方域名抓 sitemap 文档。

正文统一走 web_fetcher 清洗（去导航/广告，只留正文）。候选正文抓取用
ThreadPoolExecutor 并发，通道异常自动降级（宁缺毋滥），不影响生成。
"""
from concurrent.futures import ThreadPoolExecutor

from web_fetcher import fetch_text
from weixin_search import bing_search, sogou_weixin_search

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
    """并发抓取一批候选，返回与输入对齐的 got/None 列表。"""
    if not cands:
        return []
    with ThreadPoolExecutor(max_workers=len(cands)) as ex:
        return list(ex.map(_grab_full, cands))


def document_search(keyword: str, top_n: int = 3) -> list[dict]:
    """联网搜索，返回 [{title, publish_time, real_url, content}]。"""
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
            import github_search  # noqa: PLC0415 —— 模块缺失/依赖异常则降级
        except Exception:  # noqa: BLE001
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

    # 通道 4：官网/文档站 —— 前三通道颗粒无收、且查询明显在找单一产品/
    # 框架官方资料时才猜官网抓 sitemap 文档（避免对泛主题乱猜域名）
    if not results:
        try:
            import doc_site  # noqa: PLC0415
        except Exception:  # noqa: BLE001
            doc_site = None
        if doc_site is not None and doc_site.looks_like_doc_query(keyword):
            try:
                for d in doc_site.doc_site_search(keyword, top_n):
                    results.append(
                        {
                            "title": d.get("title", ""),
                            "publish_time": "",
                            "real_url": d.get("real_url", ""),
                            "content": d.get("content", ""),
                        }
                    )
            except Exception:  # noqa: BLE001 —— 文档站网络/抓取失败静默降级
                pass

    return results[:top_n]
