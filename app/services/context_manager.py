import json
import time

from app.database.database import get_session
from app.database.repository import SettingsRepository
from app.guard_config import GuardSettings
from app.services.text_normalizer import normalize


def _read(chat_id: int, now: float) -> dict:
    with get_session() as session:
        raw = SettingsRepository.get(session, f"guard_context:{chat_id}", default="{}")
    try:
        state = json.loads(raw)
        if not isinstance(state, dict):
            return {}
        for name in ("t", "e", "a"):
            entries = state.get(name, {})
            state[name] = {
                key: item
                for key, item in entries.items()
                if isinstance(key, str)
                and 0 < len(key) <= 48
                and isinstance(item, dict)
                and isinstance(item.get("exp"), (int, float))
                and item["exp"] > now
                and isinstance(item.get("v"), str)
                and 0 < len(item["v"]) <= 48
            }
        if not isinstance(state.get("p"), (int, float)) or state["p"] <= now:
            state["p"] = 0
        return state
    except (ValueError, TypeError, AttributeError):
        return {}


def load_context(chat_id: int | None, limits: GuardSettings, now: float | None = None) -> dict:
    if chat_id is None:
        return {}
    state = _read(chat_id, time.time() if now is None else now)
    return {
        "p": bool(state.get("p")),
        "t": list(state.get("t", {}))[-limits.max_topics :],
        "e": list(state.get("e", {}))[-limits.max_entities :],
        "a": {k: item["v"] for k, item in list(state.get("a", {}).items())[-limits.max_aliases :]},
    }


def update_context(
    chat_id: int | None, update: dict, text: str, limits: GuardSettings, now: float | None = None
) -> None:
    if chat_id is None or not update:
        return
    if not isinstance(update, dict):
        return
    now = time.time() if now is None else now
    state = _read(chat_id, now)
    expiry = now + limits.context_ttl_hours * 3600
    if update.get("political") is True:
        state["p"] = expiry
    for field, incoming, maximum in (
        ("t", "topics_add", limits.max_topics),
        ("e", "entities_add", limits.max_entities),
    ):
        entries = state.setdefault(field, {})
        additions = update.get(incoming, [])
        if not isinstance(additions, list):
            additions = []
        for value in additions[:maximum]:
            if isinstance(value, str) and 0 < len(value) <= 48 and normalize(value) in text:
                entries.pop(value, None)
                entries[value] = {"v": value, "exp": expiry}
        state[field] = dict(list(entries.items())[-maximum:])
    aliases = state.setdefault("a", {})
    additions = update.get("aliases_add", {})
    if not isinstance(additions, dict):
        additions = {}
    for alias, meaning in list(additions.items())[: limits.max_aliases]:
        if not all(isinstance(v, str) and 0 < len(v) <= 48 for v in (alias, meaning)):
            continue
        declaration = f"{normalize(alias)} یعنی {normalize(meaning)}"
        english = f"{normalize(alias)} means {normalize(meaning)}"
        if declaration in text or english in text:
            aliases.pop(alias, None)
            aliases[alias] = {"v": meaning, "exp": expiry}
    state["a"] = dict(list(aliases.items())[-limits.max_aliases :])
    state["updated_at"] = now
    with get_session() as session:
        SettingsRepository.set(
            session, f"guard_context:{chat_id}", json.dumps(state, ensure_ascii=False)
        )
