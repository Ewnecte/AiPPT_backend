"""ADKAgentExecutor —— 把 ADK Runner 封装成 A2A 可用的 AgentExecutor。

参考复现计划 6.1。用于 A2A 服务里桥接 google.adk 与 a2a-sdk。
版本敏感，实际接入时需按安装的 google-adk / a2a-sdk 版本对齐接口。
"""


class ADKAgentExecutor:
    """占位：封装 ADK Runner，供 A2A 服务调用。"""

    def __init__(self, agent):
        self.agent = agent
        # TODO: 初始化 google.adk.runners.Runner + SessionService + ArtifactService

    async def execute(self, message: str) -> str:
        # TODO: 调 Runner 流式执行，返回大纲文本
        raise NotImplementedError("TODO: 接入 ADK Runner 执行")
