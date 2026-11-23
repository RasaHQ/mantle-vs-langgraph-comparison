"""The chat model and the embedding model."""

from __future__ import annotations

import os

import tiktoken
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from langgraph_native.config import AgentConfig
from langgraph_native.usage import Generation, UsageLedger

# Repro override: LANGGRAPH_LLM_TIMEOUT_S (default 30, the committed value).
_TIMEOUT_S = float(os.environ.get("LANGGRAPH_LLM_TIMEOUT_S", "30"))
_MAX_RETRIES = 2


def build_chat_model(config: AgentConfig) -> ChatOpenAI:
    """Returns the chat model named in *config*."""
    return ChatOpenAI(
        model=config.model,
        # Repro override: LANGGRAPH_REASONING_EFFORT (default "none", the committed value).
        reasoning_effort=os.environ.get("LANGGRAPH_REASONING_EFFORT", "none"),
        timeout=_TIMEOUT_S,
        max_retries=_MAX_RETRIES,
    )


class Embeddings:
    """Query and document embeddings, with query tokens billed to a conversation."""

    def __init__(self, config: AgentConfig, ledger: UsageLedger) -> None:
        self.model = config.embedding_model
        self._client = OpenAIEmbeddings(model=config.embedding_model)
        self._ledger = ledger
        self._encoding = tiktoken.get_encoding("cl100k_base")

    async def embed_query(self, conversation_id: str, text: str) -> list[float]:
        """Embeds one search query and records its token count."""
        vector = await self._client.aembed_query(text)
        self._ledger.record(
            conversation_id,
            Generation(
                call_type="knowledge_embedding",
                model=self.model,
                prompt=len(self._encoding.encode(text)),
            ),
        )
        return vector

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embeds knowledge chunks once at startup. Not billed to a conversation."""
        if not texts:
            return []
        return await self._client.aembed_documents(texts)
