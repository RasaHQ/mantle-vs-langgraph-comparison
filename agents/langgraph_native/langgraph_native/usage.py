"""Per-conversation token usage, in the shape ``/engine_tokens`` returns.

Priced with the same ``litellm`` release the Mantle agent prices with, so a
gap between the two comes from token counts, not from price tables.
"""

from __future__ import annotations

import threading
from collections import defaultdict
from datetime import datetime, timezone
from importlib.metadata import version
from typing import Any, Optional

import litellm
from pydantic import BaseModel

_PRICE_PROVIDER = "litellm"


class Generation(BaseModel):
    """Token counts for one model call."""

    call_type: str
    model: str
    prompt: int = 0
    completion: int = 0
    cached: int = 0
    cache_write: int = 0


class _Bucket(BaseModel):
    model: str
    prompt: int = 0
    completion: int = 0
    cached: int = 0
    cache_write: int = 0
    generations: int = 0
    cost: Optional[float] = 0.0


class UsageLedger:
    """Thread-safe model calls per conversation id."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._calls: dict[str, list[Generation]] = defaultdict(list)

    def record(self, conversation_id: str, generation: Generation) -> None:
        """Adds one model call."""
        with self._lock:
            self._calls[conversation_id].append(generation)

    def payload(self, conversation_id: str) -> dict[str, Any]:
        """Returns the conversation's usage as an ``/engine_tokens`` body."""
        fetched_at = datetime.now(timezone.utc).isoformat()
        with self._lock:
            calls = list(self._calls.get(conversation_id, []))
        if not calls:
            return {
                "status": "not_found",
                "session_id": conversation_id,
                "fetched_at": fetched_at,
            }

        by_call_type: dict[str, dict[str, _Bucket]] = defaultdict(dict)
        for call in calls:
            bucket = by_call_type[call.call_type].setdefault(
                call.model, _Bucket(model=call.model)
            )
            bucket.prompt += call.prompt
            bucket.completion += call.completion
            bucket.cached += call.cached
            bucket.cache_write += call.cache_write
            bucket.generations += 1
            call_cost = generation_cost(call)
            if call_cost is None or bucket.cost is None:
                bucket.cost = None
            else:
                bucket.cost += call_cost

        buckets = [
            bucket for models in by_call_type.values() for bucket in models.values()
        ]
        prompt = sum(bucket.prompt for bucket in buckets)
        completion = sum(bucket.completion for bucket in buckets)
        priced = all(bucket.cost is not None for bucket in buckets)
        return {
            "status": "complete",
            "session_id": conversation_id,
            "prompt": prompt,
            "completion": completion,
            "cached": sum(bucket.cached for bucket in buckets),
            "cache_write": sum(bucket.cache_write for bucket in buckets),
            "total": prompt + completion,
            "generations": sum(bucket.generations for bucket in buckets),
            "cost": sum(bucket.cost or 0.0 for bucket in buckets),
            "cost_status": "complete" if priced else "partial",
            "price_source": {
                "provider": _PRICE_PROVIDER,
                "version": version("litellm"),
            },
            "by_call_type": {
                call_type: [
                    {**bucket.model_dump(), "total": bucket.prompt + bucket.completion}
                    for bucket in models.values()
                ]
                for call_type, models in by_call_type.items()
            },
            "fetched_at": fetched_at,
        }


def generation_cost(generation: Generation) -> Optional[float]:
    """Returns the USD cost of one call, or ``None`` when it cannot be priced."""
    try:
        prompt_cost, completion_cost = litellm.cost_per_token(
            model=generation.model,
            prompt_tokens=generation.prompt,
            completion_tokens=generation.completion,
            cache_read_input_tokens=generation.cached,
            cache_creation_input_tokens=generation.cache_write,
        )
    except Exception:  # noqa: BLE001 - litellm raises bare Exception for unknown models
        return None
    return prompt_cost + completion_cost
