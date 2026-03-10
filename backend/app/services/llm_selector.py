from __future__ import annotations
"""
app/services/llm_selector.py — LLM 动态模型选择器 (Rule 01-Stack-AI-Routing)

严禁在业务代码中硬编码物理模型名（如 gemini-2.5-flash）。
所有 LLM 调用必须通过本模块按任务类型选择模型。

用法：
    from app.services.llm_selector import LLMSelector

    model_config = LLMSelector.get_model_for_task("report_parse")
    model_name = model_config["name"]       # "gemini-2.5-flash"
    temperature = model_config["temperature"] # 0.1
"""
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


# 注册表文件路径（backend/llm_registry.yaml）
_REGISTRY_PATH = Path(__file__).parent.parent.parent / "llm_registry.yaml"


@lru_cache(maxsize=1)
def _load_registry() -> dict[str, Any]:
    """加载并缓存 LLM 注册表（进程生命周期内只读一次）"""
    registry_path = os.getenv("LLM_REGISTRY_PATH", str(_REGISTRY_PATH))
    with open(registry_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("models", {})


class LLMSelector:
    """
    LLM 动态选择器。

    通过任务类型从 llm_registry.yaml 获取模型配置，
    确保业务代码与物理模型名完全解耦。
    """

    @staticmethod
    def get_model_for_task(task_type: str) -> dict[str, Any]:
        """
        根据任务类型获取完整模型配置。

        Args:
            task_type: 任务类型标识，对应 llm_registry.yaml 中的 key
                       如 "report_parse", "admin_chat", "deep_analysis"

        Returns:
            dict 包含 name, tier, temperature, max_tokens, description

        Raises:
            KeyError: 未注册的任务类型
        """
        registry = _load_registry()
        if task_type not in registry:
            raise KeyError(
                f"未注册的 LLM 任务类型: '{task_type}'。"
                f"可用的任务类型: {list(registry.keys())}"
            )
        return registry[task_type]

    @staticmethod
    def get_model_name(task_type: str) -> str:
        """快捷方法：仅返回模型名称"""
        return LLMSelector.get_model_for_task(task_type)["name"]

    @staticmethod
    def get_temperature(task_type: str) -> float:
        """快捷方法：返回该任务推荐的 temperature"""
        return LLMSelector.get_model_for_task(task_type).get("temperature", 0.3)

    @staticmethod
    def get_max_tokens(task_type: str) -> int:
        """快捷方法：返回该任务推荐的 max_tokens"""
        return LLMSelector.get_model_for_task(task_type).get("max_tokens", 1024)

    @staticmethod
    def list_tasks() -> list[str]:
        """列出所有已注册的任务类型"""
        return list(_load_registry().keys())

    @staticmethod
    def reload():
        """强制重新加载注册表（热更新场景）"""
        _load_registry.cache_clear()
