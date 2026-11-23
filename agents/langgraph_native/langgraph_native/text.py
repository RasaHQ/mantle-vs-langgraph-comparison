"""Plain text out of a model message."""

from __future__ import annotations

from langchain_core.messages import AIMessage


def message_text(message: AIMessage) -> str:
    """Returns the text of *message*, ignoring tool calls and other blocks."""
    content = message.content
    if isinstance(content, str):
        return content.strip()
    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text") or ""))
    return "\n".join(part for part in parts if part).strip()
