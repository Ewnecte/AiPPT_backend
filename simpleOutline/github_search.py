"""GitHub 仓库/README 检索：把『代码 / 开源库』类问题导向仓库一手资料。

供 ppt_writer 联网检索作补充通道：当查询词明显指向某个代码库或开源项目
（如 LangChain、FastAPI、某个 owner/repo）时，普通网页结果往往只有教程
软文，而仓库 README 才是权威原文。这里直接调 GitHub REST API：
  - GET /search/repositories：按关键词搜仓库（无 token 即可用，限额低，
    仅当常规搜索无结果时才触发，够生成场景使用）；
  - GET /repos/{full_name}/readme：以原始文本格式取 README，转成纯文本。

凭据：可选环境变量 GH_TOKEN（自建 token）可显著提高限额并访问私有仓库。
任何网络/授权失败一律静默降级返回 []，不影响主流程。
"""
import os
import re

import httpx

from weixin_search import HEADERS

_API = "https://api.github.com"
_README_RAW_ACCEPT = "application/vnd.github.raw"
# 单次抓取 README 上限 / 超时
_README_LIMIT = 1600
_GH_TIMEOUT = 10.0

# 代码/仓库语义信号：命中才走 GitHub 通道（普通营销查询没必要打它）
_REPO_QUERY_RE = re.compile(
    r"\bgithub\b|\bgh\b|\brepo(sitory)?\b|开源|源码|代码库|githubusercontent|"
    r"\b[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\b",
    re.I,
)

# 提取拉丁项目名 token 时的通用词黑名单（避免拿 'how/what/repo' 这类词去搜仓库）
_GENERIC_EN_WORDS = {
    "how", "what", "why", "when", "where", "which", "who", "the", "and", "for",
    "with", "from", "use", "using", "used", "github", "git", "repo", "repos",
    "repository", "code", "source", "open", "tool", "tools", "library", "lib",
    "framework", "project", "projects", "official", "latest", "introduction",
}
_LATIN_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9._+-]{1,}")


def _gh_query(keyword: str) -> str:
    """把整句查询收敛成 GitHub 能命中的关键词。

    GitHub 仓库搜索按 name/description/topics 做 AND 匹配，中文自然语句基本
    颗粒无收，需要提取其中像「项目名」的拉丁 token（LangChain/FastAPI/aippt…）。
    owner/repo 写法（如 torchvision/models）原样返回；无拉丁 token 时退回
    原始关键字，命中率低但保底不空跑。
    """
    if re.search(r"\b[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\b", keyword):
        return keyword
    toks = [
        t for t in _LATIN_TOKEN_RE.findall(keyword)
        if len(t) >= 3 and t.lower() not in _GENERIC_EN_WORDS
    ]
    if not toks:
        return keyword
    return " ".join(list(dict.fromkeys(toks))[:4])  # 去重保序，最多 4 个


def _auth_headers() -> dict:
    token = os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")
    if not token:
        return dict(HEADERS)
    return {**HEADERS, "Authorization": f"Bearer {token}"}


def _md_to_text(md: str) -> str:
    """把 markdown README 粗转纯文本（够作检索材料，不必还原富文本）。"""
    lines: list[str] = []
    for raw in md.splitlines():
        line = raw.strip()
        if not line:
            continue
        # 跳过代码围栏标记（代码正文行保留为普通文本，成本可控）
        if line.startswith("```") or line.startswith("~~~"):
            continue
        # 跳过纯图片/徽章行
        if re.fullmatch(r"!\[[^\]]*\]\([^)]*\)", line) or line.startswith("!["):
            continue
        # README 常用裸 HTML 排版（<div align=center> 等）：行首是标签的按 HTML 剥离
        if line.startswith("<"):
            line = re.sub(r"<[^>]*>", "", line)
        # 行内代码 / 链接统一去语法，保留可见文字
        line = re.sub(r"`([^`]*)`", r"\1", line)
        line = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", line)
        line = re.sub(r"^#{1,6}\s+", "", line)
        line = re.sub(r"[*_~>]", "", line)
        line = re.sub(r"\s{2,}", " ", line).strip()
        if line:
            lines.append(line)
    # 收敛成段落文本
    return "\n".join(lines).strip()


def looks_like_repo_query(keyword: str) -> bool:
    """查询词是否像指向代码/仓库的请求（避免无谓消耗 GitHub API 配额）。"""
    return bool(_REPO_QUERY_RE.search(keyword))


def _readme_text(full_name: str) -> str:
    """取仓库 README 原始文本；404/网络/无 README 抛异常由调用方处理。"""
    resp = httpx.get(
        f"{_API}/repos/{full_name}/readme",
        headers={**_auth_headers(), "Accept": _README_RAW_ACCEPT},
        timeout=_GH_TIMEOUT,
    )
    resp.raise_for_status()
    text = _md_to_text(resp.text)
    return text[:_README_LIMIT]


def _score_item(item: dict, tokens: list[str]) -> int:
    """仓库与查询的贴合度：短名精确等于查询 token 权重最高（覆盖 star 排序误差）。"""
    short = (item.get("name") or "").lower()
    if not short or not tokens:
        return 0
    for t in tokens:
        tl = t.lower()
        if short == tl:
            return 2
    for t in tokens:
        if t.lower() in short or short in t.lower():
            return 1
    return 0


def repo_search(keyword: str, top_n: int = 2) -> list[dict]:
    """按关键词搜 GitHub 仓库并取各自 README。

    多取一些候选（per_page 放宽到 top_n 的 3 倍），按「短名贴合查询」重排，
    再取前 top_n 抓 README —— GitHub 的 star 排序未必把精确同名仓库放最前。
    返回 [{title, real_url, content}]；网络/授权失败抛出异常由调用方降级。
    """
    gh_q = _gh_query(keyword)
    tokens = _LATIN_TOKEN_RE.findall(gh_q)
    resp = httpx.get(
        f"{_API}/search/repositories",
        params={
            "q": gh_q, "sort": "stars", "order": "desc",
            "per_page": min(top_n * 3, 30),
        },
        headers=_auth_headers(),
        timeout=_GH_TIMEOUT,
    )
    resp.raise_for_status()
    items = sorted(
        (resp.json().get("items") or []),
        key=lambda it: (_score_item(it, tokens), it.get("stargazers_count") or 0),
        reverse=True,
    )[:top_n]
    results: list[dict] = []
    for item in items:
        full_name = item.get("full_name") or ""
        if not full_name:
            continue
        text = _readme_text(full_name)  # 无 README 会抛异常，交由外层整体降级
        if not text:
            continue
        desc = (item.get("description") or "").strip()
        suffix = f"（{desc[:40]}…）" if len(desc) > 40 else (f"（{desc}）" if desc else "")
        results.append(
            {
                "title": f"{full_name} {suffix}".strip(),
                "real_url": item.get("html_url") or f"https://github.com/{full_name}",
                "content": text,
            }
        )
    return results
