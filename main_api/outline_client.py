"""A2A 大纲客户端封装（TODO）

参考复现计划第 8.3 节：
  1. setup() 获取 AgentCard
  2. generate(prompt, language) → send_message_streaming
  3. 解析 status-update / artifact-update 分块，拼接 Markdown
"""


class A2AOutlineClientWrapper:
    """调用 simpleOutline Agent 生成大纲，流式返回 Markdown。"""

    def __init__(self, base_url: str):
        self.base_url = base_url
        # TODO: 初始化 a2a.client.A2AClient

    async def generate(self, content: str, language: str, model: str):
        """流式返回 Markdown 大纲。"""
        raise NotImplementedError("TODO: 实现大纲 A2A 调用")
