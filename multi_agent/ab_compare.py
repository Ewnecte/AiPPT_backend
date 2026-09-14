"""⑤ 单 Agent vs 多 Agent 对比实验（质量 / 耗时 / token 成本 三维对比）。

对照设计：
  单 Agent（baseline）：一次 LLM 调用直接产出整份 PPT 大纲，不经过工具编排、
                        不含分章文案与配图，装配为 deck 后评估。
  多 Agent（本方案）  ：Planner 调度白名单工具（大纲/文案/配图/写文件）+ 熔断保护，
                        产物经同一装配器与校验器评估。

三维对比：
  质量：自动启发式分（0~100，结构/页数/内容密度）+ 人工评分列（评审后填写 1~10）
  耗时：平均单份耗时（秒）
  成本：平均单份 token 数与人民币成本（元/份）

用法（在 backend/ 下）：
    python -m multi_agent.ab_compare                # 5 个任务，离线确定性
    python -m multi_agent.ab_compare --tasks 10 --mode real
报告写入 multi_agent/reports/ab_<时间戳>.{json,md}
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from datetime import datetime
from pathlib import Path

from .deck_validate import build_deck, quality_score, validate_deck
from .evaluate import build_tasks, planner_script
from .llm import FakeLLM, LLMClient, Usage
from .orchestrator import Limits, MultiAgentOrchestrator

REPORT_DIR = Path(__file__).resolve().parent / "reports"

SINGLE_SYSTEM = (
    "你是一次性完成整份 PPT 的助手：直接输出 Markdown 大纲（# 标题 / ## 一级 / ### 二级 / - 要点），"
    "不调用任何工具、不分步生成文案与配图。只输出大纲本身。"
)


async def run_single(task: dict, mode: str) -> dict:
    """单 Agent 基线：一次 LLM 调用产出大纲 → 装配 deck。"""
    usage = Usage()
    llm = FakeLLM() if mode == "fake" else LLMClient()
    t0 = time.monotonic()
    try:
        outline = await llm.chat(
            [{"role": "system", "content": SINGLE_SYSTEM},
             {"role": "user", "content": f"语言：中文\n主题：{task['topic']}（{task['title']}）"}],
            agent="outline",
            usage=usage,
        )
        deck = build_deck(outline, {}, [], [])
        v = validate_deck(deck)
        status = "completed" if v["openable"] else "error"
    except Exception as e:  # noqa: BLE001
        outline, deck, v, status = "", [], {"openable": False, "structure_ok": False, "page_count": 0}, "error"
        print(f"  单 Agent 异常：{e}")
    return {
        "id": task["id"], "title": task["title"], "status": status,
        "tokens": usage.total_tokens, "cost": usage.cost,
        "elapsed": time.monotonic() - t0,
        "pages": int(v.get("page_count") or 0),
        "openable": bool(v.get("openable")),
        "structure_ok": bool(v.get("structure_ok")),
        "quality": quality_score(deck),
    }


async def run_multi(task: dict, mode: str, limits: Limits) -> dict:
    """多 Agent：编排器 + 白名单工具 + 熔断。"""
    llm = FakeLLM(script=planner_script(task["sections"], task["topic"])) if mode == "fake" else LLMClient()
    orch = MultiAgentOrchestrator(task["task"], llm=llm, limits=limits, sandbox_prefix=f"ab/{task['id']}")
    t0 = time.monotonic()
    try:
        res = await orch.run()
    except Exception as e:  # noqa: BLE001
        return {"id": task["id"], "title": task["title"], "status": "error", "tokens": 0, "cost": 0.0,
                "elapsed": time.monotonic() - t0, "pages": 0, "openable": False, "structure_ok": False,
                "quality": 0.0, "reason": str(e)}
    v = res.partial.get("validation") or {}
    deck = res.partial.get("deck") or []
    return {
        "id": task["id"], "title": task["title"], "status": res.status,
        "tokens": res.usage.total_tokens, "cost": res.usage.cost,
        "elapsed": res.elapsed,
        "pages": int(v.get("page_count") or 0),
        "openable": bool(v.get("openable")),
        "structure_ok": bool(v.get("structure_ok")),
        "quality": quality_score(deck),
        "steps": len(res.steps),
    }


def agg(rows: list[dict]) -> dict:
    n = len(rows) or 1
    return {
        "tasks": n,
        "completion_rate": round(sum(1 for r in rows if r["status"] == "completed") / n * 100, 2),
        "quality_auto": round(statistics.mean([r["quality"] for r in rows]), 1),
        "avg_elapsed_s": round(statistics.mean([r["elapsed"] for r in rows]), 3),
        "avg_tokens": round(statistics.mean([r["tokens"] for r in rows]), 1),
        "avg_cost_yuan": round(statistics.mean([r["cost"] for r in rows]), 5),
        "avg_pages": round(statistics.mean([r["pages"] for r in rows]), 1),
        "openable_rate": round(sum(1 for r in rows if r["openable"]) / n * 100, 2),
    }


def render_md(single: dict, multi: dict, mode: str, limits: Limits, tasks: list[dict]) -> str:
    ratio_time = (multi["avg_elapsed_s"] / single["avg_elapsed_s"]) if single["avg_elapsed_s"] else 0
    ratio_cost = (multi["avg_cost_yuan"] / single["avg_cost_yuan"]) if single["avg_cost_yuan"] else 0
    return "\n".join([
        "# 单 Agent vs 多 Agent · 三维对比实验报告",
        "",
        f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 运行模式：{'离线确定性（FakeLLM）' if mode == 'fake' else '真实 LLM'}",
        f"- 任务数：{len(tasks)}（{'、'.join(t['id'] for t in tasks[:10])}{'…' if len(tasks) > 10 else ''}）",
        f"- 多 Agent 熔断配置：最大步数 {limits.max_steps} / token 预算 {limits.max_tokens} / 超时 {limits.timeout_s}s",
        "",
        "## 三维对比",
        "",
        "| 维度 | 单 Agent（基线） | 多 Agent（本方案） | 差异 |",
        "| --- | --- | --- | --- |",
        "| 质量：人工评分（1~10，评审填写） | 待填写 | 待填写 | — |",
        f"| 质量：自动启发式（0~100） | {single['quality_auto']} | {multi['quality_auto']} | {round(multi['quality_auto'] - single['quality_auto'], 1):+} |",
        f"| 耗时：平均单份（s） | {single['avg_elapsed_s']} | {multi['avg_elapsed_s']} | ×{round(ratio_time, 2)} |",
        f"| 成本：平均 token/份 | {single['avg_tokens']} | {multi['avg_tokens']} | ×{round(multi['avg_tokens'] / (single['avg_tokens'] or 1), 2)} |",
        f"| 成本：平均费用（元/份） | ¥{single['avg_cost_yuan']} | ¥{multi['avg_cost_yuan']} | ×{round(ratio_cost, 2)} |",
        f"| 任务完成率 | {single['completion_rate']}% | {multi['completion_rate']}% | — |",
        f"| PPT 可正常打开率 | {single['openable_rate']}% | {multi['openable_rate']}% | — |",
        f"| 平均页数 | {single['avg_pages']} | {multi['avg_pages']} | — |",
        "",
        "## 结论（自动部分）",
        "",
        f"- 质量：多 Agent 自动分 {multi['quality_auto']} vs 单 Agent {single['quality_auto']}（多 Agent 含分章文案与配图，内容密度更高）；",
        f"- 耗时：多 Agent 为单 Agent 的 ×{round(ratio_time, 2)}（多次 LLM 调用换取质量与可追溯性）；",
        f"- 成本：多 Agent 为单 Agent 的 ×{round(ratio_cost, 2)}（元/份 ¥{multi['avg_cost_yuan']} vs ¥{single['avg_cost_yuan']}）。",
        "",
        "> 人工评分请由评审同学按 1~10 打分后回填上表「人工评分」行，形成最终三维对比结论。",
    ])


async def main() -> int:
    ap = argparse.ArgumentParser(description="单 Agent vs 多 Agent 对比实验（⑤）")
    ap.add_argument("--tasks", type=int, default=5)
    ap.add_argument("--mode", choices=["fake", "real"], default="fake")
    ap.add_argument("--max-steps", type=int, default=10)
    ap.add_argument("--max-tokens", type=int, default=40000)
    ap.add_argument("--timeout", type=float, default=180.0)
    args = ap.parse_args()

    limits = Limits(max_steps=args.max_steps, max_tokens=args.max_tokens, timeout_s=args.timeout)
    tasks = build_tasks(args.tasks)
    print(f"对比实验：{len(tasks)} 个任务 | 模式={args.mode}")

    single_rows, multi_rows = [], []
    for t in tasks:
        s = await run_single(t, args.mode)
        m = await run_multi(t, args.mode, limits)
        single_rows.append(s)
        multi_rows.append(m)
        print(f"  {t['id']} 单Agent: 质量={s['quality']} 耗时={round(s['elapsed'], 3)}s tokens={s['tokens']} "
              f"| 多Agent: 质量={m['quality']} 耗时={round(m['elapsed'], 3)}s tokens={m['tokens']} 步数={m.get('steps')}")

    single, multi = agg(single_rows), agg(multi_rows)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    md = render_md(single, multi, args.mode, limits, tasks)
    (REPORT_DIR / f"ab_{stamp}.md").write_text(md, encoding="utf-8")
    (REPORT_DIR / f"ab_{stamp}.json").write_text(
        json.dumps({"single": single, "multi": multi, "single_rows": single_rows, "multi_rows": multi_rows,
                    "mode": args.mode, "limits": limits.as_dict()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("\n" + md)
    print(f"\n报告：multi_agent/reports/ab_{stamp}.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
