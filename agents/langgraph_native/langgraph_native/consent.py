"""Yes or no from the customer's answer to a confirmation question."""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from langgraph_native.text import message_text

_YES = frozenset(
    {"yes", "yeah", "yep", "yup", "sure", "ok", "okay", "alright", "go ahead"}
)
_NO = frozenset({"no", "nope", "nah", "cancel", "stop", "dont", "do not"})

_CLASSIFY = (
    "The customer was asked a yes or no question. Reply with one word: yes or no."
)


def normalise(text: str) -> str:
    """Returns *text* lowercased, with punctuation dropped."""
    cleaned = "".join(
        ch if ch.isalnum() or ch.isspace() else " " for ch in text.lower()
    )
    return " ".join(cleaned.split())


async def is_yes(text: str, model: BaseChatModel) -> bool:
    """Test if *text* agrees.

    Clear answers are decided here. Anything else goes to a one-word model
    call, because a voice transcript is often a sentence rather than "yes".
    """
    normalised = normalise(text)
    if normalised in _YES or normalised.startswith("yes"):
        return True
    if normalised in _NO or normalised.startswith("no"):
        return False
    reply = await model.ainvoke(
        [SystemMessage(content=_CLASSIFY), HumanMessage(content=text)]
    )
    return normalise(message_text(reply)).startswith("yes")
