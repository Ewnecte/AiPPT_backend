# 多 Agent PPT 生成 · 使用与评估指南（B + E）

本目录（`backend/multi_agent/`）实现了多 Agent PPT 生成的核心能力：**工具白名单与参数强校验、循环熔断、任务级评估、配图内容安全与版权说明、单/多 Agent 对比实验**，并配套一个前端 **token 看板**（`/agent`，顶栏「多Agent」）。

---

## 0. 快速开始

```bash
cd backend

# ① 演示桥段：反复重写大纲 → 熔断 + 部分结果（离线、零成本、秒级）
python -m multi_agent.demo_breaker

# ③ 任务级评估：50 个任务（离线确定性；加 --mode real 走真实 LLM）
python -m multi_agent.evaluate --tasks 50

# ⑤ 单 Agent vs 多 Agent 三维对比
python -m multi_agent.ab_compare --tasks 5

# 前端 token 看板：重启网关后访问 http://127.0.0.1:5173/agent
python start_backend.py        # 或单独重启 main_api（:6800）以加载新接口
```

> 说明：`main_api` 新增了 `/tools/agent_run`（SSE）、`/tools/agent_info`、`/tools/agent_files`，
> **必须重启 main_api** 才会生效。

---

## 1. ① 工具白名单 + 参数 Schema 校验

实现：`multi_agent/tool_registry.py`

- 白名单**只有 4 个工具**：`outline_generate`（大纲生成）、`copy_generate`（文案生成）、`image_search`（配图检索）、`write_file`（写入文件）；其余工具名一律拒绝（`tool_not_allowed`）。
- 参数用 **JSON Schema 强校验**（自实现子集校验器，含 `type/required/properties/additionalProperties/enum/pattern/minLength/maximum/items/minItems…`），校验不通过直接拒绝（`schema_invalid`），**不会进入执行阶段**。
- **写文件沙箱**：`write_file` 的路径必须落在 `backend/agent_sandbox/` 内，多重防护：
  绝对路径（`path_absolute`）、`..` 穿越（`path_traversal`）、解析后越界（`path_out_of_sandbox`）、
  扩展名白名单 `.md/.txt/.json/.csv`（`ext_not_allowed`）、文件大小上限（默认 2MB）。
- 前端 `/agent` 页面可直接查看白名单与 Schema（`GET /tools/agent_info`）。

自测（应全部被拒 / 1 条通过）：

| 调用 | 结果 |
| --- | --- |
| `browser_open` | `tool_not_allowed` |
| `write_file path=../../etc/passwd.md` | `path_traversal` |
| `write_file path=C:/Windows/evil.md` | `path_absolute` |
| `write_file path=ok.exe` | `ext_not_allowed` |
| `write_file` 带未允许字段 | `schema_invalid` |
| `outline_generate topic="A"` | `schema_invalid`（长度不足） |
| `image_search query="血腥 暴力 战争"` | `image_query_blocked`（内容安全） |
| `write_file path=ok/note.md` | ✅ 通过 |

## 2. ② 循环熔断

实现：`multi_agent/orchestrator.py`

| 限制 | 默认值 | 环境变量 |
| --- | --- | --- |
| 最大步数 | 10 | `AGENT_MAX_STEPS` |
| token 预算 | 40000 | `AGENT_MAX_TOKENS` |
| 单任务超时 | 180s | `AGENT_TIMEOUT_S` |
| 循环检测阈值（同一「工具+参数」重复次数） | 2 | `AGENT_MAX_REPEAT` |

- 每步开始前检查步数 / token / 超时；单步执行还受「剩余超时」约束（`asyncio.wait_for`）。
- **循环检测**：同一 `(工具, 参数)` 重复出现超过阈值 → 判定「原地打转」并熔断（典型：Agent 反复重写大纲）。
- 熔断后**不再消耗 token**，并把已完成部分（大纲 / 文案 / 配图 / 已落盘文件 / 成稿结构校验）一并返回。

## 3. ③ 任务级评估

实现：`multi_agent/evaluate.py`（50 个任务 = 20 个行业 × 变体，确定性可复现）

指标：任务完成率、异常率、PPT 可正常打开率、页数/结构合规率、平均 token、平均耗时、P95 耗时、平均成本（元/份）、自动质量分。

- 「可正常打开」= deck 可解析、每页 `type` 合法、`data` 结构合法（前端契约可直接渲染）；
- 「结构合规」= 封面在首页、有结束页、有目录与内容页、页数落在 [6, 30]。

**离线 50 任务实测（fake 模式）**：完成率 **100%**、异常率 **0%**、可打开 **100%**、结构合规 **100%**、
平均 token **8,108**、平均耗时 **0.006s**、平均成本 **¥0.0087/份**、自动质量分 **87.0**。
报告见 `multi_agent/reports/eval_*.md`（含逐任务明细）。

> 真实 LLM 模式：`--mode real`（会真实调用模型，成本/耗时以实测为准，建议 `--limit` 先冒烟）。

## 4. ④ 图像内容安全 + 版权来源说明

实现：`multi_agent/image_safety.py`（+ `tools_image.py` 取图）

- **两道审核**：检索词先审（`moderate_query`），取回的图片再按「来源白名单 + 元数据风险词 + URL 协议」审（`moderate_image`）；命中即拦截，不进入 PPT，并记录拦截原因。
- 风险类别：violence / adult / hate / illegal / horror（词表可扩展）。
- **版权来源**：每张入库图片生成 `attribution`（标题、来源、作者、许可证、许可链接），并汇总为「图片来源说明」写入沙箱 `image_sources.md`，同时作为成稿的**参考资料页**（`reference`）呈现。
  - Pexels → `Pexels License（可免费商用，建议署名）`
  - picsum 占位图 → 标注为「演示用占位图，请替换为正式素材」

## 5. ⑤ 单 Agent vs 多 Agent 对比实验

实现：`multi_agent/ab_compare.py`

- **单 Agent（基线）**：一次 LLM 调用直接产出大纲，无工具编排、无分章文案与配图；
- **多 Agent（本方案）**：Planner 调度白名单工具（大纲 → 文案 → 配图 → 写文件）+ 熔断保护。

输出三维对比表（质量 / 耗时 / 成本），其中「质量」含**自动启发式分**与**人工评分列（评审后回填 1~10）**。
报告见 `multi_agent/reports/ab_*.md`。

离线冒烟（2 个任务）实测：自动质量 87.0（多） vs 85.0（单）；成本 ×31（元/份 ¥0.00869 vs ¥0.00028）。
真实模式下单 Agent 的 token 占比会显著上升，请以 `--mode real` 的实测报告为准。

## 6. 演示桥段（评委现场）

1. 打开前端 `/agent` 页面（顶栏「多Agent」）；
2. 点「熔断演示」→「开始运行」：
   - 执行轨迹里第 3 次重复同一 `outline_generate` 时出现 `🔁 循环检测`；
   - 随即 `⛔ 熔断`，token 进度条**停止增长**（看板显示最终 token，不再上涨）；
   - 右侧「部分结果」仍给出大纲字数、沙箱落盘文件、结构校验（可打开 / 页数）；
3. 点「正常生成」→ 可看到四类工具依次被调用（大纲 → 文案 ×3 → 配图 → 写文件），
   配图区展示图片与**版权来源说明**，沙箱产物区列出落盘文件；
4. 命令行版演示：`python -m multi_agent.demo_breaker`（输出每一步 token 与熔断原因）。

## 7. 环境变量一览

```ini
AGENT_MAX_STEPS=10          # 最大步数
AGENT_MAX_TOKENS=40000      # token 预算
AGENT_TIMEOUT_S=180         # 单任务超时（秒）
AGENT_MAX_REPEAT=2          # 同一工具+参数允许重复次数
AGENT_SANDBOX_DIR=          # 沙箱目录（默认 backend/agent_sandbox）
AGENT_MAX_FILE_BYTES=2000000# 单文件写入上限
PRICE_INPUT_PER_1K=0.001    # 成本核算：输入 token 单价（元/千）
PRICE_OUTPUT_PER_1K=0.002   # 成本核算：输出 token 单价（元/千）
```

## 8. 核心指标达标情况（离线基线）

| 指标 | 目标 | 实测（fake 50 任务） | 结论 |
| --- | --- | --- | --- |
| 任务完成率 | > 85% | 100% | ✅ |
| 异常率 | < 5% | 0% | ✅ |
| 平均成本 | 元/份 | ¥0.0087 | ✅（成本可控） |

> 真实 LLM 模式下请以 `--mode real` 的报告复测上述三项；熔断与白名单/安全审核逻辑与模式无关，均为强制生效。
