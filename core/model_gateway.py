"""统一模型网关：超时/重试/费用与 token 统计（Phase 1 用标准库实现）。"""

import json
import os
import time
import urllib.error
import urllib.request


class GatewayError(Exception):
    pass


class ModelGateway:
    def __init__(self, cfg: dict) -> None:
        base = cfg["base_url"].rstrip("/")
        if not base.endswith("/chat/completions"):
            base += "/chat/completions"
        self.base_url = base
        self.api_key = os.environ.get(cfg.get("api_key_env", "DEEPSEEK_API_KEY"), "")
        self.model = cfg["model"]
        self.timeout = int(cfg.get("timeout_seconds", 60))
        self.max_tokens = int(cfg.get("max_tokens", 300))
        self.temperature = float(cfg.get("temperature", 0.9))
        self.retries = int(cfg.get("retries", 2))
        self.usage: list[dict] = []

    def chat(self, system: str, user: str) -> str:
        if not self.api_key:
            raise GatewayError("未配置 API Key（环境变量缺失）")
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": False,
        }
        last_err: Exception = GatewayError("unknown")
        for attempt in range(self.retries + 1):
            try:
                return self._post(payload)
            except GatewayError as exc:
                last_err = exc
                time.sleep(min(2 ** attempt, 8))
        raise last_err

    def _post(self, payload: dict) -> str:
        req = urllib.request.Request(
            self.base_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise GatewayError(f"HTTP {exc.code}") from exc
        except Exception as exc:
            raise GatewayError(str(exc)) from exc

        usage = data.get("usage", {})
        self.usage.append(
            {
                "ts": time.time(),
                "in": usage.get("prompt_tokens", 0),
                "out": usage.get("completion_tokens", 0),
            }
        )
        return data["choices"][0]["message"]["content"].strip()
