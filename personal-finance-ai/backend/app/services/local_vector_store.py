import hashlib
import math
import re

import chromadb
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.document import Document

VECTOR_SIZE = 384
CHUNK_SIZE = 1200
CHUNK_OVERLAP = 180


def _embedding(text: str) -> list[float]:
    vector = [0.0] * VECTOR_SIZE
    for token in re.findall(r"[\w.-]+", text.casefold()):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % VECTOR_SIZE
        vector[index] += -1.0 if digest[4] & 1 else 1.0
    length = math.sqrt(sum(value * value for value in vector))
    return [value / length for value in vector] if length else vector


def _chunks(text: str) -> list[str]:
    cleaned = re.sub(r"\n{3,}", "\n\n", text.strip())
    if not cleaned:
        return []
    chunks = []
    start = 0
    while start < len(cleaned):
        end = min(len(cleaned), start + CHUNK_SIZE)
        chunks.append(cleaned[start:end])
        if end == len(cleaned):
            break
        start = end - CHUNK_OVERLAP
    return chunks


def _collection():
    settings.chroma_dir.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(
        path=str(settings.chroma_dir),
        settings=chromadb.Settings(anonymized_telemetry=False),
    )
    return client.get_or_create_collection(
        "ledger_local_knowledge",
        metadata={"hnsw:space": "cosine"},
    )


def _help_sources() -> list[tuple[str, str, dict]]:
    sources = []
    for path in sorted(settings.docs_dir.glob("*.md")):
        sources.append(
            (
                f"help:{path.name}",
                path.read_text(encoding="utf-8"),
                {"basis": "help guide", "file_name": path.name, "source_id": path.name},
            )
        )
    return sources


def _document_sources(db: Session) -> list[tuple[str, str, dict]]:
    return [
        (
            f"document:{item.id}",
            item.extracted_text or "",
            {
                "basis": "document",
                "file_name": item.file_name,
                "source_id": str(item.id),
            },
        )
        for item in db.scalars(
            select(Document).where(Document.extracted_text.is_not(None))
        ).all()
    ]


def sync_local_knowledge(db: Session) -> int:
    collection = _collection()
    sources = [*_help_sources(), *_document_sources(db)]
    current_ids = set(collection.get(include=[])["ids"])
    next_ids: set[str] = set()
    ids = []
    documents = []
    metadatas = []
    embeddings = []
    for prefix, text, metadata in sources:
        for index, chunk in enumerate(_chunks(text)):
            chunk_id = f"{prefix}:{index}"
            next_ids.add(chunk_id)
            ids.append(chunk_id)
            documents.append(chunk)
            metadatas.append({**metadata, "chunk": index})
            embeddings.append(_embedding(chunk))
    stale = sorted(current_ids - next_ids)
    if stale:
        collection.delete(ids=stale)
    if ids:
        collection.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=embeddings,
        )
    return len(ids)


def search_local_knowledge(
    db: Session, query: str, basis: str, limit: int = 5
) -> list[dict]:
    sync_local_knowledge(db)
    collection = _collection()
    if collection.count() == 0:
        return []
    result = collection.query(
        query_embeddings=[_embedding(query)],
        n_results=min(limit, collection.count()),
        where={"basis": basis},
        include=["documents", "metadatas", "distances"],
    )
    matches = []
    for text, metadata, distance in zip(
        result["documents"][0],
        result["metadatas"][0],
        result["distances"][0],
        strict=True,
    ):
        matches.append(
            {
                "text": text,
                "basis": metadata["basis"],
                "file_name": metadata["file_name"],
                "source_id": metadata["source_id"],
                "distance": distance,
            }
        )
    terms = {
        token
        for token in re.findall(r"[\w.-]{4,}", query.casefold())
        if token
        not in {
            "document",
            "statement",
            "uploaded",
            "show",
            "what",
            "does",
            "confirm",
        }
    }
    if basis == "document":
        for document in db.scalars(
            select(Document).where(Document.extracted_text.is_not(None))
        ).all():
            text = document.extracted_text or ""
            candidates = _chunks(text)
            ranked_chunks = sorted(
                (
                    (
                        sum(chunk.casefold().count(term) for term in terms),
                        chunk,
                    )
                    for chunk in candidates
                ),
                reverse=True,
            )
            score, best_chunk = ranked_chunks[0] if ranked_chunks else (0, "")
            if not score:
                continue
            matches.append(
                {
                    "text": best_chunk,
                    "basis": "document",
                    "file_name": document.file_name,
                    "source_id": str(document.id),
                    "distance": 1 / (score + 1),
                }
            )
    elif basis == "help guide":
        for _, text, metadata in _help_sources():
            for chunk in _chunks(text):
                score = sum(chunk.casefold().count(term) for term in terms)
                if not score:
                    continue
                matches.append(
                    {
                        "text": chunk,
                        "basis": "help guide",
                        "file_name": metadata["file_name"],
                        "source_id": metadata["source_id"],
                        "distance": 1 / (score + 1),
                    }
                )
    deduplicated = {}
    for match in sorted(matches, key=lambda item: item["distance"]):
        key = (match["source_id"], match["text"][:120])
        deduplicated.setdefault(key, match)
    return list(deduplicated.values())[:limit]
