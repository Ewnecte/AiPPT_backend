"""通用网页正文清洗器（供 ppt_writer 联网搜索抓取任意网页正文）。

背景：联网检索的来源不止公众号，还有 Bing 等通用网页。公众号有固定的
#js_content 容器，普通文章页则是各种模板（article/main + 语义 class），
因此需要一个「下载 → 去噪 → 抽正文 → 收敛为段落文本」的通用实现。

策略（尽力而为，仅依赖 httpx + BeautifulSoup(lxml)，不引入新依赖）：
  1. httpx 下载 HTML（UA / 超时 / 体积上限），失败抛异常交由调用方降级；
  2. 用 lxml 解析后先剔除 script/style/nav/footer 等噪音节点，
     再按 id/class 语义剔除导航/广告/评论等区块，并剔除纯链接列表
     （语言切换、菜单等——正文块绝不会整块都是链接）；
  3. 候选正文根节点按「段落文本量」打分择优，而不是总文本量——
     正文容器段落密集，而整页包装层虽然文本多但段落未必多，且
     同分时偏向更内层（更具体、噪音更少）的节点。优先级：
     微信 #js_content → article/main 等语义标签 → id/class 含
     content/article/post/entry 提示词的容器 → 段落太少时退化为 <body>；
  4. 从根节点收集 <p>/标题/<li> 文本为段落，收敛空白并按字符预算截断。

说明：本模块为同步阻塞实现；调用方（tools.document_search）负责放进
线程池并发执行，避免阻塞事件循环。
"""
import re

import httpx
from bs4 import BeautifulSoup

from .weixin_search import HEADERS

# 每篇文章清洗后保留的正文长度上限（agent 注入 prompt 时还会再截断一次）
DEFAULT_LIMIT = 1600
# 单次抓取允许的最大 HTML 体积，防止超大页拖垮内存
MAX_HTML_BYTES = 2_000_000
# 单次抓取超时（秒）。外层 wait_for 对整次搜索给 12s，这里必须更短
FETCH_TIMEOUT = 10.0

# 整块剔除的标签
_STRIP_SELECTORS = (
    "script,style,noscript,template,svg,iframe,canvas,form,button,input,select,"
    "textarea,nav,aside,footer,audio,video,figure"
)
# 语义噪音区块：id/class 命中即移除（导航/广告/评论/分享等）
_NOISE_RE = re.compile(
    r"\b(nav|navbar|menu|breadcrumb|pagination|sidebar|widget|comment|comments?"
    r"|related|recommend|share|toolbar|advert|ad-|ads-|banner|popup|promo|"
    r"login|signup|cookie|copyright|foot|header-top|tags|interlanguage|"
    r"interwiki|sister|langlink)\b",
    re.I,
)
# 正文容器提示：id/class 命中即视为候选正文根
_CONTENT_HINT_RE = re.compile(
    r"\b(content|article|post|entry|rich_media|js_content|doc-page|main|body)\b",
    re.I,
)
_HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}


def _attr(el, key: str) -> str:
    """安全读取标签属性：bs4 在无属性标签上 attrs 可能为 None，不能直接 .get。"""
    attrs = el.attrs or {}
    val = attrs.get(key, "")
    if isinstance(val, list):
        return " ".join(str(v) for v in val)
    return str(val)


def _text_len(el) -> int:
    """元素纯文本长度（去空白）。"""
    return len(el.get_text(" ", strip=True))


def _link_len(el) -> int:
    """元素内 <a> 链接文字总长（用于识别整块都是链接的列表）。"""
    return sum(_text_len(a) for a in el.find_all("a"))


def _para_len(el) -> int:
    """元素内 <p>/<blockquote> 段落文字总长（正文容器段落密集）。"""
    return sum(_text_len(p) for p in el.find_all(["p", "blockquote"]))


def _strip_noise(soup: BeautifulSoup) -> None:
    """就地剔除噪音节点。"""
    for node in soup.select(_STRIP_SELECTORS):
        node.decompose()
    # 语义噪音：id/class 命中噪音关键词的块级元素（但保留正文容器类）
    for node in list(soup.find_all(["div", "section", "ul", "ol"])):
        marker = f"{_attr(node, 'id')} {_attr(node, 'class')}".strip()
        if not marker:
            continue
        if _NOISE_RE.search(marker) and not _CONTENT_HINT_RE.search(marker):
            node.decompose()
    # 纯链接列表：语言切换 / 菜单等，正文列表不会整块都是链接
    for node in list(soup.find_all(["ul", "ol"])):
        total = _text_len(node)
        if total > 8 and _link_len(node) / total > 0.6:
            node.decompose()


def _pick_best(candidates: list) -> object:
    """按段落文字量选最优正文根；同分取更小（更内层、噪音更少）者。"""
    best = None
    best_para = -1
    for el in candidates:
        p = _para_len(el)
        if p > best_para or (p == best_para and best is not None and _text_len(el) < _text_len(best)):
            best = el
            best_para = p
    return best


def _pick_root(soup: BeautifulSoup):
    """按优先级挑出正文根节点。"""
    # 1. 微信公众号正文
    for sel in ("#js_content", ".rich_media_content"):
        el = soup.select_one(sel)
        if el and _text_len(el) > 40:
            return el
    # 2. 语义标签（article/main/role=main/itemprop 等）
    semantic = [el for el in soup.select("article, main, [role='main'], [itemprop='articleBody']")]
    if semantic:
        return _pick_best(semantic)
    # 3. id/class 含正文提示词的容器
    hinted = [
        el
        for el in soup.find_all(["div", "section"])
        if _CONTENT_HINT_RE.search(f"{_attr(el, 'id')} {_attr(el, 'class')}")
    ]
    if hinted:
        root = _pick_best(hinted)
        if root is not None and _para_len(root) >= 40:
            return root
    # 4. 兜底：body（噪音已剔除）
    return soup.body or soup


def _collect_lines(root) -> list[str]:
    """从正文根收集可读段落，返回文本行列表。"""
    if root is None:
        return []
    lines: list[str] = []
    for el in root.find_all(["p", "li", "blockquote", *sorted(_HEADING_TAGS)]):
        # 避免 p 内嵌再取一遍（li 里的 p 也只在 li 层取）
        if el.find_parent(["p", "li"]) is not None and el.name not in _HEADING_TAGS:
            continue
        text = el.get_text(" ", strip=True)
        text = re.sub(r"[ \t　]{2,}", " ", text)
        if not text:
            continue
        # 过滤过短碎片（非标题）；列表项适当放宽
        min_len = 6 if el.name == "li" else 12
        if len(text) < min_len and el.name not in _HEADING_TAGS:
            continue
        lines.append(text)

    # 结构化收集太短时（纯 div 排版页），退化为整块文本按行切
    if sum(len(t) for t in lines) < 120:
        raw = root.get_text("\n", strip=True)
        lines = [ln for ln in (re.sub(r"[ \t　]{2,}", " ", ln).strip() for ln in raw.splitlines()) if len(ln) >= 6]

    # 去除连续重复行（模板常把同一句输出多次）
    deduped: list[str] = []
    for ln in lines:
        if deduped and ln == deduped[-1]:
            continue
        deduped.append(ln)
    return deduped


def _truncate(lines: list[str], limit: int) -> str:
    """按字符预算拼装正文，超出部分截断。"""
    out: list[str] = []
    total = 0
    for ln in lines:
        if total + len(ln) > limit:
            if out and total < limit:
                out.append("……")
            break
        out.append(ln)
        total += len(ln) + 1
    text = "\n".join(out)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_html_text(html: str, limit: int = DEFAULT_LIMIT) -> str:
    """从 HTML 字符串抽取正文纯文本（纯函数，便于测试）。"""
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")
    _strip_noise(soup)
    root = _pick_root(soup)
    return _truncate(_collect_lines(root), limit)


def fetch_text(url: str, limit: int = DEFAULT_LIMIT) -> str:
    """抓取 URL 并返回清洗后的正文文本；网络/解析失败抛异常由调用方处理。"""
    resp = httpx.get(
        url,
        headers=HEADERS,
        follow_redirects=True,
        timeout=FETCH_TIMEOUT,
    )
    resp.raise_for_status()
    if len(resp.content) > MAX_HTML_BYTES:
        raise RuntimeError(f"页面过大({len(resp.content)}B)，已跳过")
    return extract_html_text(resp.text, limit=limit)
