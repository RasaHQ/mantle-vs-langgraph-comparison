"""Search over the copied ``data/references`` documents.

Chunking matches the Mantle agent's references index: 1000-character chunks,
20 characters of overlap, and the four closest chunks per query. Chunk
embeddings are built once per process and cached on disk, so they are not
billed to a conversation.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Protocol

from langchain_text_splitters import RecursiveCharacterTextSplitter
from pydantic import BaseModel, ConfigDict

from langgraph_native.config import DATA_DIR
from langgraph_native.llm import Embeddings

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 20
TOP_K = 4
_NO_MATCH = "No relevant policy was found."


class Chunk(BaseModel):
    """One piece of a reference document."""

    model_config = ConfigDict(frozen=True)

    text: str
    source: str


class Knowledge(Protocol):
    """What the search tool calls."""

    async def search(self, query: str, conversation_id: str) -> str:
        """Returns the text to show the model for *query*."""


class KnowledgeIndex:
    """Cosine search over embedded reference chunks."""

    def __init__(
        self, embeddings: Embeddings, chunks: list[Chunk], vectors: list[list[float]]
    ) -> None:
        self._embeddings = embeddings
        self._chunks = chunks
        self._vectors = [_normalise(vector) for vector in vectors]

    @classmethod
    async def build(
        cls,
        embeddings: Embeddings,
        references_dir: Path = DATA_DIR / "references",
        cache_dir: Path | None = None,
    ) -> "KnowledgeIndex":
        """Chunks and embeds every ``*.md`` file in *references_dir*."""
        chunks = load_chunks(references_dir)
        cache_dir = cache_dir or references_dir.parents[1] / ".cache"
        cache_path = (
            cache_dir / f"references-{_fingerprint(chunks, embeddings.model)}.json"
        )
        if cache_path.exists():
            vectors = json.loads(cache_path.read_text(encoding="utf-8"))
        else:
            vectors = await embeddings.embed_documents([chunk.text for chunk in chunks])
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(vectors), encoding="utf-8")
        return cls(embeddings, chunks, vectors)

    async def search(self, query: str, conversation_id: str) -> str:
        """Returns the closest chunks as text for the model."""
        if not self._chunks:
            return _NO_MATCH
        vector = await self._embeddings.embed_query(conversation_id, query)
        return render(self.closest(vector))

    def closest(self, vector: list[float]) -> list[Chunk]:
        """Returns the :data:`TOP_K` chunks nearest *vector*."""
        query = _normalise(vector)
        scored = sorted(
            zip(self._chunks, self._vectors),
            key=lambda pair: sum(left * right for left, right in zip(query, pair[1])),
            reverse=True,
        )
        return [chunk for chunk, _ in scored[:TOP_K]]


def load_chunks(references_dir: Path) -> list[Chunk]:
    """Returns the reference files split into chunks."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP, length_function=len
    )
    chunks: list[Chunk] = []
    for path in sorted(references_dir.glob("*.md")):
        for piece in splitter.split_text(path.read_text(encoding="utf-8")):
            if piece.strip():
                chunks.append(Chunk(text=piece, source=path.name))
    return chunks


def render(chunks: list[Chunk]) -> str:
    """Returns the chunks as the search tool's text."""
    if not chunks:
        return _NO_MATCH
    return "\n\n".join(f"[{chunk.source}]\n{chunk.text}" for chunk in chunks)


def _normalise(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def _fingerprint(chunks: list[Chunk], model: str) -> str:
    digest = hashlib.sha256(model.encode())
    for chunk in chunks:
        digest.update(chunk.source.encode())
        digest.update(chunk.text.encode())
    return digest.hexdigest()[:16]
