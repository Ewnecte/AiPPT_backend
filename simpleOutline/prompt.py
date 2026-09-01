"""大纲 Prompt —— TODO

参考复现计划第 6.2 节：
  格式约束：# 标题 → ## 一级(5个) → ### 二级(3-4个) → - 要点(3-5条)
  输入长度 ≤ USER_INPUT_NUMBER → WITH_SEARCH；否则 NO_SEARCH
"""

# 输入字数阈值：小于等于该值走带搜索 Prompt
USER_INPUT_NUMBER = 1000

OUTLINE_INSTRUCTION_WITH_SEARCH = """TODO: 带网络搜索的大纲 Prompt（结合搜到的文章扩充大纲）"""

OUTLINE_INSTRUCTION_NO_SEARCH = """TODO: 不带搜索的大纲 Prompt（仅依据用户内容生成大纲）"""
