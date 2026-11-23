"""Fixed texts from ``data/responses.yml``, spoken without a model call."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from langgraph_native.config import DATA_DIR


class Utterance(BaseModel):
    """A response to speak and the values for its placeholders."""

    model_config = ConfigDict(frozen=True)

    name: str
    values: dict[str, Any] = Field(default_factory=dict)


class Responses:
    """Response templates by name."""

    def __init__(self, templates: dict[str, str]) -> None:
        self._templates = templates

    @classmethod
    def load(cls, path: Path) -> "Responses":
        """Reads the templates from a YAML mapping of name to text."""
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return cls({str(name): str(text).strip() for name, text in document.items()})

    def render(self, utterance: Utterance) -> str:
        """Returns the response text with its placeholders filled.

        Raises:
            KeyError: When the response or one of its placeholders is unknown.
        """
        return self._templates[utterance.name].format_map(utterance.values).strip()

    def names(self) -> set[str]:
        """Returns every response name."""
        return set(self._templates)


@lru_cache(maxsize=1)
def default_responses() -> Responses:
    """Returns the agent's responses from ``data/responses.yml``."""
    return Responses.load(DATA_DIR / "responses.yml")
