"""JSON 校验工具。

参考复现计划 7.2：
  - only_json：截取首个 { 到末个 }
  - validate_slide：字段规则校验（不调用 LLM）
"""
import json


def only_json(text: str) -> str:
    """从模型输出中截取 JSON 片段（首个 { 到末个 }）。"""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return text
    return text[start : end + 1]


def validate_slide(data: dict) -> bool:
    """校验单页 Slide 是否满足基本 schema（type + data）。"""
    if not isinstance(data, dict):
        return False
    if "type" not in data or not isinstance(data["type"], str):
        return False
    # data 允许缺失或为空（如 end 页）
    if "data" in data and data["data"] is not None and not isinstance(data["data"], dict):
        return False
    return True


def parse_slide(text: str) -> dict | None:
    """从文本解析并校验出合法 Slide，失败返回 None。"""
    try:
        data = json.loads(only_json(text))
    except (json.JSONDecodeError, ValueError):
        return None
    return data if validate_slide(data) else None
