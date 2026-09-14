"""配图内容安全审核 + 版权来源说明（④）。

两道措施：
  1) 内容安全：对检索关键词与图片元数据（标题/作者/URL）做敏感词与风险类别审核，
     命中即拦截（不允许进入 PPT）；同时保留审核结论，便于追溯。
  2) 版权来源：每张进入 PPT 的图片都附带来源、作者、许可与原始链接，
     最终汇总成「图片来源说明」，可直接放进 PPT 的参考资料页。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# 风险词表（可按需扩展）：涉政/暴恐/色情低俗/违法违规等类别
RISK_WORDS: dict[str, list[str]] = {
    "violence": ["blood", "gore", "weapon", "gun", "war", "corpse", "血腥", "暴力", "枪支", "战争", "尸体"],
    "adult": ["nude", "nsfw", "porn", "sexy", "裸", "色情", "低俗", "情色"],
    "hate": ["nazi", "swastika", "纳粹", "仇恨", "歧视"],
    "illegal": ["drug", "cocaine", "赌博", "毒品", "诈骗", "洗钱"],
    "horror": ["creepy", "horror", "恐怖", "惊悚", "鬼"],
}

# 允许的配图图源（白名单）
ALLOWED_SOURCES = {"pexels", "picsum"}


@dataclass
class SafetyVerdict:
    allowed: bool
    reason: str = ""
    categories: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"allowed": self.allowed, "reason": self.reason, "categories": self.categories}


def _match(text: str) -> list[str]:
    if not text:
        return []
    low = text.lower()
    hits: list[str] = []
    for cat, words in RISK_WORDS.items():
        for w in words:
            if w.lower() in low:
                hits.append(cat)
                break
    return hits


def moderate_query(query: str) -> SafetyVerdict:
    """检索词审核：风险词直接拦截，避免检索到不合规素材。"""
    cats = _match(query)
    if cats:
        return SafetyVerdict(False, f"检索词命中风险类别：{','.join(cats)}", cats)
    return SafetyVerdict(True)


def moderate_image(image: dict) -> SafetyVerdict:
    """图片审核：来源白名单 + 元数据风险词 + URL 协议校验。"""
    url = str(image.get("url") or "")
    if not re.match(r"^https?://", url):
        return SafetyVerdict(False, "图片链接非法（非 http/https）", ["invalid_url"])
    source = str(image.get("source") or "").lower()
    if source and source not in ALLOWED_SOURCES:
        return SafetyVerdict(False, f"图源不在白名单：{source}", ["untrusted_source"])
    text = " ".join(
        str(image.get(k, "")) for k in ("title", "alt", "author", "query", "description")
    )
    cats = _match(text)
    if cats:
        return SafetyVerdict(False, f"图片元数据命中风险类别：{','.join(cats)}", cats)
    return SafetyVerdict(True)


def attribution_of(image: dict) -> dict:
    """生成单张图片的版权来源说明。"""
    source = (image.get("source") or "unknown").lower()
    if source == "pexels":
        license_name = "Pexels License（可免费商用，建议署名）"
        license_url = "https://www.pexels.com/license/"
    elif source == "picsum":
        license_name = "picsum.photos 占位图（演示用，请替换为正式素材）"
        license_url = "https://picsum.photos/"
    else:
        license_name = "未知来源（建议人工复核）"
        license_url = ""
    return {
        "title": image.get("title") or image.get("query") or "",
        "url": image.get("url", ""),
        "source": source,
        "author": image.get("author", ""),
        "license": license_name,
        "license_url": license_url,
    }


def build_attribution_slide(images: list[dict]) -> list[str]:
    """汇总成参考资料页可用的文本行。"""
    lines: list[str] = []
    for i, img in enumerate(images, 1):
        a = attribution_of(img)
        who = f" — {a['author']}" if a["author"] else ""
        lines.append(f"[{i}] {a['title'] or '配图'}｜来源：{a['source']}{who}｜许可：{a['license']}")
    return lines
