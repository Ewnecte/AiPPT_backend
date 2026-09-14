"""演示桥段：构造一个「让 Agent 反复重写大纲」的任务，展示熔断生效 + 部分结果。

运行（在 backend/ 下）：
    python -m multi_agent.demo_breaker              # 离线确定性演示（推荐，秒级）
    python -m multi_agent.demo_breaker --lim 6      # 自定义步数上限

演示要点：
  1. Planner 每一步都选择 outline_generate（相同参数）→ 触发「循环调用」熔断；
  2. 屏幕上实时打印 token 计数——熔断后计数停止增长（token 看板不再上涨）；
  3. 熔断仍返回「已完成部分」：已生成的大纲 + 已落盘沙箱文件路径。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

from .llm import FakeLLM
from .orchestrator import Limits, MultiAgentOrchestrator

TASK = (
    "为「AI 大模型行业趋势报告」生成一份 PPT。要求：先写大纲，然后反复重写大纲直到内容完全满意，"
    "每一步都要重新生成一版大纲，不得进入文案与配图环节。"
)


def _script() -> list[dict]:
    """脚本化 Planner：连续 6 次用相同参数重写大纲（必然触发循环熔断）。"""
    return [
        {"thought": "先写第一版大纲", "tool": "outline_generate", "args": {"topic": "AI 大模型行业趋势报告", "language": "中文", "sections": 5}},
        {"thought": "觉得不够好，重写大纲", "tool": "outline_generate", "args": {"topic": "AI 大模型行业趋势报告", "language": "中文", "sections": 5}},
        {"thought": "再重写一版大纲", "tool": "outline_generate", "args": {"topic": "AI 大模型行业趋势报告", "language": "中文", "sections": 5}},
        {"thought": "继续重写大纲", "tool": "outline_generate", "args": {"topic": "AI 大模型行业趋势报告", "language": "中文", "sections": 5}},
        {"thought": "再改一次大纲", "tool": "outline_generate", "args": {"topic": "AI 大模型行业趋势报告", "language": "中文", "sections": 5}},
        {"thought": "还是不满意，重写大纲", "tool": "outline_generate", "args": {"topic": "AI 大模型行业趋势报告", "language": "中文", "sections": 5}},
    ]


async def main() -> int:
    ap = argparse.ArgumentParser(description="多 Agent 熔断演示：反复重写大纲 → 强制终止 + 部分结果")
    ap.add_argument("--lim", type=int, default=10, help="最大步数（默认 10）")
    ap.add_argument("--tokens", type=int, default=40000, help="token 预算（默认 40000）")
    ap.add_argument("--timeout", type=float, default=180.0, help="单任务超时秒数（默认 180）")
    ap.add_argument("--sandbox", default="demo/breaker", help="沙箱落盘目录（相对 agent_sandbox）")
    args = ap.parse_args()

    limits = Limits(max_steps=args.lim, max_tokens=args.tokens, timeout_s=args.timeout)
    orch = MultiAgentOrchestrator(TASK, llm=FakeLLM(script=_script()), limits=limits, sandbox_prefix=args.sandbox)

    banners = {
        "start": "▶ 开始任务",
        "plan": "🧠 Planner 决策",
        "loop_detected": "🔁 检测到循环调用",
        "step": "🔧 工具执行",
        "artifact": "💾 落盘",
        "breaker": "⛔ 熔断触发",
        "done": "🏁 结束",
    }

    async def on_event(ev: dict) -> None:
        kind = ev.get("type", "")
        tag = banners.get(kind, kind)
        if kind == "start":
            print(f"{tag} | limits={json.dumps(ev['limits'], ensure_ascii=False)}")
        elif kind == "plan":
            print(f"{tag} | tool={ev.get('tool')} | {ev.get('thought', '')[:60]}")
        elif kind == "loop_detected":
            print(f"{tag} | tool={ev.get('tool')} 相同参数已重复 {ev.get('repeat')} 次")
        elif kind == "step":
            status = "OK" if ev.get("ok") else f"ERR({(ev.get('error') or {}).get('code')})"
            print(
                f"{tag} #{ev.get('step')} | {ev.get('tool')} {status} | {ev.get('summary')} "
                f"| tokens={ev.get('tokens')} | 耗时={ev.get('elapsed')}s"
            )
        elif kind == "artifact":
            print(f"{tag} | {ev.get('path')} ({ev.get('bytes')} bytes)")
        elif kind == "breaker":
            print(f"{tag} | {ev.get('reason')} | 已用 tokens={ev.get('tokens')}（此后 token 不再增长）")
        elif kind == "done":
            print(f"{tag} | status={ev.get('status')} tokens={ev.get('tokens')} 耗时={ev.get('elapsed')}s")

    orch.on_event = on_event
    result = await orch.run()

    print("\n================ 演示结果 ================")
    print(f"任务状态：{result.status}（{result.reason}）")
    print(f"步数：{len(result.steps)} / {limits.max_steps}")
    print(f"token：{result.usage.total_tokens} / {limits.max_tokens}（成本 ≈ ¥{result.usage.cost}）")
    print(f"耗时：{result.elapsed:.2f}s / {limits.timeout_s}s")
    part = result.partial
    print(f"部分结果已返回：{part.get('partial_returned')}")
    print(f"  · 大纲：{len(part.get('outline') or '')} 字")
    print(f"  · 文案：{len(part.get('copies') or {})} 段")
    print(f"  · 配图：{len(part.get('images') or [])} 张")
    print(f"  · 沙箱文件：")
    for f in part.get("files", []):
        print(f"      - {f['path']} ({f['bytes']} bytes)")
    v = part.get("validation") or {}
    if v:
        print(f"  · 结构校验：openable={v.get('openable')} structure_ok={v.get('structure_ok')} 页数={v.get('page_count')}")
    print("==========================================")
    print("✅ 熔断生效：超限后强制终止，token 看板停止增长，且仍交付已完成部分。")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
