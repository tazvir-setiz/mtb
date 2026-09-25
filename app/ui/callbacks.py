"""
Callback Data ساختارمند: <namespace>:<action>[:<arg>]
"""
from __future__ import annotations


def parse(data: str) -> tuple[str, str, str | None]:
    parts = data.split(":")
    namespace = parts[0]
    action = parts[1] if len(parts) > 1 else ""
    arg = parts[2] if len(parts) > 2 else None
    return namespace, action, arg


def build(namespace: str, action: str, arg: str | None = None) -> str:
    if arg is None:
        return f"{namespace}:{action}"
    return f"{namespace}:{action}:{arg}"
