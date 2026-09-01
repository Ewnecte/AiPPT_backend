"""JSON 校验工具 —— TODO

参考复现计划第 7.2 节：
  - only_json：截取首个 { 到末个 } 尝试 json.loads
  - validate_slide：对比必填字段（type/data 结构）
"""


def only_json(text: str) -> str:
    """从文本中截取 JSON 片段。"""
    raise NotImplementedError("TODO: 实现 only_json")


def validate_slide(data: dict, schema: dict) -> bool:
    """校验单页 Slide 是否满足 schema。"""
    raise NotImplementedError("TODO: 实现 validate_slide")
