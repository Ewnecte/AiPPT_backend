"""① 工具白名单 + JSON Schema 参数强校验 + 沙箱写文件。

白名单：只允许四类工具
  outline_generate  大纲生成
  copy_generate     文案生成
  image_search      配图检索（含内容安全审核与版权来源标注）
  write_file        写入文件（路径必须落在沙箱目录内）

任何未在白名单内的工具名、或参数不符合 Schema，都会被拒绝并返回结构化错误，
不会进入执行阶段。写文件会做多重防护：相对路径、禁止 ..、禁止绝对路径、
解析后必须是沙箱目录的子路径、扩展名白名单、大小上限。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Callable

from . import image_safety

# ---------------------------------------------------------------- 沙箱
BACKEND_DIR = Path(__file__).resolve().parent.parent
SANDBOX_DIR = Path(os.getenv("AGENT_SANDBOX_DIR", str(BACKEND_DIR / "agent_sandbox"))).resolve()
ALLOWED_EXT = {".md", ".txt", ".json", ".csv"}
MAX_FILE_BYTES = int(os.getenv("AGENT_MAX_FILE_BYTES", "2000000"))


class ToolError(Exception):
    """工具调用错误基类。"""

    def __init__(self, code: str, message: str, detail: Any = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail

    def as_dict(self) -> dict:
        return {"ok": False, "error": {"code": self.code, "message": self.message, "detail": self.detail}}


class SchemaError(ToolError):
    def __init__(self, message: str, detail: Any = None):
        super().__init__("schema_invalid", message, detail)


# ---------------------------------------------------------------- JSON Schema（最小实现）
def _type_ok(value: Any, t: str) -> bool:
    if t == "object":
        return isinstance(value, dict)
    if t == "array":
        return isinstance(value, list)
    if t == "string":
        return isinstance(value, str)
    if t == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if t == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if t == "boolean":
        return isinstance(value, bool)
    if t == "null":
        return value is None
    return True


def validate_json_schema(value: Any, schema: dict, path: str = "$") -> None:
    """按子集 JSON Schema 强校验；不通过抛 SchemaError（含具体路径）。"""
    if not isinstance(schema, dict):
        return

    expected = schema.get("type")
    if expected:
        types = expected if isinstance(expected, list) else [expected]
        if not any(_type_ok(value, t) for t in types):
            raise SchemaError(f"{path} 类型错误：期望 {expected}，实际 {type(value).__name__}", {"path": path})

    if "enum" in schema and value not in schema["enum"]:
        raise SchemaError(f"{path} 取值不在允许集合 {schema['enum']} 内", {"path": path, "value": value})

    if "const" in schema and value != schema["const"]:
        raise SchemaError(f"{path} 必须等于 {schema['const']}", {"path": path})

    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            raise SchemaError(f"{path} 长度小于 {schema['minLength']}", {"path": path})
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            raise SchemaError(f"{path} 长度超过 {schema['maxLength']}", {"path": path})
        if "pattern" in schema and not re.search(schema["pattern"], value):
            raise SchemaError(f"{path} 不匹配模式 {schema['pattern']}", {"path": path})

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise SchemaError(f"{path} 小于最小值 {schema['minimum']}", {"path": path})
        if "maximum" in schema and value > schema["maximum"]:
            raise SchemaError(f"{path} 超过最大值 {schema['maximum']}", {"path": path})

    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            raise SchemaError(f"{path} 元素不足 {schema['minItems']}", {"path": path})
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            raise SchemaError(f"{path} 元素超过 {schema['maxItems']}", {"path": path})
        items = schema.get("items")
        if isinstance(items, dict):
            for i, v in enumerate(value):
                validate_json_schema(v, items, f"{path}[{i}]")

    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                raise SchemaError(f"{path} 缺少必填字段：{key}", {"path": path, "missing": key})
        props = schema.get("properties", {})
        for key, sub in props.items():
            if key in value:
                validate_json_schema(value[key], sub, f"{path}.{key}")
        if schema.get("additionalProperties") is False:
            extra = [k for k in value if k not in props]
            if extra:
                raise SchemaError(f"{path} 存在未允许的字段：{', '.join(extra)}", {"path": path, "extra": extra})


# ---------------------------------------------------------------- 工具规格（白名单）
TOOL_SPECS: dict[str, dict] = {
    "outline_generate": {
        "description": "根据主题生成 Markdown 大纲（# 标题 / ## 一级 / ### 二级 / - 要点）",
        "parameters": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "minLength": 2, "maxLength": 500},
                "language": {"type": "string", "enum": ["中文", "English", "日本語"]},
                "sections": {"type": "integer", "minimum": 3, "maximum": 8},
            },
            "required": ["topic"],
            "additionalProperties": False,
        },
    },
    "copy_generate": {
        "description": "为某个章节/要点生成演讲文案（60~120 字）",
        "parameters": {
            "type": "object",
            "properties": {
                "section": {"type": "string", "minLength": 1, "maxLength": 500},
                "language": {"type": "string", "enum": ["中文", "English", "日本語"]},
                "style": {"type": "string", "enum": ["professional", "casual", "academic"]},
            },
            "required": ["section"],
            "additionalProperties": False,
        },
    },
    "image_search": {
        "description": "按关键词检索配图，返回图片直链 + 版权来源说明（含内容安全审核）",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1, "maxLength": 100},
                "count": {"type": "integer", "minimum": 1, "maximum": 6},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    "write_file": {
        "description": "把内容写入沙箱目录内的文件（仅允许相对路径，禁止越界）",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 200,
                    # 只禁控制字符；具体越界判定交给沙箱守卫（能给出 path_absolute / path_traversal 等精确原因）
                    "pattern": r"^[^\x00-\x1f]+$",
                },
                "content": {"type": "string", "minLength": 1, "maxLength": 200000},
                "mode": {"type": "string", "enum": ["overwrite", "append"]},
            },
            "required": ["path", "content"],
            "additionalProperties": False,
        },
    },
}

WHITELIST = set(TOOL_SPECS.keys())


def tool_catalog_text() -> str:
    """给 Planner 看的工具目录（白名单 + 参数 Schema 摘要）。"""
    lines = []
    for name, spec in TOOL_SPECS.items():
        lines.append(f"- {name}: {spec['description']}")
        lines.append(f"  参数 Schema: {json.dumps(spec['parameters'], ensure_ascii=False)}")
    return "\n".join(lines)


# ---------------------------------------------------------------- 沙箱写文件
def _safe_target(rel_path: str) -> Path:
    raw = str(rel_path).strip().replace("\\", "/")
    if not raw:
        raise ToolError("path_empty", "path 不能为空")
    if raw.startswith("/") or re.match(r"^[A-Za-z]:", raw):
        raise ToolError("path_absolute", "禁止使用绝对路径，请使用沙箱内相对路径")
    if ".." in raw.split("/"):
        raise ToolError("path_traversal", "路径中不允许出现 ..")
    ext = Path(raw).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise ToolError("ext_not_allowed", f"仅允许写入 {sorted(ALLOWED_EXT)} 类型的文件")
    target = (SANDBOX_DIR / raw).resolve()
    try:
        target.relative_to(SANDBOX_DIR)
    except ValueError as e:  # 解析后越界
        raise ToolError("path_out_of_sandbox", f"目标路径越出沙箱目录：{target}") from e
    return target


def _write_file(args: dict, ctx: dict) -> dict:
    target = _safe_target(args["path"])
    content = args["content"]
    data = content.encode("utf-8")
    if len(data) > MAX_FILE_BYTES:
        raise ToolError("file_too_large", f"内容超过上限 {MAX_FILE_BYTES} 字节")
    target.parent.mkdir(parents=True, exist_ok=True)
    mode = args.get("mode", "overwrite")
    with open(target, "a" if mode == "append" else "w", encoding="utf-8") as f:
        f.write(content)
    rel = str(target.relative_to(SANDBOX_DIR)).replace("\\", "/")
    return {
        "ok": True,
        "tool": "write_file",
        "path": rel,
        "abs_path": str(target),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest()[:16],
        "mode": mode,
    }


# ---------------------------------------------------------------- 工具执行器
async def _outline_generate(args: dict, ctx: dict) -> dict:
    llm = ctx["llm"]
    usage = ctx["usage"]
    topic = args["topic"]
    language = args.get("language", "中文")
    sections = args.get("sections", 5)
    text = await llm.chat(
        [
            {
                "role": "system",
                "content": (
                    "你是演示文稿策划师。输出 Markdown 大纲：# 标题 → ## 一级部分 → ### 二级小节 → - 要点。"
                    f"一级部分 {sections} 个，每个一级下 3~4 个二级小节，每个二级下 3~5 条要点；只输出大纲本身。"
                ),
            },
            {"role": "user", "content": f"语言：{language}\n主题：{topic}"},
        ],
        agent="outline",
        usage=usage,
    )
    return {"ok": True, "tool": "outline_generate", "topic": topic, "outline": text, "chars": len(text)}


async def _copy_generate(args: dict, ctx: dict) -> dict:
    llm = ctx["llm"]
    usage = ctx["usage"]
    text = await llm.chat(
        [
            {"role": "system", "content": "你是 PPT 文案撰写助手，输出 60~120 字、条理清晰的中文要点说明，不要标题前缀。"},
            {
                "role": "user",
                "content": f"章节/要点：{args['section']}\n语言：{args.get('language', '中文')}\n风格：{args.get('style', 'professional')}",
            },
        ],
        agent="copy",
        usage=usage,
    )
    return {"ok": True, "tool": "copy_generate", "section": args["section"], "copy": text}


async def _image_search(args: dict, ctx: dict) -> dict:
    from . import tools_image  # 延迟导入，避免离线环境强依赖

    query = args["query"]
    count = args.get("count", 2)

    verdict = image_safety.moderate_query(query)
    if not verdict.allowed:
        raise ToolError("image_query_blocked", f"配图检索被内容安全策略拦截：{verdict.reason}", verdict.as_dict())

    raw = await tools_image.search_images(query, count)
    kept, blocked = [], []
    for img in raw:
        v = image_safety.moderate_image(img)
        if v.allowed:
            img = {**img, "attribution": image_safety.attribution_of(img)}
            kept.append(img)
        else:
            blocked.append({"url": img.get("url", ""), **v.as_dict()})
    if not kept:
        raise ToolError("image_all_blocked", "检索到的配图全部未通过内容安全审核", {"blocked": blocked})
    return {
        "ok": True,
        "tool": "image_search",
        "query": query,
        "images": kept,
        "blocked": blocked,
        "attribution": image_safety.build_attribution_slide(kept),
    }


HANDLERS: dict[str, Callable] = {
    "outline_generate": _outline_generate,
    "copy_generate": _copy_generate,
    "image_search": _image_search,
    "write_file": lambda args, ctx: _write_file(args, ctx),  # 同步实现，调用处统一 await 兼容
}


async def call_tool(name: str, args: dict, ctx: dict) -> dict:
    """白名单 → Schema 校验 → 执行。任何非法调用都不会被执行。"""
    if name not in WHITELIST:
        raise ToolError(
            "tool_not_allowed",
            f"工具 {name!r} 不在白名单内",
            {"whitelist": sorted(WHITELIST)},
        )
    if not isinstance(args, dict):
        raise SchemaError("args 必须是对象", {"args": args})
    validate_json_schema(args, TOOL_SPECS[name]["parameters"], path=f"{name}.args")
    result = HANDLERS[name](args, ctx)
    if hasattr(result, "__await__"):
        result = await result
    return result
