"""Notes speech the customer interrupted, so later turns do not treat it as heard."""

from __future__ import annotations

from langchain_core.messages import SystemMessage
from langgraph.config import get_config

PREFIX = (
    "The customer started speaking before these messages finished, "
    "so they did not hear all of them."
)


def note_for(texts: list[str]) -> str | None:
    """Returns the history note for *texts*, or ``None`` when there is nothing."""
    unique: list[str] = []
    for text in texts:
        cleaned = text.strip()
        if cleaned and cleaned not in unique:
            unique.append(cleaned)
    if not unique:
        return None
    lines = "\n".join(f"- {text}" for text in unique)
    return f"{PREFIX} Do not assume they were heard:\n{lines}"


def already_noted(messages: list) -> bool:
    """Test if *messages* already records an interrupted reply."""
    return any(PREFIX in _content(message) for message in messages)


def unheard_message(messages: list, texts: list[str]) -> SystemMessage | None:
    """Returns a history message for *texts* when one is not already present."""
    if already_noted(messages):
        return None
    note = note_for(texts)
    if note is None:
        return None
    return SystemMessage(content=note)


def configured_unheard() -> list[str]:
    """Returns interrupted replies stashed on this run, if any."""
    try:
        config = get_config()
    except RuntimeError:
        return []
    raw = (config.get("configurable") or {}).get("unheard") or []
    return [text for text in raw if isinstance(text, str)]


def _content(message: object) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    parts: list[str] = []
    if isinstance(content, list):
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                parts.append(str(block.get("text") or ""))
    return "\n".join(parts)
