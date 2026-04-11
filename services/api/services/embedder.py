"""
Embedding pipeline (Voyage AI voyage-code-3) and Qdrant vector store client.
Uses query_points() — compatible with qdrant-client >= 1.7.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

import voyageai
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, PointStruct, VectorParams,
    Filter, FieldCondition, MatchValue,
)

from core.chunker import Chunk

logger = logging.getLogger(__name__)

VOYAGE_MODEL    = "voyage-code-3"
EMBEDDING_DIM   = 1024
COLLECTION_PRE  = "codelens"
BATCH_SIZE      = 64


@dataclass
class SearchHit:
    chunk_id:      str
    file_path:     str
    symbol_names:  list[str]
    language:      str
    score:         float
    code_snippet:  str
    generated_doc: str


class ChunkEmbedder:
    def __init__(self) -> None:
        self._voyage = voyageai.Client(api_key=os.environ["VOYAGE_API_KEY"])
        self._qdrant = QdrantClient(
            url=os.environ.get("QDRANT_URL", "http://localhost:6333"),
            api_key=os.environ.get("QDRANT_API_KEY") or None,
        )

    def upsert_chunks(self, job_id: str, chunks: list[Chunk],
                      pass_one_docs: dict[str, str]) -> int:
        collection = f"{COLLECTION_PRE}_{job_id}"
        self._ensure_collection(collection)

        texts: list[str] = []
        for chunk in chunks:
            doc  = pass_one_docs.get(chunk.chunk_id, "")
            text = f"{chunk.content}\n\n// Documentation:\n// {doc}" if doc else chunk.content
            texts.append(text[:8000])

        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), BATCH_SIZE):
            result = self._voyage.embed(texts[i:i+BATCH_SIZE],
                                        model=VOYAGE_MODEL, input_type="document")
            all_embeddings.extend(result.embeddings)

        points = [
            PointStruct(
                id=_id(chunk.chunk_id),
                vector=emb,
                payload={
                    "chunk_id":     chunk.chunk_id,
                    "file_path":    chunk.file_path,
                    "language":     chunk.language,
                    "symbol_names": chunk.symbol_names,
                    "code_snippet": chunk.content[:400],
                    "generated_doc": pass_one_docs.get(chunk.chunk_id, ""),
                    "job_id":       job_id,
                },
            )
            for chunk, emb in zip(chunks, all_embeddings)
        ]

        for i in range(0, len(points), BATCH_SIZE):
            self._qdrant.upsert(collection_name=collection, points=points[i:i+BATCH_SIZE])

        logger.info("Upserted %d chunks into %s", len(points), collection)
        return len(points)

    def _ensure_collection(self, collection: str) -> None:
        existing = {c.name for c in self._qdrant.get_collections().collections}
        if collection not in existing:
            self._qdrant.create_collection(
                collection_name=collection,
                vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
            )


class SemanticSearchEngine:
    def __init__(self) -> None:
        self._voyage = voyageai.Client(api_key=os.environ["VOYAGE_API_KEY"])
        self._qdrant = QdrantClient(
            url=os.environ.get("QDRANT_URL", "http://localhost:6333"),
            api_key=os.environ.get("QDRANT_API_KEY") or None,
        )

    def search(self, job_id: str, query: str,
               top_k: int = 5, language_filter: str | None = None) -> list[SearchHit]:
        collection = f"{COLLECTION_PRE}_{job_id}"

        result = self._voyage.embed([query], model=VOYAGE_MODEL, input_type="query")
        query_vector = result.embeddings[0]

        qfilter = None
        if language_filter:
            qfilter = Filter(
                must=[FieldCondition(key="language", match=MatchValue(value=language_filter))]
            )

        # query_points() replaces the deprecated .search() in qdrant-client >= 1.7
        results = self._qdrant.query_points(
            collection_name=collection,
            query=query_vector,
            limit=top_k,
            query_filter=qfilter,
            with_payload=True,
        )

        return [
            SearchHit(
                chunk_id=h.payload["chunk_id"],
                file_path=h.payload["file_path"],
                symbol_names=h.payload.get("symbol_names", []),
                language=h.payload["language"],
                score=h.score,
                code_snippet=h.payload.get("code_snippet", ""),
                generated_doc=h.payload.get("generated_doc", ""),
            )
            for h in results.points
        ]


def _id(chunk_id: str) -> int:
    return int(chunk_id[:15], 16)
