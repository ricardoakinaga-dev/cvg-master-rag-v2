"""
Clinical evidence pack helpers for veterinary RAG answers.
"""
import re
from typing import get_args

from models.schemas import (
    ClinicalBibliographyReference,
    ClinicalEvidenceItem,
    ClinicalEvidencePack,
    ClinicalEvidenceSection,
    ClinicalSectionKey,
    SearchResponse,
)


MISSING_EVIDENCE_PLACEHOLDER = "nao localizado nos trechos recuperados"
DEFAULT_EVIDENCE_SECTIONS: list[ClinicalSectionKey] = [
    "resumo",
    "historico_resenha",
    "sinais_sintomas",
    "exames_complementares",
    "tratamento_clinico",
    "tratamento_cirurgico",
    "proximos_passos",
    "referencias",
]

_VALID_SECTION_KEYS = set(get_args(ClinicalSectionKey))
_SECTION_SUPPORT_TERMS: dict[ClinicalSectionKey, list[str]] = {
    "resumo": [
        "acute gastroenteritis", "gastroenteritis", "acute diarrhea",
        "acute hemorrhagic diarrhea syndrome", "ahds", "pancreatitis",
        "hepatopathy", "chronic kidney disease", "pyometra",
        "urethral obstruction", "traumatic brain injury",
        "linear foreign body", "linear foreign bodies",
        "gastrointestinal foreign body", "gastrointestinal foreign bodies",
        "intestinal obstruction",
    ],
    "historico_resenha": [
        "history", "historico", "resenha", "breed", "raca", "age", "idade",
        "sex", "sexo", "vomito", "vomiting", "diarreia", "diarrhea",
        "anorexia", "duration", "duracao",
    ],
    "sinais_sintomas": [
        "vomito", "vomiting", "diarreia", "diarrhea", "dor abdominal",
        "abdominal pain", "letargia", "lethargy", "anorexia", "febre",
        "fever", "desidratacao", "dehydration", "edema", "hemorrhage",
        "hemorrhagic", "obstruction",
    ],
    "exames_complementares": [
        "hemograma", "cbc", "ureia", "bun", "creatinina", "creatinine",
        "ultrassom", "ultrasound", "radiografia", "radiography", "x ray",
        "hemogasometria", "blood gas", "laboratory", "laboratorio",
        "diagnostic imaging", "imagem diagnostica", "contrast radiography",
        "abdominal radiographs", "abdominal radiography",
    ],
    "tratamento_clinico": [
        "fluidoterapia", "fluid therapy", "fluids", "analgesia", "analgesic",
        "antiemetico", "antiemetic", "antibiotico", "antibiotic",
        "highly digestible", "digestible diet", "gi diet", "reduced fat",
        "dietary fat", "nutritional management", "management", "therapy",
        "stabilization", "resuscitation",
    ],
    "tratamento_cirurgico": [
        "cirurgia", "cirurgico", "cirurgica", "surgical", "surgery",
        "ovariohysterectomy", "ovariohisterectomia", "catheterization",
        "cateterizacao", "interventional", "intervencional", "enterotomy",
        "gastrotomy", "abdominal surgery", "exploratory laparotomy",
        "peritonitis",
    ],
    "proximos_passos": [
        "monitorar", "monitoring", "follow up", "follow-up", "recheck",
        "reavaliacao", "retorno", "next step", "next steps",
        "complication", "complications", "peritonitis",
    ],
    "referencias": [
        "reference", "references", "referencia", "referencias", "bibliography",
        "doi", "isbn",
    ],
}
_EXPLICIT_SUPPORT_SECTIONS = {
    "resumo",
    "exames_complementares",
    "tratamento_clinico",
    "tratamento_cirurgico",
    "proximos_passos",
    "referencias",
}


def build_clinical_evidence_pack(
    search_response: SearchResponse,
    *,
    required_sections: list[ClinicalSectionKey] | None = None,
    max_items_per_section: int = 6,
) -> ClinicalEvidencePack:
    """Group retrieved chunks by mandatory clinical answer section."""
    section_order = _normalize_section_order(required_sections or DEFAULT_EVIDENCE_SECTIONS)
    sections = {
        section: ClinicalEvidenceSection(
            section=section,
            status="missing",
            items=[],
            placeholder=MISSING_EVIDENCE_PLACEHOLDER,
        )
        for section in section_order
    }

    for result in search_response.results:
        candidate_sections = _candidate_sections_for_result(result, section_order)
        if not candidate_sections and not result.clinical_categories and section_order:
            candidate_sections = ["resumo"] if "resumo" in section_order else [section_order[0]]

        for section in candidate_sections:
            evidence_section = sections[section]
            if len(evidence_section.items) >= max_items_per_section:
                continue
            if any(item.chunk_id == result.chunk_id for item in evidence_section.items):
                continue

            evidence_section.items.append(_build_evidence_item(result, section))
            evidence_section.status = "found"
            evidence_section.placeholder = None
            evidence_section.bibliography = _dedupe_bibliography_for_items(evidence_section.items)

    return ClinicalEvidencePack(
        query=search_response.query,
        workspace_id=search_response.workspace_id,
        source_method=search_response.method,
        section_order=section_order,
        sections=sections,
        bibliography=_dedupe_bibliography_for_sections(sections.values()),
        missing_sections=_missing_sections(sections, section_order),
        total_items=sum(len(section.items) for section in sections.values()),
    )


def _normalize_section_order(sections: list[str]) -> list[ClinicalSectionKey]:
    ordered = []
    for section in sections:
        if section not in _VALID_SECTION_KEYS or section in ordered:
            continue
        ordered.append(section)
    return ordered  # type: ignore[return-value]


def _candidate_sections_for_result(result, section_order: list[ClinicalSectionKey]) -> list[ClinicalSectionKey]:
    categories = [
        category for category in result.clinical_categories
        if category in section_order and category in _VALID_SECTION_KEYS
    ]
    if result.primary_clinical_category in section_order and result.primary_clinical_category not in categories:
        categories.insert(0, result.primary_clinical_category)
    return [
        category for category in categories
        if _result_supports_section(result.text or "", category)
    ]  # type: ignore[return-value]


def _result_supports_section(text: str, section: ClinicalSectionKey) -> bool:
    """Reject chunks that only contain low-signal words for the requested section."""
    normalized = _normalize_for_section_support(text)
    terms = [
        _normalize_for_section_support(term).strip()
        for term in _SECTION_SUPPORT_TERMS.get(section, [])
    ]
    matched = [term for term in terms if term and f" {term} " in normalized]
    if section in _EXPLICIT_SUPPORT_SECTIONS:
        return bool(matched)
    if section in {"historico_resenha", "sinais_sintomas"}:
        explicit_context = any(
            signal in normalized
            for signal in [" history ", " historico ", " resenha ", " sinais ", " signs ", " symptoms "]
        )
        return explicit_context or len(matched) >= 2
    return bool(matched)


def _normalize_for_section_support(text: str) -> str:
    normalized = re.sub(r"[\W_]+", " ", (text or "").lower(), flags=re.UNICODE)
    return f" {' '.join(normalized.split())} "


def _build_evidence_item(result, section: ClinicalSectionKey) -> ClinicalEvidenceItem:
    reference = ClinicalBibliographyReference(
        chunk_id=result.chunk_id,
        document_id=result.document_id,
        document_filename=result.document_filename,
        page=result.page_hint,
        sections=[section],
    )
    return ClinicalEvidenceItem(
        chunk_id=result.chunk_id,
        text=result.text,
        score=result.score,
        section=section,
        document_id=result.document_id,
        document_filename=result.document_filename,
        page=result.page_hint,
        query_variant=result.query_variant,
        query_variants=result.query_variants,
        clinical_categories=[
            category for category in result.clinical_categories
            if category in _VALID_SECTION_KEYS
        ],
        bibliographic_reference=reference,
        relevance_reason=(
            f"chunk categorizado como {section} pelo classificador clinico deterministico"
        ),
    )


def _missing_sections(
    sections: dict[ClinicalSectionKey, ClinicalEvidenceSection],
    section_order: list[ClinicalSectionKey],
) -> list[ClinicalSectionKey]:
    return [
        section for section in section_order
        if section != "referencias" and sections[section].status == "missing"
    ]


def _dedupe_bibliography_for_items(
    items: list[ClinicalEvidenceItem],
) -> list[ClinicalBibliographyReference]:
    return _dedupe_references(item.bibliographic_reference for item in items)


def _dedupe_bibliography_for_sections(
    sections,
) -> list[ClinicalBibliographyReference]:
    references = []
    for section in sections:
        references.extend(section.bibliography)
    return _dedupe_references(references)


def _dedupe_references(references) -> list[ClinicalBibliographyReference]:
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
