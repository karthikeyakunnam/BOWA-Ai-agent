"""Vector memory layer for BOWA.

Stores user interactions and facts in a persistent local vector database
to provide long-term semantic recall across sessions. If ChromaDB is not
installed, it falls back to a small JSON keyword recall store so the app still
runs locally.
"""

import json
import os
from pathlib import Path
from datetime import datetime, timezone

try:
    import chromadb
    from chromadb.config import Settings
    HAS_CHROMA = True
except ImportError:
    HAS_CHROMA = False

USE_CHROMA = os.environ.get("BOWA_USE_CHROMA", "0").strip() == "1"
_DB_PATH = Path("memory_db")
_FALLBACK_FILE = Path("memory_vectors_fallback.json")


def _get_collection():
    """Initialize and return the ChromaDB collection."""
    if not HAS_CHROMA or not USE_CHROMA:
        return None
    
    os.makedirs(_DB_PATH, exist_ok=True)
    client = chromadb.PersistentClient(path=str(_DB_PATH), settings=Settings(anonymized_telemetry=False))
    
    # We use a single collection for all users, filtering by user_id in metadata
    collection = client.get_or_create_collection(
        name="bowa_memories",
        metadata={"hnsw:space": "cosine"}
    )
    return collection


def add_memory(user_id: str, text: str, role: str = "user") -> None:
    """Add a conversation turn or fact to the user's vector memory."""
    if not text.strip():
        return

    collection = _get_collection()
    if not collection:
        _add_fallback_memory(user_id, text, role)
        return

    # Use a simple hash or counter for the ID
    import uuid
    doc_id = f"{user_id}_{uuid.uuid4().hex[:8]}"
    
    collection.add(
        documents=[text],
        metadatas=[{"user_id": user_id, "role": role}],
        ids=[doc_id]
    )


def retrieve_memory(user_id: str, query: str, n_results: int = 3) -> list[str]:
    """Retrieve relevant past memories for the user based on semantic similarity."""
    collection = _get_collection()
    if not collection:
        return _retrieve_fallback_memory(user_id, query, n_results)

    try:
        results = collection.query(
            query_texts=[query],
            n_results=n_results,
            where={"user_id": user_id}
        )
        
        if results and results.get("documents") and len(results["documents"]) > 0:
            return results["documents"][0]
        return []
    except Exception:
        # Chroma raises an exception if there are not enough items to query
        return _retrieve_fallback_memory(user_id, query, n_results)


def _read_fallback_store() -> dict[str, list[dict[str, str]]]:
    if not _FALLBACK_FILE.exists():
        return {}
    try:
        with _FALLBACK_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_fallback_store(store: dict[str, list[dict[str, str]]]) -> None:
    with _FALLBACK_FILE.open("w", encoding="utf-8") as file:
        json.dump(store, file, indent=2)


def _add_fallback_memory(user_id: str, text: str, role: str) -> None:
    store = _read_fallback_store()
    items = store.get(user_id, [])
    items.append({
        "text": text,
        "role": role,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    store[user_id] = items[-200:]
    _write_fallback_store(store)


def _score_overlap(query: str, text: str) -> int:
    query_terms = {term for term in query.lower().split() if len(term) > 2}
    text_terms = {term for term in text.lower().split() if len(term) > 2}
    return len(query_terms & text_terms)


def _retrieve_fallback_memory(user_id: str, query: str, n_results: int) -> list[str]:
    items = _read_fallback_store().get(user_id, [])
    scored = [
        (_score_overlap(query, item.get("text", "")), item.get("text", ""))
        for item in items
        if isinstance(item, dict)
    ]
    scored.sort(key=lambda item: item[0], reverse=True)
    return [text for score, text in scored[:n_results] if score > 0 and text]
