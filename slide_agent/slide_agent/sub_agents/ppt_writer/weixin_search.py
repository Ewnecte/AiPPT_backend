"""搜狗微信搜索：关键词 → 文章列表 → 真实 URL → 正文。

与 simpleOutline/weixin_search.py 保持一致（复现计划 7.1 要求 slide_agent 亦具备微信搜索）。
注意：搜狗页面结构与反爬策略可能变动，本实现为尽力而为（best-effort），
失败时向上抛异常由调用方降级处理。
"""
import base64
import re
import urllib.parse

import httpx
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}


def sogou_weixin_search(keyword: str, top_n: int = 3) -> list[dict]:
    """搜狗微信搜索，返回文章列表 [{title, link, real_url}]。"""
    resp = httpx.get(
        "https://weixin.sogou.com/weixin",
        params={"type": 2, "query": keyword},
        headers=HEADERS,
        follow_redirects=True,
        timeout=30,
    )
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "lxml")
    items: list[dict] = []
    for li in soup.select("ul.news-list li"):
        a = li.select_one("h3 a")
        if not a:
            continue
        title = a.get_text(strip=True)
        link = a.get("href", "")
        if not link:
            continue
        real_url = get_real_url(link)
        if real_url:
            items.append({"title": title, "link": link, "real_url": real_url})
        if len(items) >= top_n:
            break
    return items


def get_real_url(link: str) -> str:
    """解析搜狗加密跳转链接，得到 mp.weixin.qq.com 真实地址。"""
    m = re.search(r"url=([^&]+)", link)
    if m:
        try:
            decoded = urllib.parse.unquote(m.group(1))
            padding = "=" * (-len(decoded) % 4)
            real = base64.b64decode(decoded + padding).decode("utf-8", errors="ignore")
            if real.startswith("http"):
                return real
        except Exception:  # noqa: BLE001
            pass
    # 兜底：直接跟随跳转
    try:
        r = httpx.get(
            "https://weixin.sogou.com" + link if link.startswith("/") else link,
            headers=HEADERS,
            follow_redirects=True,
            timeout=30,
        )
        return str(r.url)
    except Exception:  # noqa: BLE001
        return link


def get_article_content(url: str) -> str:
    """抓取公众号文章正文。"""
    resp = httpx.get(url, headers=HEADERS, follow_redirects=True, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")
    content = soup.select_one("#js_content") or soup.select_one(".rich_media_content")
    if not content:
        return ""
    return content.get_text("\n", strip=True)
