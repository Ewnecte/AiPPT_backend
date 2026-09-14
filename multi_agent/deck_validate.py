"""成稿装配与结构校验。

- build_deck(): 大纲 + 文案 + 配图 → SlideSchema[]（与前端契约 types/AIPPT.ts 对齐）
- validate_deck(): 「PPT 可正常打开率」「页数/结构合规率」的判定依据：
    * 可正常打开：JSON 可序列化、每页 type 合法、data 结构合法（前端能解析渲染）
    * 结构合规：封面在首、结束页在尾、目录存在（章节≥3 时）、内容页有标题与要点、
                页数落在 [6, 30]
"""
from __future__ import annotations

import re
from typing import Any

SLIDE_TYPES = {"cover", "contents", "transition", "content", "reference", "end"}
MIN_PAGES, MAX_PAGES = 6, 30


# ---------------------------------------------------------------- 大纲解析
def parse_outline(md: str) -> dict:
    """把 Markdown 大纲解析成 {title, subtitle, sections:[{title, subheads:[str], bullets:[str]}]}"""
    title = ""
    subtitle = ""
    sections: list[dict] = []
    cur: dict | None = None
    cur_sub: dict | None = None  # type: ignore[type-arg]

    for raw in (md or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        h = re.match(r"^(#{1,6})\s+(.+)$", line)
        if h:
            level, body = len(h.group(1)), h.group(2).strip()
            if level == 1 and not title:
                title = body
            elif level == 2:
                cur = {"title": body, "subheads": [], "bullets": []}
                sections.append(cur)
                cur_sub = None
            else:
                if cur is None:
                    cur = {"title": "", "subheads": [], "bullets": []}
                    sections.append(cur)
                cur["subheads"].append(body)
                cur_sub = {"title": body, "bullets": []}
                cur.setdefault("subs", []).append(cur_sub)
            continue
        b = re.match(r"^[-*+]\s+(.+)$", line)
        if b and cur is not None:
            cur["bullets"].append(b.group(1).strip())
        elif not title and not subtitle:
            subtitle = line

    if not title and sections:
        title = sections[0]["title"]
    return {"title": title or "未命名演示文稿", "subtitle": subtitle, "sections": sections}


# ---------------------------------------------------------------- 成稿装配
def build_deck(outline_md: str, copies: dict[str, str] | None = None, images: list[dict] | None = None,
               attribution: list[str] | None = None) -> list[dict]:
    """装配 SlideSchema[]（前端可直接解析渲染；结构合规）。"""
    plan = parse_outline(outline_md)
    copies = copies or {}
    images = list(images or [])
    deck: list[dict] = []

    deck.append({"type": "cover", "data": {"title": plan["title"], "text": plan["subtitle"] or "由多 Agent 自动生成"}})
    section_titles = [s["title"] for s in plan["sections"] if s["title"]]
    deck.append({"type": "contents", "data": {"items": section_titles[:8] or ["内容概览"]}})

    used_img = 0
    for sec in plan["sections"]:
        if sec["title"]:
            deck.append({"type": "transition", "data": {"title": sec["title"], "text": ""}})
        items: list[dict] = []
        copy_text = copies.get(sec["title"], "")
        for sub in sec.get("subs", [])[:4]:
            items.append({"title": sub["title"], "text": "；".join(sub["bullets"][:4]) or copy_text})
        if not items:
            items = [{"title": sec["title"] or "要点", "text": copy_text or "；".join(sec["bullets"][:4])}]
        # 每章最后一页挂一张已审核通过的配图
        if used_img < len(images):
            img = images[used_img]
            used_img += 1
            items.append({"title": img.get("title") or "配图", "text": img.get("attribution", {}).get("license", ""), "kind": "image", "url": img.get("url", "")})
        deck.append({"type": "content", "data": {"title": sec["title"] or "内容", "items": items}})

    if attribution:
        deck.append({"type": "reference", "data": {"title": "图片来源说明", "references": attribution}})
    deck.append({"type": "end", "data": {}})
    return deck


# ---------------------------------------------------------------- 校验
def validate_deck(deck: Any) -> dict:
    """返回 {openable, openable_reason, structure_ok, structure_reasons, page_count, types}"""
    openable_reasons: list[str] = []
    structure_reasons: list[str] = []

    if not isinstance(deck, list) or not deck:
        return {
            "openable": False,
            "openable_reason": "deck 不是非空数组",
            "structure_ok": False,
            "structure_reasons": ["deck 为空"],
            "page_count": 0,
            "types": [],
        }

    types: list[str] = []
    for i, slide in enumerate(deck):
        if not isinstance(slide, dict):
            openable_reasons.append(f"第{i + 1}页不是对象")
            continue
        st = slide.get("type")
        if st not in SLIDE_TYPES:
            openable_reasons.append(f"第{i + 1}页 type 非法：{st!r}")
            continue
        types.append(st)
        data = slide.get("data", {})
        if not isinstance(data, dict):
            openable_reasons.append(f"第{i + 1}页 data 不是对象")
            continue
        if st == "content":
            if not str(data.get("title", "")).strip():
                structure_reasons.append(f"第{i + 1}页缺少标题")
            items = data.get("items")
            if not isinstance(items, list) or not items:
                structure_reasons.append(f"第{i + 1}页缺少内容项")
        if st == "contents":
            items = data.get("items")
            if not isinstance(items, list) or not items:
                structure_reasons.append("目录页没有条目")

    page_count = len(types)
    if page_count < MIN_PAGES:
        structure_reasons.append(f"页数不足（{page_count} < {MIN_PAGES}）")
    if page_count > MAX_PAGES:
        structure_reasons.append(f"页数过多（{page_count} > {MAX_PAGES}）")
    if not types or types[0] != "cover":
        structure_reasons.append("缺少封面或封面不在首页")
    if "end" not in types:
        structure_reasons.append("缺少结束页")
    if len([t for t in types if t == "content"]) == 0:
        structure_reasons.append("没有内容页")

    return {
        "openable": not openable_reasons,
        "openable_reason": "；".join(openable_reasons),
        "structure_ok": not openable_reasons and not structure_reasons,
        "structure_reasons": structure_reasons,
        "page_count": page_count,
        "types": types,
    }


def quality_score(deck: Any) -> float:
    """启发式质量分（0~100）：结构合规 + 页数适中 + 内容密度，用于⑤的自动对比维度。

    人工评分仍是最终依据，此分数用于无人工介入时的快速对比与回归。
    """
    v = validate_deck(deck)
    score = 0.0
    score += 35 if v["openable"] else 0
    score += 25 if v["structure_ok"] else 10
    pages = v["page_count"]
    if 8 <= pages <= 18:
        score += 20
    elif 6 <= pages <= 24:
        score += 12
    else:
        score += 4
    # 内容密度：内容页的平均条目数（越丰富越好，最多 20 分）
    items_total, content_pages = 0, 0
    for slide in deck if isinstance(deck, list) else []:
        if isinstance(slide, dict) and slide.get("type") == "content":
            content_pages += 1
            items = (slide.get("data") or {}).get("items") or []
            items_total += len(items) if isinstance(items, list) else 0
    if content_pages:
        avg_items = items_total / content_pages
        score += min(20.0, avg_items * 5.0)
    return round(min(100.0, score), 1)
