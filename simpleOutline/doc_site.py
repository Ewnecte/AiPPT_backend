"""官网 / 文档站定向抓取：把『单一产品/框架的官方资料』类查询导向一手文档。

背景：PPT 生成时前端只给主题关键词、没有域名输入，而官方文档经常是
普通搜索给不出的权威一手资料（如 FastAPI 的路由 / LangChain 的链用法）。
本模块提供两层能力：
  1. crawl_site(site, top_n)：通用能力——给定官网/文档站 URL，探测
     /sitemap.xml（或 sitemap index）→ 过滤出文档类 URL → 依次抓若干
     doc 页并清洗，返回可注入检索材料的正文。外部以后若拿到用户给的
     具体 URL（加『参考官网』输入框），可直接复用这层；
  2. doc_site_search(keyword, top_n)：可配置猜测——只有当查询像在找
     「某一款产品/框架的官方资料」时，用产品名收敛域名（LangChain →
     python.langchain.com 等，见 _ALIASES；未知产品退回 _generic_candidates
     探测 product.dev/.io/.ai 等），探测到 sitemap 才继续抓，失败一律
     静默返回 []。模糊查询（对比/列举类：MySQL vs PostgreSQL、有哪些
     OCR 工具）不会触发，避免乱猜域名白打外部站。

对齐 github_search 的策略：无谓命中会白白消耗外部站资源，守卫要严、
失败要静默降级，不影响主流程。本模块同步阻塞实现，调用方
（tools.document_search）负责放进线程池。
"""
import html
import re
import time
import urllib.parse

import httpx

from weixin_search import HEADERS
from web_fetcher import fetch_text

# 已知产品 → 官方文档站（含 scheme 的站点 origin；取不到 sitemap 会静默跳过）
_ALIASES = {
    # LLM / Agent 生态
    "langchain": "https://python.langchain.com",
    "langgraph": "https://langchain-ai.github.io/langgraph",
    "ollama": "https://docs.ollama.com",
    "fastgpt": "https://fastgpt.cn",
    "dify": "https://docs.dify.ai",
    "gradio": "https://gradio.app",
    "streamlit": "https://docs.streamlit.io",
    # Python / Web 框架
    "fastapi": "https://fastapi.tiangolo.com",
    "flask": "https://flask.palletsprojects.com",
    "django": "https://docs.djangoproject.com",
    "spring": "https://docs.spring.io",
    "requests": "https://requests.readthedocs.io",
    # 前端
    "react": "https://react.dev",
    "vue": "https://vuejs.org",
    "nextjs": "https://nextjs.org",
    "nuxt": "https://nuxt.com",
    # 数据 / ML
    "pytorch": "https://pytorch.org",
    "tensorflow": "https://www.tensorflow.org",
    "keras": "https://keras.io",
    "numpy": "https://numpy.org",
    "pandas": "https://pandas.pydata.org",
    "matplotlib": "https://matplotlib.org",
    # 基础设施 / 语言
    "kubernetes": "https://kubernetes.io",
    "k8s": "https://kubernetes.io",
    "docker": "https://docs.docker.com",
    "redis": "https://redis.io",
    "nginx": "https://nginx.org",
    "mysql": "https://dev.mysql.com",
    "postgresql": "https://www.postgresql.org",
    "python": "https://docs.python.org",
    "golang": "https://go.dev",
    "rust": "https://doc.rust-lang.org",
    "node": "https://nodejs.org",
    "git": "https://git-scm.com",
}

# 官方资料意图信号：查询命中（或命中别名表）才考虑走本通道
_DOC_INTENT_MARKERS = (
    "官方文档", "官方文档库", "官方手册", "官方指南", "官方教程",
    "官方", "官网", "一手资料",
    "documentation", "official docs", "getting started",
)
# 明确是"对比/列举多款"的查询不属于"单一产品找官方资料"，不要猜域名
_COMPARATIVE_MARKERS = (
    "vs", "对比", "区别", "比较", "优缺点", "怎么选", "如何选择",
    "推荐", "有哪些", "主流", "替代", "发展史", "排行榜",
)

# 拉丁 token 提取
_LATIN_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9._+-]{1,}")
# 泛词黑名单（避免拿 how/what/framework 之类去猜域名）
_GENERIC_EN_WORDS = {
    "how", "what", "why", "when", "where", "which", "who", "the", "and", "for",
    "with", "from", "use", "using", "used", "intro", "introduction", "getting",
    "started", "guide", "guides", "official", "docs", "documentation", "doc",
    "framework", "project", "projects", "latest", "examples", "example",
}

# 文档类路径分段：sitemap 里只挑命中这些段的内容页
_DOC_SEG = {
    "docs", "doc", "documentation", "guide", "guides", "tutorial", "tutorials",
    "getting-started", "getting_started", "quickstart", "quick-start", "start",
    "learn", "reference", "manual", "handbook", "user-guide", "user_guide",
    "concepts", "concept", "overview", "intro", "introduction",
    "installation", "gettingstarted", "use", "usage", "api", "operations",
}
# 明确不是文档正文的路径分段（标签 / 博客 / 下载 / 资源…）
_NOISE_SEG = {
    "tags", "tag", "blog", "news", "changelog", "changelogs", "category",
    "categories", "search", "404", "releases", "release", "download",
    "downloads", "assets", "asset", "static", "images", "image", "img",
    "media", "css", "js", "fonts", "font", "license", "licenses", "community",
    "contributing", "contribute", "contributors", "privacy", "terms",
    "sponsors", "sponsor", "_next", "page-data", "feed", "rss", "videos",
    "video", "slides", "slideshare",
}
# 语言前缀段：/zh/ /de/ 等通常与默认语言重复，丢
_LANG_SEG = {
    "zh", "zh-cn", "zh-tw", "zh-hans", "zh-hant", "en", "en-us", "de", "fr",
    "ja", "ko", "es", "it", "pt", "ru",
}
_SKIP_EXT = (".pdf", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".zip",
             ".tar", ".gz", ".json", ".xml", ".csv", ".mp4", ".webm")

# 探测 sitemap 的路径候选
_SITEMAP_PATHS = ("/sitemap.xml", "/sitemap_index.xml", "/sitemap-index.xml")
_MAX_SITEMAP_BYTES = 5_000_000
_PROBE_TIMEOUT = 6.0
# 抓文档页的预算：最多扫 N 个 sitemap URL，取到 top_n 篇就停
_MAX_TRY_PAGES = 8
# 单篇正文长度预算（与 web_fetcher.DEFAULT_LIMIT 一致；注入时还会再截断）
_PAGE_LIMIT = 1600
# 兜底探测的通用域名后缀（未知产品）
_GENERIC_SUFFIXES = (".dev", ".io", ".ai", ".com")
# 整次 doc_site_search 的硬性时间预算：通道 4 只在常规搜索颗粒无收时才跑，
# 外层 document_search 总共只给 ~12s，这里必须更短，到点即放弃（宁缺毋滥）
_SEARCH_BUDGET = 6.0


def looks_like_doc_query(keyword: str) -> bool:
    """查询是否像在找『某一款产品/框架的官方资料』（避免乱猜域名）。

    需要同时满足：
      - 查询里能提出一个拉丁产品 token（LangChain / FastAPI…）；
      - 且（命中官方意图词 或 命中已知别名表）；
      - 且不是明确的对比/列举型查询（那种应走通用搜索）。
    """
    low = keyword.lower()
    if any(m in low for m in _COMPARATIVE_MARKERS):
        return False
    product = _extract_product(keyword)
    if product is None:
        return False
    if any(m in low for m in _DOC_INTENT_MARKERS):
        return True
    return product.lower() in _ALIASES


def _extract_product(keyword: str) -> str | None:
    """提取查询里最可能指代单一产品/框架的拉丁 token，原大小写返回。"""
    for t in _LATIN_TOKEN_RE.findall(keyword):
        if len(t) >= 3 and t.lower() not in _GENERIC_EN_WORDS:
            # 域名只能用字母数字和连字符：去掉会破坏 host 的符号
            return t.split("/")[0].split("@")[0]
    return None


def _out_of_time(deadline: float) -> bool:
    return deadline is not None and time.monotonic() >= deadline


def _fetch_sitemap_locs(site: str, deadline: float) -> list[str]:
    """探测站点 sitemap，返回其中的文档类 URL（绝对地址，已去噪）。

    site 形如 'https://fastapi.tiangolo.com'（不带尾斜杠）。找不到或解析
    失败返回 []；到 deadline 立即放弃（黑洞域名会长时间无响应），绝不
    抛异常。
    """
    for path in _SITEMAP_PATHS:
        if _out_of_time(deadline):
            break
        try:
            resp = httpx.get(
                site + path, headers=HEADERS, follow_redirects=True,
                timeout=_PROBE_TIMEOUT,
            )
        except Exception:  # noqa: BLE001 —— 网络失败换下一个候选
            continue
        if resp.status_code != 200 or len(resp.content) > _MAX_SITEMAP_BYTES:
            continue
        if b"<" not in resp.content[:256]:  # 不是 XML（可能是反爬 HTML）
            continue
        locs = _extract_loc_urls(resp.text)
        # 若拿到的是 sitemap index（全是子 sitemap），展开前 2 个补齐页 URL
        child_maps = [u for u in locs if _looks_like_sitemap_url(u)]
        if child_maps:
            page_urls: list[str] = []
            for u in child_maps[:2]:
                if _out_of_time(deadline):
                    break
                page_urls.extend(_extract_loc_urls(_get_text(u)))
            locs = page_urls
        docs = _filter_doc_urls(locs, site)
        if docs:
            return docs
    return []


def _get_text(url: str) -> str:
    """同步抓取文本；失败返回空串（仅用于展开子 sitemap）。"""
    try:
        resp = httpx.get(url, headers=HEADERS, follow_redirects=True, timeout=_PROBE_TIMEOUT)
        resp.raise_for_status()
        return resp.text
    except Exception:  # noqa: BLE001
        return ""


def _extract_loc_urls(xml_text: str) -> list[str]:
    """从 sitemap XML 里提取所有 <loc> 并 HTML 反转义（不引 lxml，够用）。"""
    locs = re.findall(r"<loc>\s*([^<]+?)\s*</loc>", xml_text or "", re.I)
    return [html.unescape(u.strip()) for u in locs if u.strip()]


def _looks_like_sitemap_url(url: str) -> bool:
    return url.lower().rstrip("/").endswith(".xml") or "/sitemap" in url.lower()


def _filter_doc_urls(locs: list[str], site: str) -> list[str]:
    """按『与站点同源 + 路径含文档分段 + 非噪音/非资源』过滤文档 URL。

    只保留命中 _DOC_SEG 的内容页；返回按 (命中分段数, 路径深度) 粗排的
    列表（文档味越足、越具体越靠前）。没有文档页则返回 []，由调用方
    决定走根页兜底，避免抓无关的 about/blog 之类页面。
    """
    origin = urllib.parse.urlsplit(site)
    seen: set[str] = set()
    kept: list[tuple[str, int, int]] = []
    for raw in locs:
        try:
            parts = urllib.parse.urlsplit(raw)
        except ValueError:  # noqa: BLE001
            continue
        if parts.scheme not in ("http", "https"):
            continue
        if parts.netloc and parts.netloc.lower() != origin.netloc.lower():
            continue  # 只抓同源页面（CDN/子站交给其它通道）
        if parts.query or parts.fragment:  # 带参/锚点通常是分页或非正文
            continue
        segs = [s for s in parts.path.split("/") if s]
        if not segs:
            continue
        low = [s.lower() for s in segs]
        if low[0] in _LANG_SEG:  # /zh/ /de/ 等语言前缀，通常与默认语言重复
            continue
        if any(s in _NOISE_SEG for s in low):
            continue
        if low[-1].endswith(_SKIP_EXT):  # 文件资源（.pdf/.png…）
            continue
        url = raw.split("#", 1)[0]
        if url in seen:
            continue
        seen.add(url)
        doc_hits = sum(1 for s in low if s in _DOC_SEG)
        if doc_hits:
            kept.append((url, doc_hits, len(low)))
    kept.sort(key=lambda x: (x[1], x[2]), reverse=True)
    return [u for u, _, _ in kept]


def crawl_site(site: str, top_n: int = 2, brand: str = "", deadline: float | None = None) -> list[dict]:
    """抓一个官网/文档站，返回 [{title, real_url, content}]（每篇一页）。

    site 为站点 origin；brand 用于拼标题（缺省取域名）。流程：
    探测 sitemap → 过滤文档 URL → 依序抓取清洗；每篇正文过短会跳过，
    凑不满 top_n 也没关系。找不到 sitemap 或全抓失败时，退回抓站点
    根页（或 /docs）作为单条结果；仍无则返回 []。
    任何单篇失败都静默跳过，不抛异常。
    """
    title_base = brand or urllib.parse.urlsplit(site).netloc
    urls = _fetch_sitemap_locs(site, deadline)
    results: list[dict] = []
    if urls:
        for url in urls[:_MAX_TRY_PAGES]:
            if len(results) >= top_n or _out_of_time(deadline):
                break
            try:
                text = fetch_text(url, limit=_PAGE_LIMIT).strip()
            except Exception:  # noqa: BLE001 —— 单篇失败跳过
                continue
            if len(text) < 80 or _looks_like_bot_page(text):
                continue
            slug = urllib.parse.urlsplit(url).path.rstrip("/").split("/")[-1] or ""
            label = f"{title_base} · {slug}" if slug else title_base
            results.append(
                {"title": label, "real_url": url, "content": text}
            )
        if results:
            return results
    # 退回：抓根页 / /docs 做单条兜底
    for fallback in (f"{site}/docs", site):
        if _out_of_time(deadline):
            break
        try:
            text = fetch_text(fallback, limit=_PAGE_LIMIT).strip()
        except Exception:  # noqa: BLE001
            continue
        if len(text) >= 80 and not _looks_like_bot_page(text):
            return [{"title": title_base, "real_url": fallback, "content": text}]
    return []


# 反爬/验证页特征（与 tools.document_search 一致，轻量过滤）
_BOT_MARKERS = (
    "antispider", "请输入验证码", "访问过于频繁", "环境异常", "安全验证",
    "verify you are human", "unusual traffic", "人机验证",
)


def _looks_like_bot_page(text: str) -> bool:
    low = text.lower()
    return any(m in low for m in _BOT_MARKERS)


def _generic_candidates(product: str) -> list[str]:
    """未知产品的域名候选（按优先级）：product.dev/.io/.ai/.com。"""
    token = re.sub(r"[^A-Za-z0-9-]", "", product.lower())
    if not token:
        return []
    return [f"https://{token}{s}" for s in _GENERIC_SUFFIXES]


def doc_site_search(keyword: str, top_n: int = 2) -> list[dict]:
    """按关键词猜官网并定向抓文档，返回 [{title, real_url, content}]。

    先查已知别名表（LangChain/FastAPI…），命中即抓对应官方文档站；
    未知产品才做通用后缀探测。首个能抓到文档的站点即返回，全部失败
    返回 []。整体受 _SEARCH_BUDGET 硬预算约束（黑洞域名等慢响应会直接
    放弃），网络/解析异常一律静默降级，不抛错。
    """
    product = _extract_product(keyword)
    if product is None:
        return []
    alias_site = _ALIASES.get(product.lower())
    candidates = [alias_site] if alias_site else _generic_candidates(product)
    deadline = time.monotonic() + _SEARCH_BUDGET
    for site in candidates:
        if _out_of_time(deadline):
            break
        try:
            items = crawl_site(site, top_n=top_n, brand=product, deadline=deadline)
        except Exception:  # noqa: BLE001 —— 站点抓取失败换下一个候选
            continue
        if items:
            return items
    return []
