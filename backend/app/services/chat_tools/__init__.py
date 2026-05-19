"""
app/services/chat_tools/ — 总经理 AI 对话的 Tool 集合

设计原则:
- 每个 Tool 是一个 async 函数,装饰 @tool 自动注册到 ToolRegistry
- 自动从 type hints + docstring 抽取 OpenAI Function Calling JSON Schema
- Tool 拿到 db: AsyncSession + 业务参数,返回 dict(可序列化为 JSON 给 LLM)
- 失败时返回 {"error": "..."},LLM 可在多轮中决定是否重试/澄清

使用方式:
    from app.services.chat_tools import registry, tool

    @tool(description="查询近 N 天日报数")
    async def count_reports(db: AsyncSession, days: int = 7) -> dict:
        '''
        Args:
            days: 查询的天数,默认 7
        '''
        ...

    # 给 LLM:
    schemas = registry.openai_schemas()
    # 执行:
    result = await registry.dispatch("count_reports", db, {"days": 7})
"""
from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional, get_args, get_origin, get_type_hints

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("aipm.chat_tools")


ToolFunc = Callable[..., Awaitable[Any]]


# ────────────────────────────────────────────────────────────────
# Type → JSON Schema 简单映射(够用即可,不引入 pydantic 重型方案)
# ────────────────────────────────────────────────────────────────

_PRIMITIVE_TO_JSON = {
    int: "integer",
    float: "number",
    str: "string",
    bool: "boolean",
}


def _py_type_to_json(annotation: Any) -> dict[str, Any]:
    """把 Python 类型注解转换为 JSON Schema 片段"""
    if annotation is inspect.Parameter.empty or annotation is type(None):
        return {"type": "string"}

    origin = get_origin(annotation)
    if origin is None:
        if annotation in _PRIMITIVE_TO_JSON:
            return {"type": _PRIMITIVE_TO_JSON[annotation]}
        # 兜底:无法识别按 string 处理(LLM 自然语言场景下足够)
        return {"type": "string"}

    # list[X] / List[X]
    if origin in (list,):
        args = get_args(annotation)
        item_type = args[0] if args else str
        return {"type": "array", "items": _py_type_to_json(item_type)}

    # Optional[X] = Union[X, None]
    if origin is type(None) or str(origin).endswith("UnionType") or origin.__name__ == "Union":
        # 取第一个非 None 的类型
        for a in get_args(annotation):
            if a is not type(None):
                return _py_type_to_json(a)
        return {"type": "string"}

    if origin is dict:
        return {"type": "object"}

    return {"type": "string"}


def _parse_param_docs(docstring: Optional[str]) -> dict[str, str]:
    """从 docstring 的 Args 段解析每个参数的中文描述"""
    if not docstring:
        return {}
    docs: dict[str, str] = {}
    in_args = False
    for line in docstring.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("args:"):
            in_args = True
            continue
        if in_args:
            if not stripped or stripped.endswith(":") and not stripped.startswith("-"):
                # 下一个 section
                if ":" in stripped and not stripped[0].isalpha():
                    continue
                if not stripped:
                    in_args = False
                    continue
            # 形如:  param_name: 描述文本
            if ":" in stripped:
                name, _, desc = stripped.partition(":")
                name = name.strip().lstrip("-").strip()
                if name:
                    docs[name] = desc.strip()
    return docs


# ────────────────────────────────────────────────────────────────
# Tool 元数据
# ────────────────────────────────────────────────────────────────


@dataclass
class ToolSpec:
    name: str
    description: str
    func: ToolFunc
    parameters_schema: dict[str, Any] = field(default_factory=dict)

    def to_openai_schema(self) -> dict[str, Any]:
        """OpenAI / Gemini Function Calling 协议要求的 JSON 结构"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_schema,
            },
        }


# ────────────────────────────────────────────────────────────────
# Registry
# ────────────────────────────────────────────────────────────────


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            logger.warning("tool %s already registered, overwriting", spec.name)
        self._tools[spec.name] = spec

    def get(self, name: str) -> Optional[ToolSpec]:
        return self._tools.get(name)

    def all(self) -> list[ToolSpec]:
        return list(self._tools.values())

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def openai_schemas(self, only: Optional[list[str]] = None) -> list[dict[str, Any]]:
        """返回给 LLM 的 tools 列表"""
        items = self.all() if not only else [self._tools[n] for n in only if n in self._tools]
        return [t.to_openai_schema() for t in items]

    async def dispatch(
        self, name: str, db: AsyncSession, args: dict[str, Any]
    ) -> dict[str, Any]:
        """
        执行一个 Tool。失败时返回 {"error": "..."},而不是抛异常 —
        这样 LLM 可以在下一轮看到错误并自主决策(重试/换工具/告知用户)。
        """
        spec = self._tools.get(name)
        if not spec:
            return {"error": f"unknown tool: {name}"}

        # 过滤掉不在 signature 里的多余参数,避免 TypeError
        sig = inspect.signature(spec.func)
        accepted = {p for p in sig.parameters.keys() if p != "db"}
        clean_args = {k: v for k, v in (args or {}).items() if k in accepted}

        try:
            result = await spec.func(db, **clean_args)
            if not isinstance(result, dict):
                result = {"result": result}
            return result
        except Exception as exc:
            logger.exception("tool %s raised", name)
            return {"error": f"{type(exc).__name__}: {exc}"[:300]}


# 全局单例
registry = ToolRegistry()


# ────────────────────────────────────────────────────────────────
# 装饰器
# ────────────────────────────────────────────────────────────────


def tool(
    *,
    name: Optional[str] = None,
    description: str,
) -> Callable[[ToolFunc], ToolFunc]:
    """
    Tool 注册装饰器。

    用法:
        @tool(description="查询近 N 天日报数")
        async def count_reports(db: AsyncSession, days: int = 7) -> dict:
            '''
            Args:
                days: 天数,默认 7
            '''
            ...

    自动:
    - 从函数签名抽取参数类型 → JSON Schema
    - 从 docstring 抽取参数中文描述
    - 注册到全局 registry
    """

    def decorator(func: ToolFunc) -> ToolFunc:
        sig = inspect.signature(func)
        param_docs = _parse_param_docs(func.__doc__)
        # 解析真实类型对象(绕过 `from __future__ import annotations` 的字符串延迟)
        try:
            resolved_hints = get_type_hints(func)
        except Exception:  # pragma: no cover
            resolved_hints = {}

        properties: dict[str, Any] = {}
        required: list[str] = []

        for pname, param in sig.parameters.items():
            if pname == "db":
                continue
            annotation = resolved_hints.get(pname, param.annotation)
            prop = _py_type_to_json(annotation)
            if pname in param_docs:
                prop["description"] = param_docs[pname]
            properties[pname] = prop
            if param.default is inspect.Parameter.empty:
                required.append(pname)

        schema: dict[str, Any] = {"type": "object", "properties": properties}
        if required:
            schema["required"] = required

        spec = ToolSpec(
            name=name or func.__name__,
            description=description,
            func=func,
            parameters_schema=schema,
        )
        registry.register(spec)
        return func

    return decorator


# ────────────────────────────────────────────────────────────────
# 自动导入子模块以触发 @tool 注册
# ────────────────────────────────────────────────────────────────


def _autoload() -> None:
    from importlib import import_module
    for mod in ("reports", "projects", "people", "weekly_report", "okr"):
        try:
            import_module(f"app.services.chat_tools.{mod}")
        except ImportError as exc:  # pragma: no cover
            logger.warning("chat_tools.%s import failed: %s", mod, exc)


_autoload()
