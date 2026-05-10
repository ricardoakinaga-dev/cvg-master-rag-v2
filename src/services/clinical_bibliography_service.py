"""
Clinical bibliography helpers for structured RAG answers.
"""
from collections.abc import Mapping, Sequence
from typing import get_args

from models.schemas import (
    Citation,
    ClinicalBibliographyReference,
    ClinicalSectionKey,
)


BIBLIOGRAPHY_FOOTER_HEADING = "## Referencias bibliograficas"
_VALID_SECTION_KEYS = set(get_args(ClinicalSectionKey))


def build_bibliography_references(
    citations: Sequence[Citation],
    section_chunk_map: Mapping[str, Sequence[str]] | None = None,
) -> list[ClinicalBibliographyReference]:
    """Deduplicate citation metadata and attach the sections supported by each chunk."""
    sections_by_chunk = _sections_by_chunk(section_chunk_map or {})
    references: dict[tuple[str | None, int | None, str], ClinicalBibliographyReference] = {}

    for citation in citations:
        key = (citation.document_filename, citation.page, citation.chunk_id)
        if key not in references:
            references[key] = ClinicalBibliographyReference(
                chunk_id=citation.chunk_id,
                document_id=citation.document_id,
                document_filename=citation.document_filename,
                page=citation.page,
                sections=[],
            )
        reference = references[key]
        for section in sections_by_chunk.get(citation.chunk_id, []):
            if section not in reference.sections:
                reference.sections.append(section)

    return list(references.values())


def format_bibliography_footer(
    references: Sequence[ClinicalBibliographyReference],
    *,
    answer_markdown: str | None = None,
) -> str:
    """Render the mandatory bibliography footer from structured references."""
    deduped_references = _dedupe_references(references)
    if answer_markdown:
        deduped_references = _order_references_by_first_appearance(
            deduped_references,
            answer_markdown,
        )

    if not deduped_references:
        return f"{BIBLIOGRAPHY_FOOTER_HEADING}\nNenhuma referencia bibliografica recuperada."

    lines = [BIBLIOGRAPHY_FOOTER_HEADING]
    for index, reference in enumerate(deduped_references, start=1):
        filename = reference.document_filename or "Documento sem nome"
        page = f"p. {reference.page}" if reference.page is not None else "p. n/a"
        sections = ", ".join(reference.sections) if reference.sections else "secao nao informada"
        lines.append(f"{index}. {filename}, {page}, {reference.chunk_id} - {sections}")
    return "\n".join(lines)


def _sections_by_chunk(
    section_chunk_map: Mapping[str, Sequence[str]],
) -> dict[str, list[ClinicalSectionKey]]:
    sections_by_chunk: dict[str, list[ClinicalSectionKey]] = {}
    for section, chunk_ids in section_chunk_map.items():
        if section not in _VALID_SECTION_KEYS:
            continue
        for chunk_id in chunk_ids:
            sections_by_chunk.setdefault(chunk_id, [])
            if section not in sections_by_chunk[chunk_id]:
                sections_by_chunk[chunk_id].append(section)  # type: ignore[arg-type]
    return sections_by_chunk


def _dedupe_references(
    references: Sequence[ClinicalBibliographyReference],
) -> list[ClinicalBibliographyReference]:
    deduped: dict[tuple[str | None, int | None, str], ClinicalBibliographyReference] = {}
    for reference in references:
        key = (reference.document_filename, reference.page, reference.chunk_id)
        if key not in deduped:
            deduped[key] = reference.model_copy(update={"sections": list(reference.sections)})
            continue
        merged = deduped[key]
        for section in reference.sections:
            if section not in merged.sections:
                merged.sections.append(section)
    return list(deduped.values())


def _order_references_by_first_appearance(
    references: Sequence[ClinicalBibliographyReference],
    answer_markdown: str,
) -> list[ClinicalBibliographyReference]:
    def sort_key(indexed_reference):
        index, reference = indexed_reference
        position = answer_markdown.find(reference.chunk_id)
        if position < 0:
            position = len(answer_markdown) + index
        return position, index

    return [
        reference
        for _, reference in sorted(enumerate(references), key=sort_key)
    ]
