"""RAG engine (extended).

Absorbs Namrata's Jira Integrated RAG Explorer: ingest a source document,
chunk it, embed + store, then answer questions strictly from the retrieved
chunks with a visible retrieve-then-generate pipeline (chunks shown beside
answers, tunable top-K, chunk editing).

Deterministic-first Phase 0: chunking + keyword retrieval run locally so the
whole pipeline is visible and testable offline. A real embedding provider
(and vector store) can replace the retriever behind the same interface.
"""

from __future__ import annotations

import re

from ..core.llm import LLMRouter
from ..pipeline.registry import Engine, register


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> list[dict]:
    """Split a document into overlapping chunks with stable ids."""
    words = text.split()
    chunks = []
    start = 0
    idx = 1
    while start < len(words):
        piece = " ".join(words[start : start + chunk_size])
        chunks.append({"id": f"chunk_{idx:03d}", "text": piece, "start": start})
        start += chunk_size - overlap
        idx += 1
    return chunks


def retrieve(chunks: list[dict], query: str, top_k: int = 3) -> list[dict]:
    """Tiny deterministic retriever: rank chunks by shared-token overlap."""
    q_tokens = {w for w in re.findall(r"\w+", query.lower()) if len(w) > 2}
    scored = []
    for c in chunks:
        c_tokens = {w for w in re.findall(r"\w+", c["text"].lower()) if len(w) > 2}
        score = len(q_tokens & c_tokens)
        scored.append((score, c))
    scored.sort(key=lambda x: -x[0])
    return [c for _, c in scored[:top_k]]


async def _rag(ctx: dict, **payload) -> dict:
    router: LLMRouter = ctx["router"]
    doc: str = payload.get("document", "")
    query: str = payload.get("query", "")
    top_k: int = int(payload.get("top_k", 3))

    if not doc:
        return {
            "kind": "rag_report",
            "payload": {"error": "document is required."},
            "engine": "rag",
        }

    chunks = chunk_text(doc)
    hits = retrieve(chunks, query, top_k) if query else []

    answer = None
    if query and not router.is_mock:
        context = "\n\n".join(h.get("text", "") for h in hits)
        answer = await router.complete_text(
            "Answer ONLY from the provided context. If the context lacks the "
            "answer, say 'Insufficient information in the document.'",
            f"CONTEXT:\n{context}\n\nQUESTION: {query}",
        )
    elif query:
        answer = (
            "Deterministic mode: retrieved the top chunks shown. Configure an "
            "LLM provider for a generated answer grounded in those chunks."
        )

    return {
        "kind": "rag_report",
        "payload": {
            "chunk_count": len(chunks),
            "chunks": chunks,
            "top_k": top_k,
            "query": query,
            "retrieved": hits,
            "answer": answer,
            "visible_pipeline": True,
        },
        "engine": "rag",
    }


def register_engines() -> None:
    register(
        Engine(
            id="rag",
            name="RAG Explorer",
            description="Visible retrieve-then-generate over a document: "
            "browse/edit chunks, tune top-K, ask grounded questions.",
            uses_llm=True,
            run=_rag,
        )
    )


register_engines()