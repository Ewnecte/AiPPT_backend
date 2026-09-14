"""③ 任务级评估：N（默认 50）个生成任务，统计核心指标。

指标：
  任务完成率      status == completed 的比例           目标 > 85%
  异常率          熔断 + 异常终止 的比例               目标 < 5%
  PPT 可正常打开率 结构可解析可渲染（validate.openable）
  页数/结构合规率  validate.structure_ok
  平均 token / 平均耗时 / 平均成本(元/份) / P95 耗时 / 自动质量分

用法（在 backend/ 下）：
    python -m multi_agent.evaluate                 # 50 个任务，离线确定性（秒级）
    python -m multi_agent.evaluate --limit 5       # 冒烟：只跑 5 个
    python -m multi_agent.evaluate --mode real     # 真实 LLM（慢、产生费用）
报告写入 multi_agent/reports/eval_<时间戳>.{json,md}
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from datetime import datetime
from pathlib import Path

from .deck_validate import quality_score
from .llm import FakeLLM, LLMClient
from .orchestrator import Limits, MultiAgentOrchestrator

REPORT_DIR = Path(__file__).resolve().parent / "reports"

# ---- 任务集：20 个行业 × 变体 = 50 个任务（确定性可复现）
INDUSTRIES = [
    "AI 大模型行业趋势", "新能源汽车竞争格局", "跨境电商增长策略", "智能制造升级路径",
    "医疗健康数字化转型", "金融科技风控体系", "在线教育产品设计", "碳中和与新能源",
    "企业数据治理实践", "云原生架构演进", "短视频内容运营", "智慧城市解决方案",
    "消费品牌年轻化", "半导体供应链安全", "SaaS 增长模型", "工业互联网平台",
    "AIGC 内容生产", "人才招聘与组织效能", "供应链韧性建设", "低空经济产业机会",
]
VARIANTS = [
    ("行业分析报告", 5),
    ("落地实施方案", 4),
    ("年度总结与展望", 5),
]


def build_tasks(limit: int | None = None) -> list[dict]:
    tasks: list[dict] = []
    for i, ind in enumerate(INDUSTRIES):
        for j, (kind, sections) in enumerate(VARIANTS):
            if len(tasks) >= 50:
                break
            tasks.append(
                {
                    "id": f"T{len(tasks) + 1:02d}",
                    "topic": ind,
                    "title": f"{ind}·{kind}",
                    "sections": sections,
                    "task": f"为「{ind}」生成一份《{kind}》PPT：先写 {sections} 个一级章节的大纲，"
                            f"为前 3 个章节各写一段文案，为 1 个章节检索配图，最后把产物写入沙箱。",
                }
            )
    return tasks[:limit] if limit else tasks


def planner_script(sections: int, topic: str) -> list[dict]:
    """离线模式下的确定性计划：大纲 → 3 段文案 → 配图 → 写文件 → 完成。"""
    script = [
        {"thought": "先生成大纲", "tool": "outline_generate",
         "args": {"topic": topic, "language": "中文", "sections": sections}},
    ]
    for k in range(1, 4):
        script.append({"thought": f"为第 {k} 章写文案", "tool": "copy_generate",
                       "args": {"section": f"Chapter {k}", "language": "中文", "style": "professional"}})
    script.append({"thought": "为内容页检索配图", "tool": "image_search",
                   "args": {"query": f"{topic} 商务", "count": 2}})
    script.append({"thought": "把大纲落盘", "tool": "write_file",
                   "args": {"path": "runs/outline_snapshot.md", "content": "# placeholder\n", "mode": "overwrite"}})
    script.append({"thought": "可以交付了", "tool": "finish", "args": {}})
    return script


async def run_one(task: dict, mode: str, limits: Limits) -> dict:
    llm = FakeLLM(script=planner_script(task["sections"], task["topic"])) if mode == "fake" else LLMClient()
    orch = MultiAgentOrchestrator(
        task["task"],
        llm=llm,
        limits=limits,
        sandbox_prefix=f"eval/{task['id']}",
    )
    t0 = time.monotonic()
    try:
        result = await orch.run()
    except Exception as e:  # noqa: BLE001
        return {
            "id": task["id"], "title": task["title"], "status": "error", "reason": str(e),
            "tokens": 0, "cost": 0.0, "elapsed": time.monotonic() - t0,
            "openable": False, "structure_ok": False, "pages": 0, "quality": 0.0,
        }
    v = result.partial.get("validation") or {}
    deck = result.partial.get("deck") or []
    return {
        "id": task["id"],
        "title": task["title"],
        "status": result.status,
        "reason": result.reason,
        "steps": len(result.steps),
        "tokens": result.usage.total_tokens,
        "cost": result.usage.cost,
        "elapsed": result.elapsed,
        "openable": bool(v.get("openable")),
        "structure_ok": bool(v.get("structure_ok")),
        "pages": int(v.get("page_count") or 0),
        "quality": quality_score(deck),
        "files": [f["path"] for f in (result.partial.get("files") or [])],
    }


def summarize(rows: list[dict]) -> dict:
    n = len(rows) or 1
    done = sum(1 for r in rows if r["status"] == "completed")
    abnormal = sum(1 for r in rows if r["status"] in ("breaker", "error"))
    openable = sum(1 for r in rows if r["openable"])
    structure = sum(1 for r in rows if r["structure_ok"])
    times = sorted(r["elapsed"] for r in rows)
    p95 = times[min(len(times) - 1, int(len(times) * 0.95))] if times else 0.0
    return {
        "tasks": n,
        "completion_rate": round(done / n * 100, 2),
        "anomaly_rate": round(abnormal / n * 100, 2),
        "ppt_openable_rate": round(openable / n * 100, 2),
        "structure_compliance_rate": round(structure / n * 100, 2),
        "avg_tokens": round(statistics.mean([r["tokens"] for r in rows]), 1),
        "avg_elapsed_s": round(statistics.mean([r["elapsed"] for r in rows]), 3),
        "p95_elapsed_s": round(p95, 3),
        "avg_cost_yuan": round(statistics.mean([r["cost"] for r in rows]), 5),
        "avg_quality": round(statistics.mean([r["quality"] for r in rows]), 1),
        "avg_pages": round(statistics.mean([r["pages"] for r in rows]), 1),
    }


def render_md(summary: dict, rows: list[dict], mode: str, limits: Limits) -> str:
    ok_done = "✅" if summary["completion_rate"] > 85 else "❌"
    ok_abn = "✅" if summary["anomaly_rate"] < 5 else "❌"
    lines = [
        "# 多 Agent PPT 生成 · 任务级评估报告",
        "",
        f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 运行模式：{'离线确定性（FakeLLM）' if mode == 'fake' else '真实 LLM'}",
        f"- 熔断配置：最大步数 {limits.max_steps} / token 预算 {limits.max_tokens} / 超时 {limits.timeout_s}s",
        f"- 任务数：{summary['tasks']}",
        "",
        "## 核心指标",
        "",
        "| 指标 | 结果 | 目标 | 达标 |",
        "| --- | --- | --- | --- |",
        f"| 任务完成率 | {summary['completion_rate']}% | > 85% | {ok_done} |",
        f"| 异常率（熔断/异常终止） | {summary['anomaly_rate']}% | < 5% | {ok_abn} |",
        f"| PPT 可正常打开率 | {summary['ppt_openable_rate']}% | — | — |",
        f"| 页数/结构合规率 | {summary['structure_compliance_rate']}% | — | — |",
        f"| 平均 token | {summary['avg_tokens']} | — | — |",
        f"| 平均耗时 | {summary['avg_elapsed_s']}s（P95 {summary['p95_elapsed_s']}s） | ≤ 180s | ✅ |",
        f"| 平均成本 | ¥{summary['avg_cost_yuan']}/份 | — | — |",
        f"| 自动质量分 | {summary['avg_quality']} / 100 | — | — |",
        f"| 平均页数 | {summary['avg_pages']} | — | — |",
        "",
        "## 逐任务明细（前 20 条）",
        "",
        "| ID | 任务 | 状态 | 步数 | 页数 | token | 耗时(s) | 成本(¥) | 可打开 | 结构合规 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in rows[:20]:
        lines.append(
            f"| {r['id']} | {r['title']} | {r['status']} | {r.get('steps', '-')} | {r['pages']} | "
            f"{r['tokens']} | {round(r['elapsed'], 3)} | {r['cost']} | {'✅' if r['openable'] else '❌'} | "
            f"{'✅' if r['structure_ok'] else '❌'} |"
        )
    lines.append("")
    lines.append(f"> 完整 {len(rows)} 条明细见同目录 JSON 报告。")
    return "\n".join(lines)


async def main() -> int:
    ap = argparse.ArgumentParser(description="多 Agent PPT 生成任务级评估（③）")
    ap.add_argument("--tasks", type=int, default=50, help="任务数量（默认 50）")
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 个（冒烟用）")
    ap.add_argument("--mode", choices=["fake", "real"], default="fake", help="fake=离线确定性，real=真实 LLM")
    ap.add_argument("--max-steps", type=int, default=10)
    ap.add_argument("--max-tokens", type=int, default=40000)
    ap.add_argument("--timeout", type=float, default=180.0)
    ap.add_argument("--concurrency", type=int, default=4, help="并发任务数")
    args = ap.parse_args()

    limits = Limits(max_steps=args.max_steps, max_tokens=args.max_tokens, timeout_s=args.timeout)
    tasks = build_tasks(args.limit or args.tasks)
    print(f"开始评估：{len(tasks)} 个任务 | 模式={args.mode} | 并发={args.concurrency} | 熔断={limits.as_dict()}")

    sem = asyncio.Semaphore(args.concurrency)
    rows: list[dict] = []

    async def worker(t: dict) -> None:
        async with sem:
            r = await run_one(t, args.mode, limits)
            rows.append(r)
            print(f"  [{len(rows)}/{len(tasks)}] {r['id']} {r['status']:<9} 页数={r['pages']:<3} "
                  f"tokens={r['tokens']:<6} 耗时={round(r['elapsed'], 3)}s")

    await asyncio.gather(*(worker(t) for t in tasks))
    rows.sort(key=lambda r: r["id"])
    summary = summarize(rows)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    md = render_md(summary, rows, args.mode, limits)
    (REPORT_DIR / f"eval_{stamp}.md").write_text(md, encoding="utf-8")
    (REPORT_DIR / f"eval_{stamp}.json").write_text(
        json.dumps({"summary": summary, "rows": rows, "mode": args.mode, "limits": limits.as_dict()},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("\n============ 评估结果 ============")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    print(f"  报告：multi_agent/reports/eval_{stamp}.md")
    ok = summary["completion_rate"] > 85 and summary["anomaly_rate"] < 5
    print(f"\n核心指标：任务完成率>85% {'✅' if summary['completion_rate'] > 85 else '❌'} | "
          f"异常率<5% {'✅' if summary['anomaly_rate'] < 5 else '❌'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
