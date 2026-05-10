"""
Re-index all documents from disk into Qdrant.
Ensures Qdrant state matches the persisted corpus.
"""
import argparse
import json
import os
import sys

from pathlib import Path

# Setup paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue
from core.config import (
    QDRANT_COLLECTION,
    QDRANT_CHECK_COMPATIBILITY,
    QDRANT_HOST,
    QDRANT_PORT,
    DOCUMENTS_DIR,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
)
from services.embedding_service import get_embeddings_batch
from services.chunker import recursive_chunk
from services.chunk_io import iter_json_array_batches
from models.schemas import Chunk, NormalizedDocument
from scripts.corpus_utils import canonical_document_ids


REINDEX_INDEX_BATCH_SIZE = max(1, int(os.getenv("INGESTION_INDEX_BATCH_SIZE", "32")))


def _create_reindex_qdrant_client(timeout: float | None = None) -> QdrantClient:
    """Create a Qdrant client while preserving monkeypatchable script tests."""
    client_kwargs = {"host": QDRANT_HOST, "port": QDRANT_PORT}
    if timeout is not None:
        client_kwargs["timeout"] = timeout
    if QDRANT_CHECK_COMPATIBILITY:
        try:
            return QdrantClient(**client_kwargs, check_compatibility=True)
        except TypeError as exc:
            if "check_compatibility" not in str(exc):
                raise
    return QdrantClient(**client_kwargs)


def _embed_and_index_chunk_batches(chunks: list[Chunk], workspace_id: str) -> int:
    """Generate embeddings and index chunks in bounded batches."""
    from services.vector_service import index_chunks

    indexed = 0
    for start in range(0, len(chunks), REINDEX_INDEX_BATCH_SIZE):
        chunk_batch = chunks[start:start + REINDEX_INDEX_BATCH_SIZE]
        texts = [chunk.text for chunk in chunk_batch]
        embeddings = get_embeddings_batch(texts)
        if len(embeddings) != len(chunk_batch):
            raise RuntimeError(
                f"embedding count mismatch: {len(embeddings)} != {len(chunk_batch)}"
            )
        index_chunks(chunk_batch, embeddings, workspace_id)
        indexed += len(chunk_batch)
    return indexed


def _embed_and_index_persisted_chunk_file(chunks_file: Path, workspace_id: str) -> int:
    """Stream a persisted chunks JSON file and index it in bounded batches."""
    from services.vector_service import index_chunks

    indexed = 0
    for chunk_dicts in iter_json_array_batches(chunks_file, REINDEX_INDEX_BATCH_SIZE):
        chunk_batch = [Chunk(**item) for item in chunk_dicts]
        texts = [chunk.text for chunk in chunk_batch]
        embeddings = get_embeddings_batch(texts)
        if len(embeddings) != len(chunk_batch):
            raise RuntimeError(
                f"embedding count mismatch: {len(embeddings)} != {len(chunk_batch)}"
            )
        index_chunks(chunk_batch, embeddings, workspace_id)
        indexed += len(chunk_batch)
    return indexed


def _count_persisted_chunks(chunks_file: Path) -> int:
    total = 0
    for batch in iter_json_array_batches(chunks_file, REINDEX_INDEX_BATCH_SIZE):
        total += len(batch)
    return total


def full_reindex(
    workspace_id: str = "default",
    recreate_collection: bool = True,
    local_only: bool = False,
    verify: bool = True,
):
    """Rebuild chunks from all raw documents and optionally re-index to Qdrant."""
    workspace_id = (workspace_id or "default").strip() or "default"
    if local_only:
        qdrant_available = False
        client = None
    else:
        try:
            client = _create_reindex_qdrant_client(timeout=None)
            qdrant_available = True
        except Exception as e:
            client = None
            qdrant_available = False
            print(f"WARN: Qdrant client unavailable, continuing local-only reindex ({e})")

    # 1. Prepare collection (or confirm local-only mode)
    if qdrant_available:
        print(f"Preparing collection '{QDRANT_COLLECTION}' for workspace '{workspace_id}'...")
    else:
        print(f"Preparing workspace '{workspace_id}' (local-only mode).")

    if qdrant_available and recreate_collection:
        print("Creating/recreating collection...")
        from services.vector_service import ensure_collection
        try:
            ensure_collection(recreate=True)
        except Exception as e:
            qdrant_available = False
            print(f"WARN: unable to prepare collection ('{QDRANT_COLLECTION}') ({e})")
            print("       Continuing in local-only mode.")
    elif qdrant_available:
        print("Skipping collection recreation (using existing collection).")
        try:
            from services.vector_service import delete_workspace_chunks
            delete_workspace_chunks(workspace_id)
            print(f"Purged existing Qdrant points for workspace '{workspace_id}'.")
        except Exception as e:
            qdrant_available = False
            print(f"WARN: unable to purge workspace '{workspace_id}' from Qdrant ({e})")
            print("       Continuing in local-only mode.")
    elif not qdrant_available:
        print("Skipping collection creation (Qdrant unavailable).")

    # 2. Find all raw JSON files
    doc_dir = DOCUMENTS_DIR / workspace_id
    if not doc_dir.exists():
        print(f"Workspace path not found: {doc_dir}")
        return 0

    raw_files = list(doc_dir.glob('*_raw.json'))
    raw_files.sort()
    canonical_ids = set()
    try:
        canonical_ids = canonical_document_ids(workspace_id)
    except Exception:
        canonical_ids = set()

    if canonical_ids:
        filtered_raw_files = [p for p in raw_files if p.stem.removesuffix("_raw") in canonical_ids]
        orphan_raw_files = [p for p in raw_files if p not in filtered_raw_files]
        if orphan_raw_files:
            print(f"WARN: skipping {len(orphan_raw_files)} non-canonical raw file(s)")
            for orphan in orphan_raw_files:
                print(f"  - {orphan.name}")
        raw_files = filtered_raw_files

    print(f"Found {len(raw_files)} documents on disk")
    if not raw_files:
        print("No documents to reindex for this workspace.")
        return 0

    total_points = 0
    for raw_file in raw_files:
        doc_id = raw_file.stem.removesuffix("_raw")
        chunks_file = doc_dir / f'{doc_id}_chunks.json'

        print(f"\nProcessing {doc_id}...")

        # Load normalized doc
        try:
            with open(raw_file, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print(f"  WARN: failed to load {raw_file.name}: {e}")
            continue

        normalized = NormalizedDocument(**raw_data)

        pdf_uses_persisted_chunks = normalized.source_type == "pdf"
        if pdf_uses_persisted_chunks:
            if not chunks_file.exists():
                print(f"  WARN: PDF without persisted chunks, skipping unsafe raw re-chunk: {doc_id}")
                continue
            try:
                chunk_count = _count_persisted_chunks(chunks_file)
            except (OSError, json.JSONDecodeError, TypeError, ValueError) as e:
                print(f"  WARN: failed to load persisted PDF chunks for {doc_id}: {e}")
                continue
            print("  PDF: using persisted chunks instead of raw page re-chunk")
        else:
            # Re-chunk
            chunks = recursive_chunk(
                normalized,
                chunk_size=CHUNK_SIZE,
                overlap=CHUNK_OVERLAP,
                workspace_id=workspace_id
            )
            chunk_count = len(chunks)
        print(f"  Chunks: {chunk_count}")

        # Save chunks (with correct offsets)
        if not pdf_uses_persisted_chunks:
            if chunks_file.exists():
                chunks_file.unlink()
            with open(chunks_file, "w", encoding="utf-8") as f:
                json.dump([c.model_dump() for c in chunks], f, ensure_ascii=False)
            print(f"  Chunks saved to {chunks_file.name}")

        if not qdrant_available:
            continue

        try:
            if pdf_uses_persisted_chunks:
                indexed_count = _embed_and_index_persisted_chunk_file(chunks_file, workspace_id)
            else:
                indexed_count = _embed_and_index_chunk_batches(chunks, workspace_id)
            total_points += indexed_count
            print(f"  Indexed {indexed_count} points")
        except Exception as e:
            qdrant_available = False
            print(f"  WARN: index failed for {doc_id}: {e}")
            print("       Continuing local-only mode for remaining docs.")

    print(f"\n=== Reindex Complete ===")
    print(f"Total documents: {len(raw_files)}")
    print(f"Total points indexed: {total_points}")

    if not qdrant_available or client is None or not verify:
        print("SKIP: verification requires Qdrant; local chunk regeneration completed.")
        return total_points

    # Verify
    try:
        count = client.count(
            collection_name=QDRANT_COLLECTION,
            count_filter=Filter(
                must=[
                    FieldCondition(
                        key="workspace_id",
                        match=MatchValue(value=workspace_id),
                    )
                ]
            ),
            exact=True,
        ).count
    except Exception as e:
        print(f"VERIFY ERROR: unable to count workspace '{workspace_id}' in collection '{QDRANT_COLLECTION}': {e}")
        return total_points

    print(f"Qdrant workspace points count: {count}")

    if count == total_points:
        print("VERIFICATION: PASS - workspace Qdrant matches disk")
    else:
        print("VERIFICATION: FAIL - workspace Qdrant/Disk mismatch!")

    return total_points


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for the reindex script."""
    parser = argparse.ArgumentParser(
        description="Reindex raw corpus files and rebuild chunks/indexes."
    )
    parser.add_argument(
        "workspace_id",
        nargs="?",
        default="default",
        help="Workspace to reindex (default: default)"
    )
    parser.add_argument(
        "--workspace-id",
        dest="workspace_id_flag",
        default=None,
        help="Alternative explicit workspace flag (overrides positional arg)."
    )
    parser.add_argument(
        "--local-only",
        action="store_true",
        help="Regenerate chunk files without touching Qdrant."
    )
    parser.add_argument(
        "--skip-recreate",
        action="store_true",
        help="Do not recreate collection before indexing in Qdrant."
    )
    parser.add_argument(
        "--skip-verify",
        action="store_true",
        help="Skip Qdrant post-run verification."
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run reindex operation from CLI arguments."""
    args = parse_args(argv)
    workspace = args.workspace_id_flag or args.workspace_id
    return full_reindex(
        workspace_id=workspace,
        recreate_collection=not args.skip_recreate,
        local_only=args.local_only,
        verify=not args.skip_verify,
    )


if __name__ == '__main__':
    main()
