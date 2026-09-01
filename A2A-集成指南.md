# A2A 集成指南（阶段五升级项）

> 当前各服务用 **HTTP 直连**（`main_api → simpleOutline/slide_agent → personaldb`）已打通主链路。
> 本指南说明如何升级为 **A2A（Agent-to-Agent）协议**，与 SRS 3.3/7.1 的多智能体架构对齐。

## 一、为什么用 A2A

A2A 是 Google 提出的 Agent 间标准通信协议（JSON-RPC over HTTP），本项目用它让
`main_api` 以统一的 `AgentCard` 发现、调用大纲/内容两个 Agent，便于后续扩展新 Agent。

| 服务 | 当前（HTTP 直连） | 目标（A2A） |
| ---- | ----------------- | ----------- |
| simpleOutline | `POST /generate` | A2A Server（Starlette + A2AStarletteApplication） |
| slide_agent | `POST /generate` | A2A Server（`show_agent=["ControllerAgent"]`） |
| main_api | `httpx` 调 `/generate` | A2A Client（`A2AClient`，先 `setup()` 拿 AgentCard） |

## 二、依赖与版本

```txt
google-adk==1.5.0
a2a-sdk==0.2.10
```

> ⚠️ **版本敏感**：`google.adk` / `a2a` 的接口在不同版本间有差异，务必先
> `pip install -r requirements.txt` 后，用 `python -c "import a2a; help(a2a.server)"`
> 核对实际接口，再对照下面代码调整。

## 三、参考代码

### 3.1 simpleOutline → A2A Server

```python
# simpleOutline/main_api.py（升级版示意，需按实际版本对齐）
import uvicorn
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.agent_execution import AgentExecutor
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from adk_agent_executor import ADKAgentExecutor
from agent import build_adk_agent

agent = build_adk_agent(provider, model)
executor = ADKAgentExecutor(agent)

card = AgentCard(
    name="AiPPT 大纲 Agent",
    description="根据主题生成 Markdown 大纲",
    url="http://127.0.0.1:10001",
    version="1.0.0",
    capabilities=AgentCapabilities(streaming=True),
    skills=[AgentSkill(id="outline", name="大纲生成", description="...", tags=["outline"])],
)

server = A2AStarletteApplication(executor=executor, agent_card=card)
uvicorn.run(server.build(), host="127.0.0.1", port=10001)
```

### 3.2 ADKAgentExecutor（把 ADK Runner 桥接给 A2A）

```python
# simpleOutline/adk_agent_executor.py（升级版示意）
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.types import Part, TaskState, TextPart, UnaryPart

class ADKAgentExecutor(AgentExecutor):
    def __init__(self, agent):
        self.agent = agent
        # 初始化 google.adk.runners.Runner + SessionService + ArtifactService

    async def execute(self, context: RequestContext, event_queue) -> None:
        # 解析用户消息 → runner.run_async 流式执行 → 把 delta 压入 event_queue
        ...
```

### 3.3 main_api → A2A Client

```python
# main_api/outline_client.py（升级版示意）
from a2a.client import A2AClient
from a2a.types import MessageSendParams, Message, Part, TextPart

class A2AOutlineClientWrapper:
    def __init__(self, base_url: str):
        self.client = A2AClient(base_url)

    async def generate(self, content, language, model):
        await self.client.setup()  # 拉取 AgentCard
        params = MessageSendParams(message=Message(
            role="user", parts=[Part(root=TextPart(text=content))]
        ))
        # send_message_streaming，解析 status-update / artifact-update 分块
        async for item in self.client.send_message_streaming(params):
            ...
```

## 四、实施步骤

1. 先装依赖并核对 `google.adk` / `a2a` 实际接口。
2. 把 `simpleOutline`、`slide_agent` 的 `main_api.py` 换成 A2A Server（保留 `agent.py` 里的生成逻辑不动）。
3. 把 `main_api` 的 `outline_client.py` / `content_client.py` 换成 A2A Client（接口签名不变，`main.py` 无需改动）。
4. 用 `simpleOutline/a2a_client.py` 与 `slide_agent` 的测试客户端做本地联调。

## 五、兼容性提示

- 内容生成用 `StreamingMode.NONE`（LLM 非流式，避免 JSON 粘连），Agent 级别仍走 SSE。
- 大纲生成用 `StreamingMode.SSE`。
- 若暂时不想改 A2A，当前 HTTP 直连版本可继续使用，接口与数据格式完全一致。
