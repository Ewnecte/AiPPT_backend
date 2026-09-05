"""JSON 校验工具。

参考复现计划 7.2：
  - only_json：截取首个 { 到末个 }
  - validate_slide：字段规则校验（不调用 LLM）
"""
import json

# 与 frontend/src/types/AIPPT.ts 的 ChartType 保持一致
_VALID_CHART_TYPES = {"line", "bar", "pie", "column", "ring", "area", "radar"}


def only_json(text: str) -> str:
    """从模型输出中截取 JSON 片段（首个 { 到末个 }）。"""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return text
    return text[start : end + 1]


def validate_slide(data: dict) -> bool:
    """校验单页 Slide 是否满足基本 schema。

    除 type/data 外，额外校验：
      - data.items 若存在必须是列表
      - kind=chart 的项需携带合法 chartType + labels + series
    """
    if not isinstance(data, dict):
        return False
    if "type" not in data or not isinstance(data["type"], str):
        return False

    d = data.get("data")
    # data 允许缺失或为空（如 end 页）
    if d is None:
        return True
    if not isinstance(d, dict):
        return False

    items = d.get("items")
    if items is not None and not isinstance(items, list):
        return False

    for it in items or []:
        if isinstance(it, dict) and it.get("kind") == "chart":
            if it.get("chartType") not in _VALID_CHART_TYPES:
                return False
            if not isinstance(it.get("labels"), list) or not isinstance(it.get("series"), list):
                return False
    return True


def parse_slide(text: str) -> dict | None:
    """从文本解析并校验出合法 Slide，失败返回 None。"""
    try:
        data = json.loads(only_json(text))
    except (json.JSONDecodeError, ValueError):
        return None
    return data if validate_slide(data) else None
