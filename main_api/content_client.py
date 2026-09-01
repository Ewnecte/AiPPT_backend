"""A2A 内容客户端封装（TODO）

参考复现计划第 8.3 节：
  1. setup() 获取 AgentCard
  2. generate(markdown, metadata) → send_message_streaming
  3. 解析逐页 JSON，并用 process_chart_part_text 拆包图表/图片项
"""


class A2AContentClientWrapper:
    """调用 slide_agent 逐页生成 Slide JSON，流式返回。"""

    def __init__(self, base_url: str):
        self.base_url = base_url
        # TODO: 初始化 a2a.client.A2AClient

    async def generate(self, markdown: str, metadata: dict):
        """逐页流式返回 Slide Schema JSON。"""
        raise NotImplementedError("TODO: 实现内容 A2A 调用")
