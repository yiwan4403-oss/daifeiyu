"""代码生成器：LLM 产出 manifest + plugin.py + test_plugin.py。只写沙箱，不写生产。"""

import asyncio
import json
import re

from core.model_gateway import ModelGateway

GEN_PROMPT = (
    "你是 Resident 的插件开发者。根据需求，生成一个可用的 Python 插件。\n"
    "输出 JSON 对象，字段：\n"
    '{"id": "插件id(小写字母数字-)", "name": "插件名", "version": "1.0.0",\n'
    ' "description": "一句话", "capabilities": ["能力名"],\n'
    ' "tools": [{"name": "工具名", "description": "工具说明", "params": "参数说明"}],\n'
    ' "permissions": [],\n'
    ' "code": "plugin.py 完整内容", "tests": "test_plugin.py 完整内容"}\n'
    "规则：\n"
    "- plugin.py 必须定义 class PluginClass(Plugin)，继承自 extensions.sdk.Plugin；"
    "manifest 属性从 Plugin 基类继承的 manifest 用类属性声明\n"
    "- 用 from extensions.sdk import Plugin 导入\n"
    "- tool(name) 方法按名字返回工具函数；工具函数签名 (ctx, ...) 或纯参数均可，"
    "测试里直接调用 plugin.tool('xxx')\n"
    "- tests 用 pytest 风格，包含至少一个真实断言\n"
    "- 只允许标准库 import\n"
    "- 代码里禁止 import os/sys/subprocess 之外的危险模块，禁止读写插件目录以外文件\n"
    "只输出 JSON，不要解释。"
)


class CodeGenerator:
    def __init__(self, cfg: dict) -> None:
        m = cfg["model"]
        reason = cfg.get("task_models", {}).get("reason", m["model"])
        light = cfg.get("task_models", {}).get("light", m["model"])
        self.gateway = ModelGateway(
            {
                "base_url": m["base_url"],
                "api_key_env": m.get("api_key_env", "DEEPSEEK_API_KEY"),
                "model": reason,
                "timeout_seconds": int(m.get("timeout_seconds", 60)),
                "max_tokens": 16000,
                "temperature": 0.2,
                "retries": 1,
            }
        )
        self.fallback = ModelGateway(
            {
                "base_url": m["base_url"],
                "api_key_env": m.get("api_key_env", "DEEPSEEK_API_KEY"),
                "model": light,
                "timeout_seconds": int(m.get("timeout_seconds", 60)),
                "max_tokens": 16000,
                "temperature": 0.1,
                "retries": 1,
            }
        )

    def _parse(self, raw: str) -> dict | None:
        raw = raw.strip()
        raw = re.sub(r"^```[a-zA-Z]*\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end <= start:
            return None
        try:
            data = json.loads(raw[start : end + 1])
        except Exception:
            return None
        for key in ("id", "name", "version", "code", "tests"):
            if not data.get(key):
                return None
        return data

    def generate_sync(self, requirement: str) -> dict:
        if not getattr(self.gateway, "api_key", ""):
            return {"error": "未配置 API Key"}
        for gw, prompt in (
            (self.gateway, GEN_PROMPT),
            (self.gateway, GEN_PROMPT + "\n上次输出无法解析。只输出一个 JSON 对象，不要代码块。"),
            (self.fallback, GEN_PROMPT + "\n只输出一个 JSON 对象，不要代码块、不要解释。"),
        ):
            try:
                raw = gw.chat(prompt, requirement)
            except Exception as exc:
                continue
            data = self._parse(raw)
            if data is not None:
                return data
        return {"error": "模型输出无法解析为 JSON（已重试并降级）"}

    async def generate(self, requirement: str) -> dict:
        return await asyncio.to_thread(self.generate_sync, requirement)
