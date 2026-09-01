"""页面类型 Prompt + prompt_mapper —— TODO

参考复现计划第 7.2 节：
  cover / contents / transition / content / end 各有专属 Prompt；
  USE_CHART=true 时 content 支持生成图表项。
"""


def prompt_mapper(slide_type: str) -> str:
    """根据页面类型返回对应 Prompt。"""
    raise NotImplementedError("TODO: 实现 prompt_mapper")
