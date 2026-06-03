"""
Ingestion Service — orchestrates upload → parse → chunk → index
"""
import os
import json
import uuid
import time as time_module
import gc
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Iterator, Optional

import pdfplumber

from models.schemas import (
    DocumentUploadResponse, DocumentMetadata,
    NormalizedDocument, Chunk, SearchRequest
)
from services.document_parser import parse_document, save_raw_json, ParseError, UnsupportedFormatError
from services.chunker import recursive_chunk, semantic_chunk
from services.embedding_service import get_embeddings_batch
from services.vector_service import (
    index_chunks,
    delete_document_chunks,
    validate_qdrant_collection_name,
)
from services.chunk_io import append_json_array_items, iter_json_array_batches
from core.config import DOCUMENTS_DIR, CHUNKS_DIR, CHUNK_SIZE, CHUNK_OVERLAP, EMBEDDING_DIM
from scripts.corpus_utils import canonical_document_ids
from services.admin_service import get_tenant_by_workspace


class IngestionError(Exception):
    pass


VALID_CHUNKING_STRATEGIES = {"recursive", "semantic"}
INGESTION_INDEX_BATCH_SIZE = max(1, int(os.getenv("INGESTION_INDEX_BATCH_SIZE", "32")))
PDF_CONTROLLED_INGESTION_ENABLED = os.getenv("PDF_CONTROLLED_INGESTION_ENABLED", "true").lower() not in {
    "0",
    "false",
    "no",
    "off",
}
PDF_INGESTION_PAGE_BATCH_SIZE = max(1, int(os.getenv("PDF_INGESTION_PAGE_BATCH_SIZE", "10")))
PDF_INGESTION_MEMORY_SAMPLES_LIMIT = max(0, int(os.getenv("PDF_INGESTION_MEMORY_SAMPLES_LIMIT", "20")))


def _is_operational_upload(file_path: Path) -> bool:
    """Uploads staged via the API live under a workspace uploads/ directory."""
    return "/uploads/" in str(file_path).replace("\\", "/")


def _tenant_retention_policy(workspace_id: str) -> tuple[str, int]:
    """Return the operational upload retention policy for a workspace."""
    tenant = get_tenant_by_workspace(workspace_id) or {}
    mode = tenant.get("operational_retention_mode", "keep_latest")
    if mode not in {"keep_latest", "keep_all"}:
        mode = "keep_latest"
    try:
        hours = int(tenant.get("operational_retention_hours", 24) or 24)
    except Exception:
        hours = 24
    return mode, max(1, hours)


def _prune_previous_operational_uploads(workspace_id: str, filename: str, keep_document_id: str) -> int:
    """Keep only the newest operational upload revision for a given filename/workspace."""
    doc_dir = DOCUMENTS_DIR / workspace_id
    if not doc_dir.exists():
        return 0

    try:
        canonical_ids = canonical_document_ids(workspace_id)
    except Exception:
        canonical_ids = set()
    retention_mode, retention_hours = _tenant_retention_policy(workspace_id)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=retention_hours)

    removed = 0
    candidates: list[tuple[str, Path, Path, str]] = []
    for raw_file in sorted(doc_dir.glob("*_raw.json")):
        document_id = raw_file.stem.removesuffix("_raw")
        if document_id == keep_document_id:
            continue
        if document_id in canonical_ids:
            continue
        try:
            payload = json.loads(raw_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        raw_json_path = str(payload.get("raw_json_path", "") or "").replace("\\", "/")
        if "/uploads/" not in raw_json_path:
            continue
        created_at = str(payload.get("created_at", "") or "")
        should_prune = False
        if retention_mode == "keep_latest" and payload.get("filename") == filename:
            should_prune = True
        else:
            try:
                created_at_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                should_prune = created_at_dt < cutoff
            except Exception:
                should_prune = False
        if should_prune:
            qdrant_collection = (
                payload.get("metadata", {}).get("qdrant_collection")
                or payload.get("metadata", {}).get("collection")
            )
            candidates.append((document_id, raw_file, doc_dir / f"{document_id}_chunks.json", created_at, qdrant_collection))

    candidates.sort(key=lambda item: item[3], reverse=True)
    for document_id, raw_file, chunks_file, _created_at, qdrant_collection in candidates:
        try:
            delete_document_chunks(document_id, collection_name=qdrant_collection)
        except Exception:
            pass
        try:
            raw_file.unlink(missing_ok=True)
        except Exception:
            pass
        try:
            chunks_file.unlink(missing_ok=True)
        except Exception:
            pass
        removed += 1
    return removed


def _embedding_is_valid(emb: object) -> bool:
    """Return True if emb is a list of the correct embedding dimension."""
    return (
        isinstance(emb, list)
        and len(emb) == EMBEDDING_DIM
        and all(isinstance(x, (int, float)) for x in emb)
    )


def _restore_embeddings_if_needed(chunks: list[dict]) -> tuple[list[dict], bool]:
    """
    Validate embeddings per-chunk; recover from Qdrant or regenerate if missing/invalid.

    Recovery priority:
      1. Already valid embeddings in chunk dicts → return as-is ("original")
      2. Embeddings in Qdrant (read by chunk_id) → use directly (no API call, "original")
      3. get_embeddings_batch via API → if succeeds ("regenerated"), if fails → zeros

    Per-chunk validation: each chunk must have a valid embedding field (list of
    EMBEDDING_DIM floats). If ANY chunk is invalid or missing, ALL chunks are
    recovered or regenerated.

    Count mismatch protection: if get_embeddings_batch returns a different count
    than the number of chunks, raise RuntimeError — no silent truncation or padding.

    Returns (updated_chunks, were_regenerated):
      - updated_chunks: chunks with valid embeddings (Qdrant or regenerated)
      - were_regenerated: True if embeddings were regenerated via API
                           False if they came from Qdrant or were already valid
    """
    if not chunks:
        return chunks, False

    # Per-chunk validation
    all_valid = all(_embedding_is_valid(c.get("embedding")) for c in chunks)
    if all_valid:
        return chunks, False  # nothing to do

    # At least one chunk is invalid or missing — try Qdrant first (no API needed)
    chunk_ids = [c.get("chunk_id") for c in chunks]
    workspace_id = chunks[0].get("workspace_id", "default")

    qdrant_embeddings: dict[str, list[float]] = {}
    try:
        qdrant_embeddings = _get_embeddings_from_qdrant(chunk_ids, workspace_id)
    except Exception:
        # Qdrant read failed — will fall through to API regeneration
        qdrant_embeddings = {}

    # Classify each chunk: has_valid_qdrant_emb | needs_api | already_valid
    chunk_indices_from_qdrant: list[int] = []   # indices whose Qdrant embedding is valid
    chunk_indices_needed: list[tuple[int, dict]] = []  # (index, chunk) that need API

    for i, c in enumerate(chunks):
        qdrant_emb = qdrant_embeddings.get(c.get("chunk_id"))
        if qdrant_emb is not None and _embedding_is_valid(qdrant_emb):
            chunk_indices_from_qdrant.append(i)
        else:
            chunk_indices_needed.append((i, c))

    if not chunk_indices_needed:
        # All embeddings found in Qdrant and all are valid — use them directly
        updated_chunks = []
        for i, c in enumerate(chunks):
            c_copy = dict(c)
            c_copy["embedding"] = qdrant_embeddings[c["chunk_id"]]
            updated_chunks.append(c_copy)
        return updated_chunks, False  # not regenerated, came from valid Qdrant embeddings

    # Some chunks are missing or have invalid embeddings — try API for those
    # Valid Qdrant embeddings are preserved; invalid/missing ones go to API

    # Regenerate only the missing embeddings via API
    regenerated: dict[int, list[float]] = {}
    if chunk_indices_needed:
        texts_for_api = [c.get("text", "")[:8000] for _, c in chunk_indices_needed]
        try:
            api_embeddings = get_embeddings_batch(texts_for_api)
        except Exception:
            # API also failed — return chunks as-is so the caller indexes zeros
            return chunks, False

        if len(api_embeddings) != len(chunk_indices_needed):
            raise RuntimeError(
                f"Embedding count mismatch: got {len(api_embeddings)} embeddings "
                f"for {len(chunk_indices_needed)} missing chunks. Refusing to index with truncated data."
            )

        for (i, _), emb in zip(chunk_indices_needed, api_embeddings):
            if not _embedding_is_valid(emb):
                raise RuntimeError(
                    f"Regenerated embedding for chunk {chunks[i].get('chunk_id')} is invalid "
                    f"(length {len(emb) if isinstance(emb, list) else type(emb)}). "
                    f"Expected {EMBEDDING_DIM}-dim float list."
                )
            regenerated[i] = emb

    # Build final chunks: valid Qdrant embeddings + regenerated embeddings
    valid_qdrant_indices = set(chunk_indices_from_qdrant)
    updated_chunks = []
    any_regenerated = bool(regenerated)
    for i, c in enumerate(chunks):
        c_copy = dict(c)
        if i in regenerated:
            c_copy["embedding"] = regenerated[i]
        elif i in valid_qdrant_indices:
            c_copy["embedding"] = qdrant_embeddings[c["chunk_id"]]
        updated_chunks.append(c_copy)

    return updated_chunks, any_regenerated


def _get_embeddings_from_qdrant(chunk_ids: list[str], workspace_id: str) -> dict[str, list[float]]:
    """
    Read dense embeddings directly from Qdrant for the given chunk_ids.

    Uses the same point ID scheme as index_chunks:
      point_id = abs(hash(chunk_id)) % (2**63)

    Returns a dict mapping chunk_id -> embedding vector.
    Raises Exception if Qdrant is unavailable.
    """
    if not chunk_ids:
        return {}

    from services.vector_service import get_client, QDRANT_COLLECTION

    client = get_client()

    # Compute point IDs using the same formula as index_chunks
    point_ids = [abs(hash(cid)) % (2**63) for cid in chunk_ids]

    # Retrieve with vectors
    records = client.retrieve(
        collection_name=QDRANT_COLLECTION,
        ids=point_ids,
        with_vectors=True,
    )

    # Build chunk_id -> embedding map
    result: dict[str, list[float]] = {}
    for record in records:
        # The payload contains chunk_id
        payload = record.payload or {}
        chunk_id = payload.get("chunk_id")
        if chunk_id and record.vector and "dense" in record.vector:
            result[chunk_id] = record.vector["dense"]

    return result


def _chunk_document(normalized_doc, workspace_id: str, strategy: str = "recursive"):
    """Dispatch to the appropriate chunker based on strategy."""
    if strategy not in VALID_CHUNKING_STRATEGIES:
        raise ValueError(
            f"Invalid chunking_strategy '{strategy}'. "
            f"Must be one of: {', '.join(sorted(VALID_CHUNKING_STRATEGIES))}"
        )
    if strategy == "semantic":
        return semantic_chunk(
            normalized_doc,
            chunk_size=CHUNK_SIZE,
            overlap=CHUNK_OVERLAP,
            workspace_id=workspace_id,
        )
    return recursive_chunk(
        normalized_doc,
        chunk_size=CHUNK_SIZE,
        overlap=CHUNK_OVERLAP,
        workspace_id=workspace_id,
    )


def _embed_and_index_chunks_in_batches(
    chunks: list[Chunk],
    workspace_id: str,
    ingestion_id: str | None = None,
    qdrant_collection: str | None = None,
) -> None:
    """Generate embeddings and index chunks in small batches to cap memory usage."""
    for start in range(0, len(chunks), INGESTION_INDEX_BATCH_SIZE):
        chunk_batch = chunks[start:start + INGESTION_INDEX_BATCH_SIZE]
        texts = [chunk.text for chunk in chunk_batch]
        embeddings = get_embeddings_batch(texts)
        if len(embeddings) != len(chunk_batch):
            raise IngestionError(
                f"Mismatch: {len(chunk_batch)} chunks mas {len(embeddings)} embeddings"
            )
        index_chunks(
            chunk_batch,
            embeddings,
            workspace_id,
            ingestion_id=ingestion_id,
            collection_name=qdrant_collection,
        )


def _coerce_embedding(embedding: object) -> list[float]:
    if _embedding_is_valid(embedding):
        return embedding
    return [0.0] * EMBEDDING_DIM


def _validate_json_file(path: Path) -> None:
    with open(path, "r", encoding="utf-8") as f:
        json.load(f)


def _atomic_promote_json(temp_path: Path, final_path: Path) -> None:
    _validate_json_file(temp_path)
    temp_path.replace(final_path)


def _write_raw_json_temp(normalized: NormalizedDocument, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    final_path = output_dir / f"{normalized.document_id}_raw.json"
    temp_path = final_path.with_suffix(final_path.suffix + ".tmp")
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(normalized.model_dump(), f, ensure_ascii=False, indent=2)
        f.write("\n")
    _validate_json_file(temp_path)
    return temp_path, final_path


def _save_raw_json_atomic(normalized: NormalizedDocument, output_dir: Path) -> Path:
    temp_path, final_path = _write_raw_json_temp(normalized, output_dir)
    _atomic_promote_json(temp_path, final_path)
    return final_path


def _reindex_persisted_chunks_file(
    *,
    document_id: str,
    workspace_id: str,
    chunks_path: Path,
    qdrant_collection: str | None = None,
) -> tuple[int, str, bool]:
    """Restore/index a persisted chunks file in bounded batches."""
    temp_path = chunks_path.with_suffix(chunks_path.suffix + ".reindex_tmp")
    total_chunks = 0
    any_regenerated = False
    any_degraded = False

    with open(temp_path, "w", encoding="utf-8") as out:
        out.write("[\n")
        first_item = True
        for chunk_batch in iter_json_array_batches(chunks_path, INGESTION_INDEX_BATCH_SIZE):
            updated_batch, were_regenerated = _restore_embeddings_if_needed(chunk_batch)
            any_regenerated = any_regenerated or were_regenerated
            any_degraded = any_degraded or any(
                not _embedding_is_valid(chunk.get("embedding")) for chunk in updated_batch
            )
            first_item = append_json_array_items(out, updated_batch, first_item)
            total_chunks += len(updated_batch)
        out.write("\n]\n")

    if any_regenerated:
        embedding_status = "regenerated"
    elif any_degraded:
        embedding_status = "degraded_zero_fallback"
    else:
        embedding_status = "original"

    qdrant_synced = True
    try:
        delete_document_chunks(document_id, collection_name=qdrant_collection)
    except Exception:
        qdrant_synced = False

    if qdrant_synced:
        try:
            for chunk_batch in iter_json_array_batches(temp_path, INGESTION_INDEX_BATCH_SIZE):
                chunk_objs = [Chunk(**chunk) for chunk in chunk_batch]
                embeddings = [_coerce_embedding(chunk.get("embedding")) for chunk in chunk_batch]
                index_chunks(chunk_objs, embeddings, workspace_id, collection_name=qdrant_collection)
        except Exception:
            qdrant_synced = False

    temp_path.replace(chunks_path)
    return total_chunks, embedding_status, qdrant_synced


def _persist_chunks_incrementally(chunks_file: Path, chunks: list[Chunk], first_item: bool) -> bool:
    """Append chunk metadata to an already-open JSON array without retaining all chunks."""
    with open(chunks_file, "a", encoding="utf-8") as f:
        for chunk in chunks:
            if not first_item:
                f.write(",\n")
            json.dump(chunk.model_dump(), f, ensure_ascii=False)
            first_item = False
    return first_item


def _renumber_chunks(
    chunks: list[Chunk],
    document_id: str,
    start_index: int,
    char_offset: int,
) -> list[Chunk]:
    """Convert per-batch chunk positions into document-level chunk ids and offsets."""
    renumbered: list[Chunk] = []
    for local_index, chunk in enumerate(chunks):
        chunk_index = start_index + local_index
        renumbered.append(
            chunk.model_copy(
                update={
                    "chunk_id": f"chunk_{document_id}_{chunk_index:04d}",
                    "chunk_index": chunk_index,
                    "start_char": chunk.start_char + char_offset,
                    "end_char": chunk.end_char + char_offset,
                }
            )
        )
    return renumbered


def _current_rss_mb() -> float | None:
    """Return current resident memory in MB on Linux, or None when unavailable."""
    try:
        with open("/proc/self/status", encoding="utf-8") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    parts = line.split()
                    if len(parts) >= 2:
                        return round(int(parts[1]) / 1024, 2)
    except Exception:
        return None
    return None


def _clear_pdf_page_cache(page: object) -> None:
    """Release pdfplumber/pdfminer page caches after extracting a page."""
    try:
        flush_cache = getattr(page, "flush_cache", None)
        if callable(flush_cache):
            flush_cache()
    except Exception:
        pass
    try:
        get_textmap = getattr(page, "get_textmap", None)
        cache_clear = getattr(get_textmap, "cache_clear", None)
        if callable(cache_clear):
            cache_clear()
    except Exception:
        pass


def _get_pdf_page_count(file_path: Path) -> int:
    """Count PDF pages without extracting text/layout for the whole document."""
    with pdfplumber.open(file_path) as pdf:
        return len(pdf.pages)


def _iter_pdf_text_batches(
    file_path: Path,
    page_count: int,
    batch_size: int,
) -> Iterator[list[dict]]:
    """
    Yield text batches by reopening only the requested page range.

    Reopening per batch is slower than keeping the full PDF object open, but it
    prevents page/layout caches from accumulating across a long book ingestion.
    """
    for start_page in range(1, page_count + 1, batch_size):
        end_page = min(page_count, start_page + batch_size - 1)
        page_numbers = list(range(start_page, end_page + 1))
        page_batch: list[dict] = []
        with pdfplumber.open(file_path, pages=page_numbers) as pdf:
            for offset, page in enumerate(pdf.pages):
                page_number = int(getattr(page, "page_number", start_page + offset) or start_page + offset)
                try:
                    text = page.extract_text() or ""
                finally:
                    _clear_pdf_page_cache(page)
                page_batch.append({"page_number": page_number, "text": text})
        gc.collect()
        yield page_batch


def _ingest_pdf_controlled(
    file_path: Path,
    workspace_id: str,
    original_filename: Optional[str],
    chunking_strategy: str,
    start_time: float,
    ingestion_id: str | None = None,
    qdrant_collection: str | None = None,
) -> DocumentUploadResponse:
    """Ingest PDFs page-batch by page-batch to avoid loading the full book."""
    if chunking_strategy not in VALID_CHUNKING_STRATEGIES:
        raise IngestionError(
            f"Invalid chunking_strategy '{chunking_strategy}'. "
            f"Must be one of: {', '.join(sorted(VALID_CHUNKING_STRATEGIES))}"
        )

    doc_dir = DOCUMENTS_DIR / workspace_id
    doc_dir.mkdir(parents=True, exist_ok=True)

    doc_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    filename = original_filename or file_path.name
    catalog_scope = "operational" if _is_operational_upload(file_path) else "canonical"
    collection = validate_qdrant_collection_name(qdrant_collection)
    raw_json_path = str(doc_dir / f"{doc_id}_raw.json")
    chunks_file = doc_dir / f"{doc_id}_chunks.json"
    chunks_temp_file = chunks_file.with_suffix(chunks_file.suffix + ".tmp")

    total_chars = 0
    char_offset = 0
    page_count = 0
    chunk_count = 0
    response_status = "parsed"
    telemetry_status = "success"
    telemetry_error = None
    indexing_enabled = True
    first_chunk_item = True
    rss_peak_mb = _current_rss_mb()
    memory_samples: list[dict] = []

    try:
        chunks_temp_file.write_text("[\n", encoding="utf-8")
        page_count = _get_pdf_page_count(file_path)

        for batch_index, page_batch in enumerate(
            _iter_pdf_text_batches(file_path, page_count, PDF_INGESTION_PAGE_BATCH_SIZE),
            start=1,
        ):
            batch_started = time_module.time()
            if not page_batch:
                continue
            batch_start_offset = char_offset
            batch_chars = sum(len(page["text"]) for page in page_batch)
            total_chars += batch_chars
            char_offset += batch_chars + len(page_batch)

            normalized_batch = NormalizedDocument(
                document_id=doc_id,
                source_type="pdf",
                filename=filename,
                workspace_id=workspace_id,
                created_at=created_at,
                pages=page_batch,
                sections=[],
                metadata={"page_count": page_count},
                raw_json_path=raw_json_path,
            )
            batch_chunks = _chunk_document(normalized_batch, workspace_id, chunking_strategy)
            batch_chunks = _renumber_chunks(batch_chunks, doc_id, chunk_count, batch_start_offset)
            first_chunk_item = _persist_chunks_incrementally(chunks_temp_file, batch_chunks, first_chunk_item)
            chunk_count += len(batch_chunks)
            batch_points_indexed = 0
            batch_status = "success"
            batch_error = None

            if indexing_enabled and batch_chunks:
                try:
                    if ingestion_id:
                        _embed_and_index_chunks_in_batches(
                            batch_chunks,
                            workspace_id,
                            ingestion_id=ingestion_id,
                            qdrant_collection=collection,
                        )
                    else:
                        _embed_and_index_chunks_in_batches(
                            batch_chunks,
                            workspace_id,
                            qdrant_collection=collection,
                        )
                    batch_points_indexed = len(batch_chunks)
                except Exception as e:
                    response_status = "partial"
                    telemetry_status = "partial"
                    telemetry_error = f"Erro ao gerar embeddings ou indexar no Qdrant: {e}"
                    batch_status = "partial"
                    batch_error = str(e)
                    indexing_enabled = False

            rss_mb = _current_rss_mb()
            if rss_mb is not None:
                rss_peak_mb = max(rss_peak_mb or rss_mb, rss_mb)
                if len(memory_samples) < PDF_INGESTION_MEMORY_SAMPLES_LIMIT:
                    memory_samples.append(
                        {
                            "batch_index": batch_index,
                            "page_start": page_batch[0]["page_number"],
                            "page_end": page_batch[-1]["page_number"],
                            "rss_mb": rss_mb,
                            "chunks_total": chunk_count,
                        }
                    )

            batch_duration_ms = int((time_module.time() - batch_started) * 1000)
            try:
                from services.telemetry_service import get_telemetry
                get_telemetry().log_ingestion_batch(
                    ingestion_id=ingestion_id,
                    document_id=doc_id,
                    workspace_id=workspace_id,
                    filename=filename,
                    batch_index=batch_index,
                    page_start=page_batch[0]["page_number"],
                    page_end=page_batch[-1]["page_number"],
                    chars_extracted=batch_chars,
                    chunks_created=len(batch_chunks),
                    embeddings_created=batch_points_indexed,
                    points_indexed=batch_points_indexed,
                    rss_mb=rss_mb,
                    rss_peak_mb=rss_peak_mb,
                    duration_ms=batch_duration_ms,
                    status=batch_status,
                    error=batch_error,
                )
            except Exception:
                pass

            if ingestion_id:
                try:
                    from services.ingestion_job_service import record_ingestion_heartbeat
                    record_ingestion_heartbeat(
                        ingestion_id,
                        page_count=page_count,
                        pages_processed=page_batch[-1]["page_number"],
                        chunks_written=chunk_count,
                        qdrant_points_written=max(0, chunk_count if indexing_enabled else chunk_count - len(batch_chunks)),
                        rss_peak_mb=rss_peak_mb,
                        last_batch_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    )
                except Exception:
                    pass

            del normalized_batch
            del batch_chunks
            del page_batch
            gc.collect()
    except Exception as e:
        try:
            chunks_temp_file.unlink(missing_ok=True)
        except Exception:
            pass
        if isinstance(e, IngestionError):
            raise
        raise IngestionError(f"Erro no parse controlado do PDF: {e}")
    finally:
        if chunks_temp_file.exists():
            with open(chunks_temp_file, "a", encoding="utf-8") as f:
                f.write("\n]\n")

    if total_chars == 0:
        try:
            chunks_temp_file.unlink(missing_ok=True)
        except Exception:
            pass
        raise IngestionError("PDF não contém texto extraível (pode ser escaneado).")
    if chunk_count == 0:
        try:
            chunks_temp_file.unlink(missing_ok=True)
        except Exception:
            pass
        raise IngestionError("Chunking não gerou nenhum chunk.")

    normalized = NormalizedDocument(
        document_id=doc_id,
        source_type="pdf",
        filename=filename,
        workspace_id=workspace_id,
        created_at=created_at,
        pages=[],
        sections=[],
        metadata={
            "catalog_scope": catalog_scope,
            "ingestion_status": response_status,
            "ingestion_mode": "controlled_pdf",
            "raw_text_persisted": False,
            "source_path": str(file_path),
            "ingestion_id": ingestion_id,
            "qdrant_collection": collection,
            "page_count": page_count,
            "char_count": total_chars,
            "chunk_count": chunk_count,
            "page_batch_size": PDF_INGESTION_PAGE_BATCH_SIZE,
            "index_batch_size": INGESTION_INDEX_BATCH_SIZE,
            "rss_peak_mb": rss_peak_mb,
            "memory_samples": memory_samples,
        },
        raw_json_path=raw_json_path,
    )
    try:
        raw_temp_file, raw_final_file = _write_raw_json_temp(normalized, doc_dir)
        _validate_json_file(chunks_temp_file)
        raw_temp_file.replace(raw_final_file)
        chunks_temp_file.replace(chunks_file)
    except Exception as e:
        response_status = "partial"
        telemetry_status = "partial"
        telemetry_error = telemetry_error or f"Erro ao salvar raw JSON: {e}"
        try:
            chunks_temp_file.unlink(missing_ok=True)
        except Exception:
            pass
        try:
            raw_temp_file.unlink(missing_ok=True)
        except Exception:
            pass
        try:
            chunks_file.unlink(missing_ok=True)
        except Exception:
            pass
        try:
            raw_final_file.unlink(missing_ok=True)
        except Exception:
            pass

    pruned_upload_revisions = 0
    if catalog_scope == "operational":
        try:
            pruned_upload_revisions = _prune_previous_operational_uploads(
                workspace_id=workspace_id,
                filename=filename,
                keep_document_id=doc_id,
            )
        except Exception:
            pruned_upload_revisions = 0

    elapsed_ms = int((time_module.time() - start_time) * 1000)
    try:
        from services.telemetry_service import get_telemetry
        tel = get_telemetry()
        tel.log_ingestion(
            document_id=doc_id,
            workspace_id=workspace_id,
            source_type="pdf",
            filename=filename,
            status=telemetry_status,
            chunk_count=chunk_count,
            processing_time_ms=elapsed_ms,
            error=telemetry_error,
            embedding_status="regenerated" if indexing_enabled else "degraded_zero_fallback",
        )
    except Exception:
        pass

    return DocumentUploadResponse(
        document_id=doc_id,
        status=response_status,
        catalog_scope=catalog_scope,
        source_type="pdf",
        filename=filename,
        page_count=page_count,
        char_count=total_chars,
        chunk_count=chunk_count,
        created_at=created_at,
        chunking_strategy=chunking_strategy,
        qdrant_collection=collection,
    )


def ingest_document(
    file_path: Path,
    workspace_id: str = "default",
    original_filename: Optional[str] = None,
    chunking_strategy: str = "recursive",
    ingestion_id: str | None = None,
    qdrant_collection: str | None = None,
) -> DocumentUploadResponse:
    """
    Full ingestion pipeline:
    1. Parse document
    2. Save raw JSON
    3. Chunk text (recursive or semantic based on chunking_strategy)
    4. Generate embeddings
    5. Index in Qdrant

    Returns DocumentUploadResponse with document_id and metadata.
    """
    start_time = time_module.time()
    collection = validate_qdrant_collection_name(qdrant_collection)

    # Validate workspace directory
    doc_dir = DOCUMENTS_DIR / workspace_id
    doc_dir.mkdir(parents=True, exist_ok=True)

    if PDF_CONTROLLED_INGESTION_ENABLED and file_path.suffix.lower() == ".pdf":
        return _ingest_pdf_controlled(
            file_path=file_path,
            workspace_id=workspace_id,
            original_filename=original_filename,
            chunking_strategy=chunking_strategy,
            start_time=start_time,
            ingestion_id=ingestion_id,
            qdrant_collection=collection,
        )

    # ── Step 1: Parse ─────────────────────────────────────────
    try:
        normalized, metadata = parse_document(file_path, workspace_id)
    except UnsupportedFormatError as e:
        raise IngestionError(str(e))
    except ParseError as e:
        raise IngestionError(f"Erro no parse: {e}")
    except Exception as e:
        raise IngestionError(f"Erro inesperado no parse: {e}")

    doc_id = metadata.document_id
    catalog_scope = "operational" if _is_operational_upload(file_path) else "canonical"
    normalized.metadata["catalog_scope"] = catalog_scope
    normalized.metadata["qdrant_collection"] = collection

    # ── Step 2: Save raw JSON ───────────────────────────────────
    try:
        raw_json_path = _save_raw_json_atomic(normalized, doc_dir)
        metadata.status = "parsed"
    except Exception as e:
        metadata.status = "partial"
        # Continue even if save fails

    # ── Step 3: Chunk ───────────────────────────────────────────
    try:
        chunks = _chunk_document(normalized, workspace_id, chunking_strategy)
    except Exception as e:
        raise IngestionError(f"Erro no chunking: {e}")

    if not chunks:
        raise IngestionError("Chunking não gerou nenhum chunk.")

    response_status = "parsed"
    response_chunk_count = len(chunks)
    telemetry_status = "success"
    telemetry_error = None

    # ── Step 4/5: Generate embeddings and index in Qdrant ─────
    try:
        _embed_and_index_chunks_in_batches(
            chunks,
            workspace_id,
            ingestion_id=ingestion_id,
            qdrant_collection=collection,
        )
    except Exception as e:
        metadata.status = "partial"
        response_status = "partial"
        telemetry_status = "partial"
        telemetry_error = f"Erro ao gerar embeddings ou indexar no Qdrant: {e}"

    # Persist the ingestion status into the canonical raw JSON so the registry
    # can distinguish partial ingestion from a fully indexed document.
    try:
        normalized.metadata["ingestion_status"] = response_status
        normalized.metadata["chunk_count"] = len(chunks)
        _save_raw_json_atomic(normalized, doc_dir)
    except Exception:
        pass  # Non-critical

    # ── Save chunk metadata ───────────────────────────────────
    try:
        chunks_file = doc_dir / f"{doc_id}_chunks.json"
        chunks_temp_file = chunks_file.with_suffix(chunks_file.suffix + ".tmp")
        with open(chunks_temp_file, "w", encoding="utf-8") as f:
            json.dump([c.model_dump() for c in chunks], f, ensure_ascii=False)
        _atomic_promote_json(chunks_temp_file, chunks_file)
    except Exception:
        try:
            chunks_temp_file.unlink(missing_ok=True)
        except Exception:
            pass
        pass  # Non-critical

    pruned_upload_revisions = 0
    if catalog_scope == "operational":
        try:
            pruned_upload_revisions = _prune_previous_operational_uploads(
                workspace_id=workspace_id,
                filename=original_filename or file_path.name,
                keep_document_id=doc_id,
            )
        except Exception:
            pruned_upload_revisions = 0

    # ── Step 4: Log ingestion event ────────────────────────
    elapsed_ms = int((time_module.time() - start_time) * 1000)
    try:
        from services.telemetry_service import get_telemetry
        tel = get_telemetry()
        tel.log_ingestion(
            document_id=doc_id,
            workspace_id=workspace_id,
            source_type=normalized.source_type,
            filename=original_filename or file_path.name,
            status=telemetry_status,
            chunk_count=response_chunk_count,
            processing_time_ms=elapsed_ms,
            error=telemetry_error,
            embedding_status="regenerated",
        )
    except Exception:
        pass  # Non-critical

    return DocumentUploadResponse(
        document_id=doc_id,
        status=response_status,
        catalog_scope=catalog_scope,
        source_type=metadata.source_type,
        filename=metadata.filename,
        page_count=metadata.page_count,
        char_count=metadata.char_count,
        chunk_count=response_chunk_count,
        created_at=metadata.created_at,
        chunking_strategy=chunking_strategy,
        qdrant_collection=collection,
    )


def reindex_document(
    document_id: str,
    workspace_id: str = "default",
    chunking_strategy: str = "recursive",
    chunks: list[dict] | None = None,
) -> tuple[int, str, int]:
    """
    Returns tuple of (chunk_count, embedding_status, processing_time_ms).
    """
    """
    Re-chunk and re-index a document (useful after changing chunking strategy).

    If `chunks` is provided (list of chunk dicts, e.g. from a backup file), those
    exact chunks are used — no re-chunking. This is used for faithful restoration
    of the original state.

    Returns a tuple of (chunk_count, embedding_status):
      - embedding_status in {"original", "regenerated", "degraded_zero_fallback"}
        "original" — chunks had valid embeddings (backup was good)
        "regenerated" — embeddings were regenerated from chunk text
        "degraded_zero_fallback" — backup had no valid embeddings and
                                   get_embeddings_batch also failed; zeros indexed

    Parameters:
        chunks: optional pre-serialized chunks (e.g. from *_chunks_backup.json).
                If provided, chunking_strategy is ignored and these chunks are
                indexed directly into Qdrant and written to the chunks file.
    """
    start_time = time_module.time()
    doc_dir = DOCUMENTS_DIR / workspace_id
    if not doc_dir.exists() and DOCUMENTS_DIR.name == workspace_id:
        doc_dir = DOCUMENTS_DIR
    raw_path = doc_dir / f"{document_id}_raw.json"

    def _persist_raw_ingestion_status(status: str) -> None:
        try:
            with open(raw_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            payload.setdefault("metadata", {})
            payload["metadata"]["ingestion_status"] = status
            with open(raw_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    if chunks is None:
        # Normal path: load raw, re-chunk, generate embeddings
        if not raw_path.exists():
            raise IngestionError(f"Raw JSON não encontrado: {raw_path}")

        with open(raw_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        normalized = NormalizedDocument(**data)
        collection = validate_qdrant_collection_name(
            normalized.metadata.get("qdrant_collection")
        )
        if normalized.source_type == "pdf":
            chunks_path = doc_dir / f"{document_id}_chunks.json"
            if not chunks_path.exists():
                raise IngestionError(
                    "Documento PDF não possui arquivo de chunks persistido; reingira pelo pipeline controlado."
                )
            chunk_count, embedding_status, qdrant_synced = _reindex_persisted_chunks_file(
                document_id=document_id,
                workspace_id=workspace_id,
                chunks_path=chunks_path,
                qdrant_collection=collection,
            )
            _persist_raw_ingestion_status("parsed" if qdrant_synced else "partial")
            elapsed_ms = int((time_module.time() - start_time) * 1000)
            return chunk_count, embedding_status, elapsed_ms

        qdrant_synced = True
        try:
            delete_document_chunks(document_id, collection_name=collection)
        except Exception:
            qdrant_synced = False

        # Re-chunk and re-index
        chunk_objs = _chunk_document(normalized, workspace_id, chunking_strategy)

        try:
            _embed_and_index_chunks_in_batches(
                chunk_objs,
                workspace_id,
                qdrant_collection=collection,
            )
        except Exception:
            qdrant_synced = False

        # Save updated chunks to disk (so document_registry reflects new strategy)
        try:
            chunks_file = doc_dir / f"{document_id}_chunks.json"
            with open(chunks_file, "w", encoding="utf-8") as f:
                json.dump([c.model_dump() for c in chunk_objs], f, ensure_ascii=False)
        except Exception:
            pass  # Non-critical

        _persist_raw_ingestion_status("parsed" if qdrant_synced else "partial")

        elapsed_ms = int((time_module.time() - start_time) * 1000)
        return len(chunk_objs), "regenerated", elapsed_ms

    else:
        chunks_file = doc_dir / f"{document_id}_chunks.json"
        temp_chunks_file = chunks_file.with_suffix(chunks_file.suffix + ".restore_tmp")
        with open(temp_chunks_file, "w", encoding="utf-8") as f:
            json.dump(chunks, f, ensure_ascii=False)

        try:
            chunk_count, embedding_status, qdrant_synced = _reindex_persisted_chunks_file(
                document_id=document_id,
                workspace_id=workspace_id,
                chunks_path=temp_chunks_file,
            )
            temp_chunks_file.replace(chunks_file)
        finally:
            try:
                temp_chunks_file.unlink(missing_ok=True)
            except Exception:
                pass

        _persist_raw_ingestion_status("parsed" if qdrant_synced else "partial")

        elapsed_ms = int((time_module.time() - start_time) * 1000)
        return chunk_count, embedding_status, elapsed_ms
