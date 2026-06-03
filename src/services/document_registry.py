"""
Filesystem-backed document registry helpers that do not depend on Qdrant.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from core.config import DOCUMENTS_DIR, EMBEDDING_MODEL
from scripts.corpus_utils import canonical_document_ids


def _clean_source_title(filename: str) -> str:
    """Return a readable title from a source filename when no explicit title exists."""
    stem = Path(filename or "unknown").stem
    stem = re.sub(r"\s*\([^)]*(?:vetbooks|pdf|scan)[^)]*\)\s*", " ", stem, flags=re.IGNORECASE)
    stem = stem.replace("_", " ")
    stem = re.sub(r"\s+", " ", stem).strip(" -")
    return stem or filename or "unknown"


def _extract_publication_year(*values: object) -> Optional[int]:
    """Extract a plausible publication year from metadata or filenames."""
    for value in values:
        if value is None:
            continue
        text = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
        for match in re.finditer(r"\b(19\d{2}|20\d{2})\b", text):
            year = int(match.group(1))
            if 1900 <= year <= 2100:
                return year
    return None


def _classify_catalog_scope(document_id: str, raw_data: dict, canonical_ids: set[str]) -> str:
    """Tag a document as canonical corpus or operational upload."""
    if document_id in canonical_ids:
        return "canonical"
    raw_json_path = str(raw_data.get("raw_json_path", "") or "").replace("\\", "/")
    if "/uploads/" in raw_json_path:
        return "operational"
    metadata = raw_data.get("metadata", {})
    explicit_scope = metadata.get("catalog_scope")
    if explicit_scope in {"canonical", "operational"}:
        return explicit_scope
    return "operational"


def _load_workspace_items(workspace_id: str = "default") -> list[dict]:
    """Load every readable raw/chunk pair from disk with its computed scope."""
    base_dir = DOCUMENTS_DIR / workspace_id
    if not base_dir.exists():
        return []

    try:
        canonical_ids = canonical_document_ids(workspace_id)
    except Exception:
        canonical_ids = set()

    items: list[dict] = []
    for raw_file in sorted(base_dir.glob("*_raw.json")):
        document_id = raw_file.stem.removesuffix("_raw")
        chunks_file = base_dir / f"{document_id}_chunks.json"

        try:
            raw_data = json.loads(raw_file.read_text(encoding="utf-8"))
        except Exception:
            continue

        chunks = []
        if chunks_file.exists():
            try:
                chunks = json.loads(chunks_file.read_text(encoding="utf-8"))
            except Exception:
                chunks = []

        pages = raw_data.get("pages", [])
        metadata = raw_data.get("metadata", {})
        tags = raw_data.get("tags") or metadata.get("tags") or []
        filename = raw_data.get("filename", "unknown")
        first_chunk_text = "\n".join(str(chunk.get("text", "")) for chunk in chunks[:5])
        source_title = (
            metadata.get("source_title")
            or metadata.get("title")
            or metadata.get("book_title")
            or _clean_source_title(filename)
        )
        publication_year = (
            metadata.get("publication_year")
            or metadata.get("year")
            or _extract_publication_year(metadata, filename, first_chunk_text)
        )
        ingestion_status = metadata.get("ingestion_status")
        indexed_at = None
        if chunks and ingestion_status != "partial":
            indexed_at = max(
                (chunk.get("created_at") for chunk in chunks if chunk.get("created_at")),
                default=None,
            )

        items.append(
            {
                "document_id": document_id,
                "workspace_id": raw_data.get("workspace_id", workspace_id),
                "catalog_scope": _classify_catalog_scope(document_id, raw_data, canonical_ids),
                "source_type": raw_data.get("source_type", "unknown"),
                "filename": filename,
                "source_title": source_title,
                "publication_year": publication_year,
                "edition": metadata.get("edition"),
                "authors": metadata.get("authors") or metadata.get("author"),
                "publisher": metadata.get("publisher"),
                "isbn": metadata.get("isbn"),
                "page_count": metadata.get("page_count") or metadata.get("total_pages") or len(pages) or None,
                "char_count": metadata.get("char_count")
                if metadata.get("char_count") is not None
                else sum(len(page.get("text", "")) for page in pages),
                "chunk_count": len(chunks),
                "status": ingestion_status or ("parsed" if chunks else "partial"),
                "created_at": raw_data.get("created_at"),
                "chunking_strategy": chunks[0].get("strategy", "recursive") if chunks else "recursive",
                "tags": tags if isinstance(tags, list) else [],
                "embeddings_model": EMBEDDING_MODEL,
                "qdrant_collection": metadata.get("qdrant_collection"),
                "indexed_at": indexed_at,
            }
        )
    return items


def get_document_registry(workspace_id: str = "default") -> dict[str, dict]:
    """Load document metadata from the canonical raw/chunk files on disk."""
    return {
        item["document_id"]: item
        for item in _load_workspace_items(workspace_id)
        if item.get("catalog_scope") == "canonical"
    }


def list_workspace_items(workspace_id: str = "default", catalog_scope: Optional[str] = None) -> list[dict]:
    """List workspace items from disk, optionally filtered by scope."""
    items = _load_workspace_items(workspace_id)
    if catalog_scope:
        items = [item for item in items if item.get("catalog_scope") == catalog_scope]
    return items


def get_document_metadata(document_id: str, workspace_id: str = "default") -> Optional[dict]:
    """Return metadata for a single document from the workspace inventory."""
    for item in _load_workspace_items(workspace_id):
        if item.get("document_id") == document_id:
            return item
    return None


def list_document_items(
    workspace_id: str = "default",
    limit: int = 100,
    offset: int = 0,
    source_type: Optional[str] = None,
    status: Optional[str] = None,
    query: Optional[str] = None,
) -> dict:
    """Return a paginated, filterable document list from the workspace inventory."""
    registry = list(_load_workspace_items(workspace_id))

    if source_type:
        registry = [item for item in registry if item.get("source_type") == source_type]
    if status:
        registry = [item for item in registry if item.get("status") == status]
    if query:
        needle = query.lower().strip()
        registry = [
            item for item in registry
            if needle in item.get("filename", "").lower()
            or needle in item.get("document_id", "").lower()
            or any(needle in str(tag).lower() for tag in item.get("tags", []))
        ]

    registry.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    total = len(registry)
    items = registry[offset : offset + limit]
    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "workspace_id": workspace_id,
    }


def get_corpus_overview(workspace_id: str = "default") -> dict:
    """Return a compact overview of the canonical corpus on disk."""
    registry = get_document_registry(workspace_id)
    total_chunks = sum(item.get("chunk_count", 0) for item in registry.values())
    parsed_documents = sum(1 for item in registry.values() if item.get("status") == "parsed")
    partial_documents = sum(1 for item in registry.values() if item.get("status") != "parsed")

    return {
        "workspace_id": workspace_id,
        "documents": len(registry),
        "chunks": total_chunks,
        "parsed_documents": parsed_documents,
        "partial_documents": partial_documents,
    }


def get_workspace_inventory(workspace_id: str = "default") -> dict:
    """Return canonical and operational disk inventory for a workspace."""
    items = _load_workspace_items(workspace_id)
    canonical = [item for item in items if item.get("catalog_scope") == "canonical"]
    operational = [item for item in items if item.get("catalog_scope") == "operational"]

    return {
        "workspace_id": workspace_id,
        "documents": len(canonical),
        "chunks": sum(item.get("chunk_count", 0) for item in canonical),
        "parsed_documents": sum(1 for item in canonical if item.get("status") == "parsed"),
        "partial_documents": sum(1 for item in canonical if item.get("status") != "parsed"),
        "operational_documents": len(operational),
        "operational_chunks": sum(item.get("chunk_count", 0) for item in operational),
    }
