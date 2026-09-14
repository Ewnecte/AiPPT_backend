"""② 多 Agent 编排 + 循环熔断。

角色（Agent 化）：
  Planner Agent     读任务与历史，决定下一步调用哪个白名单工具（或 finish）
  Outline Agent     工具 outline_generate 背后的执行者（生成大纲）
  Copy Agent        工具 copy_generate 背后的执行者（生成文案）
  Image Agent       工具 image_search 背后的执行者（检索 + 内容安全审核 + 版权说明）
  File Agent        工具 write_file 背后的执行者（沙箱落盘）

熔断（超限强制终止并返回已完成部分）：
  - 最大步数 max_steps（默认 10）
  - 最大 token 预算 max_tokens（默认取 AGENT_MAX_TOKENS，40000）
  - 单任务超时 timeout_s（默认 180 秒）
  - 循环检测：同一 (工具, 参数) 重复出现即判定「原地打转」（如反复重写大纲）并熔断
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from . import tool_registry as tr
from .deck_validate import build_deck, validate_deck
from .llm import FakeLLM, LLMClient, Usage

DEFAULT_MAX_STEPS = int(os.getenv("AGENT_MAX_STEPS", "10"))
DEFAULT_MAX_TOKENS = int(os.getenv("AGENT_MAX_TOKENS", "40000"))
DEFAULT_TIMEOUT_S = float(os.getenv("AGENT_TIMEOUT_S", "180"))
MAX_REPEAT_SAME_CALL = int(os.getenv("AGENT_MAX_REPEAT", "2"))


@dataclass
class Limits:
    max_steps: int = DEFAULT_MAX_STEPS
    max_tokens: int = DEFAULT_MAX_TOKENS
    timeout_s: float = DEFAULT_TIMEOUT_S
    max_repeat: int = MAX_REPEAT_SAME_CALL

    def as_dict(self) -> dict:
        return {
            "max_steps": self.max_steps,
            "max_tokens": self.max_tokens,
            "timeout_s": self.timeout_s,
            "max_repeat": self.max_repeat,
        }


@dataclass
class StepRecord:
    n: int
    tool: str
    args: dict
    ok: bool
    elapsed: float
    tokens_after: int
    error: dict | None = None
    summary: str = ""

    def as_dict(self) -> dict:
        return {
            "step": self.n,
            "tool": self.tool,
            "args": self.args,
            "ok": self.ok,
            "elapsed": round(self.elapsed, 3),
            "tokens_after": self.tokens_after,
            "error": self.error,
            "summary": self.summary,
        }


@dataclass
class RunResult:
    task: str
    status: str  # completed | breaker | error
    reason: str
    steps: list[StepRecord] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    elapsed: float = 0.0
    partial: dict = field(default_factory=dict)
    events: list[dict] = field(default_factory=list)
    limits: Limits = field(default_factory=Limits)
    agent_calls: dict[str, int] = field(default_factory=dict)

    @property
    def partial_returned(self) -> bool:
        return self.status == "breaker"

    def as_dict(self) -> dict:
        return {
            "task": self.task,
            "status": self.status,
            "reason": self.reason,
            "limits": self.limits.as_dict(),
            "steps": [s.as_dict() for s in self.steps],
            "usage": self.usage.as_dict(),
            "elapsed": round(self.elapsed, 3),
            "partial": self.partial,
            "agent_calls": self.agent_calls,
        }


class MultiAgentOrchestrator:
    """多 Agent 编排器：Planner 决策 + 白名单工具执行 + 熔断保护。"""

    def __init__(
        self,
        task: str,
        *,
        llm: Any | None = None,
        limits: Limits | None = None,
        on_event: Callable[[dict], Any] | None = None,
        sandbox_prefix: str = "runs",
    ):
        self.task = task
        self.llm = llm or LLMClient()
        self.limits = limits or Limits()
        self.on_event = on_event
        self.sandbox_prefix = sandbox_prefix.strip("/") or "runs"

        self.usage = Usage()
        self.steps: list[StepRecord] = []
        self.events: list[dict] = []
        self.agent_calls: dict[str, int] = {}

        # 部分结果（熔断时也要能返回）
        self.outline: str = ""
        self.copies: dict[str, str] = {}
        self.images: list[dict] = []
        self.files: list[dict] = []
        self.attribution: list[str] = []
        self._call_counts: dict[str, int] = {}
        self._t0 = time.monotonic()

    # ------------------------------------------------------------ 事件
    async def _emit(self, type_: str, **payload: Any) -> None:
        ev = {"type": type_, "ts": round(time.monotonic() - self._t0, 3), **payload}
        self.events.append(ev)
        if self.on_event:
            out = self.on_event(ev)
            if hasattr(out, "__await__"):
                await out

    def _tokens(self) -> int:
        return self.usage.total_tokens

    def _elapsed(self) -> float:
        return time.monotonic() - self._t0

    # ------------------------------------------------------------ Planner
    async def _plan(self) -> dict:
        history = "\n".join(
            f"  {s.n}. {s.tool}({json.dumps(s.args, ensure_ascii=False)[:120]}) -> "
            f"{'OK' if s.ok else 'ERR'} {s.summary[:80]}"
            for s in self.steps[-6:]
        ) or "  （还没有执行任何工具）"
        remaining_steps = max(0, self.limits.max_steps - len(self.steps))
        remaining_tokens = max(0, self.limits.max_tokens - self._tokens())
        sys = (
            "你是 PPT 生成任务的多 Agent 调度器（Planner）。你只能从下面的工具白名单中选择工具，"
            "参数必须严格符合 JSON Schema。当你认为任务已经可以交付时，返回 tool=finish。\n"
            "输出必须是单个 JSON 对象：{\"thought\": \"...\", \"tool\": \"<工具名|finish>\", \"args\": {...}}\n\n"
            f"可用工具：\n{tr.tool_catalog_text()}"
        )
        user = (
            f"任务：{self.task}\n\n"
            f"已完成步骤：\n{history}\n\n"
            f"剩余步数预算：{remaining_steps}，剩余 token 预算：{remaining_tokens}\n\n"
            "请决定下一步。若大纲还没有生成，先调用 outline_generate；"
            "随后可对每个一级章节调用 copy_generate，再为需要配图的章节调用 image_search，"
            "最后用 write_file 把大纲/文案/来源说明写入沙箱。"
        )
        text = await self.llm.chat(
            [{"role": "system", "content": sys}, {"role": "user", "content": user}],
            agent="planner",
            usage=self.usage,
            json_mode=True,
        )
        self.agent_calls["planner"] = self.agent_calls.get("planner", 0) + 1
        return self._parse_decision(text)

    @staticmethod
    def _parse_decision(text: str) -> dict:
        raw = text.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```[a-zA-Z]*\n?|```$", "", raw).strip()
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict) and ("tool" in obj or "args" in obj):
                return obj
        except Exception:  # noqa: BLE001
            pass
        m = re.search(r"\{.*\}", raw, re.S)
        if m:
            try:
                obj = json.loads(m.group(0))
                if isinstance(obj, dict):
                    return obj
            except Exception:  # noqa: BLE001
                pass
        return {"tool": "", "args": {}, "thought": "decision_parse_failed"}

    # ------------------------------------------------------------ 主循环
    async def run(self) -> RunResult:
        await self._emit("start", task=self.task, limits=self.limits.as_dict(), tools=sorted(tr.WHITELIST))

        status, reason = "completed", "planner_finish"
        try:
            while True:
                # ---- 熔断检查（步数 / token / 超时）
                if len(self.steps) >= self.limits.max_steps:
                    status, reason = "breaker", f"达到最大步数 {self.limits.max_steps}"
                    break
                if self._tokens() >= self.limits.max_tokens:
                    status, reason = "breaker", f"达到 token 预算 {self.limits.max_tokens}"
                    break
                if self._elapsed() >= self.limits.timeout_s:
                    status, reason = "breaker", f"达到单任务超时 {self.limits.timeout_s}s"
                    break

                decision = await self._plan()
                tool = str(decision.get("tool") or "")
                args = decision.get("args") or {}
                await self._emit("plan", thought=str(decision.get("thought") or "")[:300], tool=tool, args=args)

                if tool in ("finish", "done", ""):
                    if not tool:
                        status, reason = "breaker", "Planner 输出无法解析（安全终止）"
                    break

                # ---- 循环检测：同一工具+参数重复出现 → 原地打转，熔断
                sig = f"{tool}:{hashlib.md5(json.dumps(args, sort_keys=True, ensure_ascii=False).encode()).hexdigest()}"
                self._call_counts[sig] = self._call_counts.get(sig, 0) + 1
                if self._call_counts[sig] > self.limits.max_repeat:
                    status, reason = "breaker", f"检测到循环调用（{tool} 以相同参数重复 {self._call_counts[sig]} 次）"
                    await self._emit(
                        "loop_detected", tool=tool, repeat=self._call_counts[sig], args=args
                    )
                    break

                # ---- 执行工具（受剩余超时约束）
                remaining = max(0.1, self.limits.timeout_s - self._elapsed())
                t_step = time.monotonic()
                error: dict | None = None
                summary = ""
                ok = False
                try:
                    result = await asyncio.wait_for(tr.call_tool(tool, args, {"llm": self.llm, "usage": self.usage}), timeout=remaining)
                    ok = True
                    summary = self._absorb(result)
                except asyncio.TimeoutError:
                    error = {"code": "step_timeout", "message": f"单步执行超过剩余超时预算（{remaining:.1f}s）"}
                except tr.ToolError as e:
                    error = e.as_dict()["error"]
                except Exception as e:  # noqa: BLE001
                    error = {"code": "tool_exception", "message": f"{type(e).__name__}: {e}"}

                rec = StepRecord(
                    n=len(self.steps) + 1,
                    tool=tool,
                    args=args,
                    ok=ok,
                    elapsed=time.monotonic() - t_step,
                    tokens_after=self._tokens(),
                    error=error,
                    summary=summary,
                )
                self.steps.append(rec)
                await self._emit(
                    "step",
                    step=rec.n,
                    tool=tool,
                    ok=ok,
                    args=args,
                    summary=summary,
                    error=error,
                    elapsed=round(rec.elapsed, 3),
                    tokens=self._tokens(),
                    cost_yuan=self.usage.cost,
                )
                if error:
                    await self._emit("tool_error", step=rec.n, tool=tool, error=error)
        except Exception as e:  # noqa: BLE001 —— 任何未预期异常也返回部分结果
            status, reason = "error", f"{type(e).__name__}: {e}"

        # ---- 收尾：无论完成还是熔断，都返回/落盘“已完成部分”
        partial = await self._finalize(status, reason)
        if status == "breaker":
            await self._emit(
                "breaker",
                reason=reason,
                steps=len(self.steps),
                tokens=self._tokens(),
                elapsed=round(self._elapsed(), 3),
                partial_returned=True,
            )
        result = RunResult(
            task=self.task,
            status=status,
            reason=reason,
            steps=self.steps,
            usage=self.usage,
            elapsed=self._elapsed(),
            partial=partial,
            events=list(self.events),
            limits=self.limits,
            agent_calls=self.agent_calls,
        )
        await self._emit("done", status=status, reason=reason, tokens=self._tokens(), elapsed=round(result.elapsed, 3), usage=self.usage.as_dict())
        return result

    # ------------------------------------------------------------ 结果吸收
    def _absorb(self, result: dict) -> str:
        tool = result.get("tool", "")
        if tool == "outline_generate":
            self.outline = result.get("outline", "")
            return f"大纲 {result.get('chars', len(self.outline))} 字"
        if tool == "copy_generate":
            sec = result.get("section", "")
            self.copies[sec] = result.get("copy", "")
            return f"文案 {sec[:24]}（{len(self.copies[sec])} 字）"
        if tool == "image_search":
            imgs = result.get("images", [])
            self.images.extend(imgs)
            self.attribution = result.get("attribution", []) or self.attribution
            blocked = len(result.get("blocked", []))
            return f"配图 {len(imgs)} 张（拦截 {blocked} 张）"
        if tool == "write_file":
            self.files.append({"path": result.get("path"), "bytes": result.get("bytes"), "sha256": result.get("sha256")})
            return f"写入沙箱 {result.get('path')}"
        return "ok"

    async def _finalize(self, status: str, reason: str) -> dict:
        """组装成稿 + 结构校验 + 把产物写入沙箱（部分结果同样落盘）。"""
        deck: list[dict] = []
        validation: dict = {}
        if self.outline or self.copies:
            deck = build_deck(self.outline, self.copies, self.images, self.attribution)
            validation = validate_deck(deck)

        prefix = self.sandbox_prefix
        artifacts = []
        if self.outline:
            artifacts.append((f"{prefix}/outline.md", self.outline))
        if self.copies:
            body = "\n\n".join(f"## {k}\n{v}" for k, v in self.copies.items())
            artifacts.append((f"{prefix}/copy.md", body))
        if self.attribution:
            artifacts.append((f"{prefix}/image_sources.md", "# 图片来源说明\n\n" + "\n".join(self.attribution)))
        if deck:
            artifacts.append((f"{prefix}/deck.json", json.dumps(deck, ensure_ascii=False, indent=2)))
        for path, content in artifacts:
            try:
                res = await tr.call_tool("write_file", {"path": path, "content": content, "mode": "overwrite"}, {"llm": self.llm, "usage": self.usage})
                self.files.append({"path": res["path"], "bytes": res["bytes"], "sha256": res["sha256"]})
                await self._emit("artifact", path=res["path"], bytes=res["bytes"])
            except tr.ToolError as e:
                await self._emit("artifact_error", path=path, error=e.as_dict()["error"])

        return {
            "outline": self.outline,
            "copies": self.copies,
            "images": self.images,
            "attribution": self.attribution,
            "files": self.files,
            "deck": deck,
            "validation": validation,
            "partial_returned": status == "breaker",
            "breaker_reason": reason if status == "breaker" else "",
        }


async def run_task(task: str, *, mode: str = "auto", on_event=None, limits: Limits | None = None,
                   script: list[dict] | None = None) -> RunResult:
    """便捷入口：mode=real 用真实 LLM；mode=fake 用离线脚本化 LLM；auto 有 Key 用 real。"""
    if mode == "fake":
        llm = FakeLLM(script=script)
    elif mode == "real":
        llm = LLMClient()
    else:
        llm = LLMClient() if os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY") else FakeLLM(script=script)
    orch = MultiAgentOrchestrator(task, llm=llm, limits=limits, on_event=on_event)
    return await orch.run()
