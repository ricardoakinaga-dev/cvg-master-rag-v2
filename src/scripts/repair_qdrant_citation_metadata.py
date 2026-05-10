"""
Repair Qdrant payload citation metadata from the canonical disk corpus.

This does not recalculate embeddings or modify vectors. It scrolls current
Qdrant points, matches them by chunk_id/document_id, and adds source metadata
such as document_filename, source_title, publication_year, and page_start/end.
"""
from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from qdrant_client.models import FieldCondition, Filter, MatchValue

from core.config import DOCUMENTS_DIR, QDRANT_COLLECTION
from services.chunk_io import iter_json_array_batches
from services.document_registry import get_document_metadata
from services.vector_service import get_client


def _clean_payload(payload: dict) -> dict:
    return {key: value for key, value in payload.items() if value not in (None, "", [])}


def _citation_payload(chunk: dict, doc_meta: dict) -> dict:
    filename = doc_meta.get("filename")
    source_title = doc_meta.get("source_title") or filename
    page_hint = chunk.get("page_hint")

    payload = {
        "document_filename": filename,
        "source_title": source_title,
        "source": source_title or filename,
        "source_type": doc_meta.get("source_type"),
        "catalog_scope": doc_meta.get("catalog_scope"),
        "document_page_count": doc_meta.get("page_count"),
        "publication_year": doc_meta.get("publication_year"),
        "edition": doc_meta.get("edition"),
        "authors": doc_meta.get("authors"),
        "publisher": doc_meta.get("publisher"),
        "isbn": doc_meta.get("isbn"),
        "tags": doc_meta.get("tags") or [],
    }

    if page_hint is not None:
        payload["page_start"] = page_hint
        payload["page_end"] = page_hint

    return _clean_payload(payload)


def _scroll_document_points(client, document_id: str) -> dict[str, list[int | str]]:
    by_chunk_id: dict[str, list[int | str]] = {}
    offset = None
    query_filter = Filter(
        must=[
            FieldCondition(
                key="document_id",
                match=MatchValue(value=document_id),
            )
        ]
    )

    while True:
        points, offset = client.scroll(
            collection_name=QDRANT_COLLECTION,
            scroll_filter=query_filter,
            limit=256,
            offset=offset,
            with_payload=["chunk_id"],
            with_vectors=False,
        )
        for point in points:
            chunk_id = (point.payload or {}).get("chunk_id")
            if chunk_id:
                by_chunk_id.setdefault(str(chunk_id), []).append(point.id)
        if offset is None:
            break
    return by_chunk_id


def _batched(items: list[int | str], size: int) -> Iterable[list[int | str]]:
    for start in range(0, len(items), size):
        yield items[start:start + size]


def repair_document(document_id: str, workspace_id: str, batch_size: int, dry_run: bool) -> tuple[int, int]:
    doc_meta = get_document_metadata(document_id, workspace_id) or {}
    if not doc_meta:
        return 0, 0

    client = get_client()
    point_ids_by_chunk = _scroll_document_points(client, document_id)
    chunks_path = DOCUMENTS_DIR / workspace_id / f"{document_id}_chunks.json"
    if not chunks_path.exists():
        return 0, 0

    seen_chunks = 0
    updated_points = 0
    for chunk_batch in iter_json_array_batches(chunks_path, batch_size):
        payload_to_ids: dict[tuple[tuple[str, str], ...], tuple[dict, list[int | str]]] = {}
        for chunk in chunk_batch:
            chunk_id = str(chunk.get("chunk_id") or "")
            point_ids = point_ids_by_chunk.get(chunk_id, [])
            if not point_ids:
                continue
            seen_chunks += 1
            payload = _citation_payload(chunk, doc_meta)
            key = tuple(sorted((k, repr(v)) for k, v in payload.items()))
            if key not in payload_to_ids:
                payload_to_ids[key] = (payload, [])
            payload_to_ids[key][1].extend(point_ids)

        for payload, point_ids in payload_to_ids.values():
            for ids in _batched(point_ids, batch_size):
                updated_points += len(ids)
                if not dry_run:
                    client.set_payload(
                        collection_name=QDRANT_COLLECTION,
                        payload=payload,
                        points=ids,
                        wait=True,
                    )

    return seen_chunks, updated_points


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-id", default="default")
    parser.add_argument("--document-id", action="append", dest="document_ids")
    parser.add_argument("--all", action="store_true", help="Repair every document in the workspace.")
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.all and not args.document_ids:
        parser.error("Use --all or at least one --document-id")

    if args.all:
        from services.document_registry import list_workspace_items

        document_ids = [item["document_id"] for item in list_workspace_items(args.workspace_id)]
    else:
        document_ids = args.document_ids or []

    total_chunks = 0
    total_points = 0
    for document_id in document_ids:
        chunks, points = repair_document(document_id, args.workspace_id, args.batch_size, args.dry_run)
        total_chunks += chunks
        total_points += points
        print(f"{document_id}: chunks_matched={chunks} points_updated={points}")

    mode = "DRY_RUN" if args.dry_run else "APPLIED"
    print(f"{mode}: documents={len(document_ids)} chunks_matched={total_chunks} points_updated={total_points}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
