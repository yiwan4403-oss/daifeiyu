"""Manifest 读取与校验。"""

import yaml

from extensions.sdk import Manifest, ToolSpec


class ManifestError(Exception):
    pass


def load_manifest(path: str) -> Manifest:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception as exc:
        raise ManifestError(f"manifest 无法读取: {exc}") from exc
    if not isinstance(data, dict):
        raise ManifestError("manifest 必须是映射")
    for key in ("id", "name", "version"):
        if not data.get(key):
            raise ManifestError(f"缺少必填字段: {key}")
    tools = []
    for t in data.get("tools") or []:
        if isinstance(t, dict) and t.get("name"):
            tools.append(
                ToolSpec(
                    name=str(t["name"]),
                    description=str(t.get("description", "")),
                    params=str(t.get("params", "{}")),
                )
            )
    return Manifest(
        id=str(data["id"]),
        name=str(data["name"]),
        version=str(data["version"]),
        description=str(data.get("description", "")),
        capabilities=[str(c) for c in (data.get("capabilities") or [])],
        tools=tools,
        permissions=[str(p) for p in (data.get("permissions") or [])],
        python=str(data.get("python", ">=3.10")),
    )
