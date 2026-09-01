"""模板生成器 —— 生成 template_1..4.json（PPTist 文档格式）+ SVG 封面。

格式对齐参考项目：顶层 title/width/height/theme/slides/intend，
每个 slide 带 type（cover/contents/transition/content/end）标注，
文本元素带 textType（title/subtitle/itemTitle/item/content）。

运行：python generate_templates.py
"""
import json
from pathlib import Path

W, H = 1000, 562.5

# 四套主题（名称与配色，对应前端模板选择页）
TEMPLATES = [
    {"name": "科技蓝紫", "c1": "#667eea", "c2": "#764ba2", "colors": ["#667eea", "#764ba2", "#3b82f6", "#8b5cf6", "#a78bfa", "#c4b5fd"]},
    {"name": "商务蓝", "c1": "#0ea5e9", "c2": "#6366f1", "colors": ["#0ea5e9", "#6366f1", "#3b82f6", "#1d4ed8", "#38bdf8", "#7dd3fc"]},
    {"name": "活力橙", "c1": "#f97316", "c2": "#ef4444", "colors": ["#f97316", "#ef4444", "#f59e0b", "#fb7185", "#fbbf24", "#fda4af"]},
    {"name": "清新绿", "c1": "#10b981", "c2": "#14b8a6", "colors": ["#10b981", "#14b8a6", "#22c55e", "#2dd4bf", "#4ade80", "#5eead4"]},
]


def _shape(sid, left, top, width, height, fill):
    return {
        "type": "shape", "id": sid, "left": left, "top": top,
        "width": width, "height": height, "viewBox": [200, 200],
        "path": "M 0 0 L 200 0 L 200 200 L 0 200 Z",
        "fill": fill, "fixedRatio": False, "rotate": 0, "lock": True,
    }


def _text(tid, left, top, width, height, content, text_type, color="#333"):
    return {
        "type": "text", "id": tid, "left": left, "top": top,
        "width": width, "height": height, "content": content,
        "rotate": 0, "defaultFontName": "", "defaultColor": color,
        "vertical": False, "textType": text_type,
    }


def _chart(cid, left, top, width, height):
    return {
        "type": "chart", "id": cid, "left": left, "top": top,
        "width": width, "height": height, "chartType": "bar", "chartMark": "chartItem",
    }


def _image(iid, left, top, width, height):
    return {
        "type": "image", "id": iid, "left": left, "top": top,
        "width": width, "height": height, "src": "", "imageType": "itemFigure",
    }


def _slide(sid, stype, elements, bg="#ffffff"):
    return {"id": sid, "type": stype, "background": {"type": "solid", "color": bg}, "elements": elements}


def cover(theme):
    c1 = theme["c1"]
    return _slide("cover-1", "cover", [
        _shape("bg", 0, 0, W, H, c1),
        _text("t", 100, 190, 800, 130, '<p style="text-align:center;"><strong><span style="font-size:54px;">模板封面标题</span></strong></p>', "title", "#ffffff"),
        _text("s", 100, 330, 800, 60, '<p style="text-align:center;"><span style="font-size:20px;">副标题</span></p>', "subtitle", "#ffffff"),
    ], bg=c1)


def contents(theme, n=5):
    items = []
    for i in range(n):
        y = 90 + i * 74
        items.append(_shape(f"dot{i}", 80, y + 14, 14, 14, theme["colors"][0]))
        items.append(_text(f"it{i}", 110, y, 760, 40, f'<p><strong><span style="font-size:20px;">目录项 {i + 1}</span></strong></p>', "item"))
    return _slide("contents-1", "contents", items)


def transition(theme):
    return _slide("transition-1", "transition", [
        _shape("bar", 60, 250, 60, 6, theme["colors"][0]),
        _text("t", 60, 270, 880, 90, '<p><strong><span style="font-size:40px;">章节标题</span></strong></p>', "title"),
    ])


def content(theme, n, sid, with_chart=False, with_image=False):
    elements = [_text("t", 50, 30, 900, 60, '<p><strong><span style="font-size:32px;">页面标题</span></strong></p>', "title")]
    elements.append(_shape("bar", 50, 90, 60, 6, theme["colors"][0]))

    cols = 2
    item_w, item_h = 420, 90
    gap_x, gap_y = 40, 30
    start_y = 120
    for i in range(n):
        col, row = i % cols, i // cols
        left = 50 + col * (item_w + gap_x)
        top = start_y + row * (item_h + gap_y)
        elements.append(_shape(f"card{i}", left, top, item_w, item_h, "#f5f6fa"))
        elements.append(_text(f"it{i}", left + 16, top + 12, item_w - 32, 28, f'<p><strong><span style="font-size:18px;">要点 {i + 1}</span></strong></p>', "itemTitle"))
        elements.append(_text(f"ic{i}", left + 16, top + 44, item_w - 32, 40, f'<p><span style="font-size:14px;">要点 {i + 1} 的详细说明</span></p>', "item"))

    if with_chart:
        elements.append(_chart("chart", 50, 300, 400, 220))
    if with_image:
        elements.append(_image("img", 500, 300, 400, 220))

    return _slide(sid, "content", elements)


def end(theme):
    c1 = theme["c1"]
    return _slide("end-1", "end", [
        _shape("bg", 0, 0, W, H, c1),
        _text("t", 100, 230, 800, 100, '<p style="text-align:center;"><strong><span style="font-size:48px;">谢谢观看</span></strong></p>', "title", "#ffffff"),
    ], bg=c1)


def build_template(theme):
    """组装一套模板：cover + contents + transition + 4 个 content + chart + end。"""
    slides = [
        cover(theme),
        contents(theme, 5),
        transition(theme),
        content(theme, 2, "content-2"),
        content(theme, 3, "content-3"),
        content(theme, 4, "content-4"),
        content(theme, 6, "content-6"),
        content(theme, 3, "content-chart", with_chart=True),
        end(theme),
    ]
    return {
        "title": f"{theme['name']}模板",
        "width": W,
        "height": H,
        "theme": {
            "themeColors": theme["colors"],
            "fontColor": "#333",
            "fontName": "",
            "backgroundColor": "#fff",
            "shadow": {"h": 3, "v": 3, "blur": 2, "color": "#808080"},
            "outline": {"width": 2, "color": "#525252", "style": "solid"},
        },
        "slides": slides,
        "intend": 4,
    }


def write_cover(idx, theme):
    c1, c2, name = theme["c1"], theme["c2"], theme["name"]
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="480" height="270" viewBox="0 0 480 270">
  <defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="{c1}"/><stop offset="1" stop-color="{c2}"/>
  </linearGradient></defs>
  <rect width="480" height="270" fill="url(#g)"/>
  <rect x="32" y="40" width="6" height="36" rx="3" fill="#fff" opacity="0.9"/>
  <text x="52" y="68" font-family="sans-serif" font-size="28" font-weight="bold" fill="#fff">{name}</text>
  <rect x="32" y="130" width="210" height="12" rx="6" fill="#fff" opacity="0.85"/>
  <rect x="32" y="152" width="140" height="12" rx="6" fill="#fff" opacity="0.55"/>
</svg>'''
    Path(f"template_{idx}.svg").write_text(svg, encoding="utf-8")


def main():
    for idx, theme in enumerate(TEMPLATES, start=1):
        doc = build_template(theme)
        Path(f"template_{idx}.json").write_text(
            json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        write_cover(idx, theme)
        print(f"生成 template_{idx}.json + template_{idx}.svg（{theme['name']}，{len(doc['slides'])} 页）")


if __name__ == "__main__":
    main()
