"""Yes, no, or something else, from the customer's answer to a confirmation question."""

from __future__ import annotations

from typing import Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from langgraph_native.text import message_text

Answer = Literal["yes", "no", "other"]

_YES = frozenset(
    {"yes", "yeah", "yep", "yup", "sure", "ok", "okay", "alright", "go ahead"}
)
_NO = frozenset({"no", "nope", "nah", "cancel", "stop", "dont", "do not"})

_CLASSIFY = (
    "The customer was asked a yes or no question{question}. Reply with one word: "
    "yes if they agree, no if they decline, or other if they ask a question, "
    "raise a concern, or talk about something else instead of answering."
)


def normalise(text: str) -> str:
    """Returns *text* lowercased, with punctuation dropped."""
    cleaned = "".join(
        ch if ch.isalnum() or ch.isspace() else " " for ch in text.lower()
    )
    return " ".join(cleaned.split())


async def classify(
    text: str, model: BaseChatModel, question: str | None = None
) -> Answer:
    """Returns whether *text* agrees, declines, or does neither.

    Clear answers are decided here. Anything else, including a reply with a
    question in it, goes to a one-word model call, because a voice transcript
    is often a sentence rather than "yes".
    """
    normalised = normalise(text)
    if normalised in _YES:
        return "yes"
    if normalised in _NO:
        return "no"
    if "?" not in text:
        if normalised.startswith("yes"):
            return "yes"
        if normalised.startswith("no "):
            return "no"
    asked = f': "{question}"' if question else ""
    reply = await model.ainvoke(
        [
            SystemMessage(content=_CLASSIFY.format(question=asked)),
            HumanMessage(content=text),
        ]
    )
    word = normalise(message_text(reply))
    if word.startswith("yes"):
        return "yes"
    if word.startswith("no"):
        return "no"
    return "other"


async def is_yes(text: str, model: BaseChatModel) -> bool:
    """Test if *text* agrees. Anything that is not a clear yes counts as no."""
    return await classify(text, model) == "yes"
