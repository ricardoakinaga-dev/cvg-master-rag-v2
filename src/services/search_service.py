"""
Search Service — orchestrates retrieval + answer generation
"""
import hashlib
import time
import json
import re
from datetime import datetime, timezone
from types import SimpleNamespace

from models.schemas import ClinicalQueryVariant, QueryRequest, QueryResponse, SearchRequest, SearchResponse, Citation, GroundingReport
from services.vector_service import search_hybrid
from services.llm_service import generate_answer, estimate_answer_cost, client as llm_client
from services.grounding_service import verify_grounding, enrich_citations_with_filename
from services.clinical_query_planner_service import (
    CLINICAL_PROBLEM_RULES,
    DEFAULT_CLINICAL_SECTIONS,
    plan_clinical_query,
    prepare_clinical_retrieval_query,
)
from services.clinical_evidence_pack_service import build_clinical_evidence_pack
from services.clinical_response_generator_service import (
    generate_clinical_answer_from_evidence_pack,
    reduce_unsupported_clinical_answer,
)
from core.config import LOGS_DIR
from services.telemetry_service import get_telemetry
from services.request_context import get_request_id
from core.config import QUERY_EXPANSION_ENABLED


HYDE_SYSTEM_PROMPT = "Você é um assistente que escreve respostas factuais breves para ajudar na busca de documentos."
HYDE_USER_PROMPT_TEMPLATE = "Given the question below, write a brief factual answer (2-3 sentences) that would help retrieve relevant documents. Answer ONLY with facts — do not speculate beyond what is directly implied by the question.\n\nQuestion: {query}\nAnswer:"
STRICT_GROUNDED_SYSTEM_PROMPT = """Você é um assistente de IA que responde perguntas
usando SOMENTE o contexto fornecido abaixo.

Responda apenas com fatos explicitamente suportados pelos trechos.
Prefira uma resposta curta e altamente extractiva:
- no máximo 4 bullets curtos ou 1 parágrafo curto
- não invente etapas ausentes
- não una partes desconexas em um protocolo mais amplo
- se o contexto cobrir só parte da resposta, diga apenas essa parte
- se o contexto não trouxer protocolo completo, diga que os trechos só sustentam uma orientação parcial
- nunca responda apenas que a orientação é parcial; liste os fatos concretos encontrados nos trechos
- quando houver doses, dietas, exames, terapias ou monitoramento nos trechos, inclua esses itens

Só diga "Não sei" quando os trechos não trouxerem nenhum fato útil para responder.
Responda em português."""
LOW_CONFIDENCE_GROUNDING_OVERRIDE_THRESHOLD = 0.8
RETRIEVAL_PROFILE_TO_EXPANSION_MODE = {
    "hybrid": "off",
    "hyde_hybrid": "always",
    "semantic_hybrid": "off",
    "semantic_hyde_hybrid": "always",
}
SEMANTIC_RETRIEVAL_PROFILES = {"semantic_hybrid", "semantic_hyde_hybrid"}

# Adaptive expansion: patterns that suggest a specific lookup (skip expansion)
_SPECIFIC_LOOKUP_PATTERNS = [
    r"\b\d{4,}\b",        # long numbers (years, IDs, phone numbers)
    r"\b\d+/\d+\b",       # dates or ratios
    r"\b[A-Z]{2,}\d+\b",  # uppercase code prefixes followed by digits (e.g. PROJ123)
    r"\b(art\.?|artigo|nº|número|ref\.?|processo)\b",  # specific reference terms
]
_PROTOCOL_LOOKUP_PATTERN = r"\bprotocolo(?:\s*(?:n[ºo.]?|#|:|-))?\s*(?:\d{3,}|[A-Z]{2,}\d+)\b"
_SEIZURE_QUERY_PATTERN = r"\b(convuls(?:ão|ao|ões|oes)|crises?\s+convuls(?:ivas?|ivos?)|epilepsia|epiléptic[ao]s?)\b"
_CANINE_QUERY_PATTERN = r"\b(c[aã]o|c[aã]es|cachorr[oa]s?|canin[ao]s?)\b"
_FELINE_QUERY_PATTERN = r"\b(gat[oa]s?|felin[ao]s?)\b"
_TREATMENT_QUERY_PATTERN = r"\b(trat(?:ar|ament(?:o|os))|protocolos?|manejo|conduta|emerg[êe]ncia|anticonvulsiv(?:ante|antes))\b"
_CROSSLINGUAL_QUERY_ALIASES = [
    (_SEIZURE_QUERY_PATTERN, ["seizure", "seizures", "epileptic"]),
    (_CANINE_QUERY_PATTERN, ["dog", "dogs", "canine"]),
    (_FELINE_QUERY_PATTERN, ["cat", "cats", "feline"]),
    (r"\btrat(?:ar|ament(?:o|os))\b", ["treatment", "management"]),
    (r"\bprotocolos?\b", ["protocol", "management", "approach"]),
    (r"\bmanejo\b", ["management"]),
    (r"\bconduta\b", ["approach", "management"]),
    (r"\bemerg[êe]ncia\b", ["emergency"]),
    (r"\banticonvulsiv(?:ante|antes)\b", ["anticonvulsant", "antiepileptic"]),
    (r"\bgastroenterit(?:e|es)\b", ["gastroenteritis", "enteritis"]),
    (r"\bdiarre(?:ia|ico|ica)\b", ["diarrhea"]),
    (r"\bv[ôo]mit(?:o|os|ando|ar)\b", ["vomiting", "emesis"]),
    (r"\bdesidrat(?:a[çc][aã]o|ado|ada|ados|adas)\b", ["dehydration"]),
    (r"\bfluid(?:o|os|oterapia)\b", ["fluid therapy", "fluids"]),
    (r"\bantiem[ée]tic(?:o|os|a|as)\b", ["antiemetic", "antiemetics"]),
    (r"\bhepatopat(?:ia|ias)|\bhep[aá]tic(?:o|a|os|as)|\bf[ií]gad(?:o|os)\b", ["hepatopathy", "hepatic disease", "liver disease"]),
    (r"\bhepatit(?:e|es)\b", ["hepatitis", "chronic hepatitis"]),
    (r"\bcolangit(?:e|es)\b", ["cholangitis"]),
    (r"\bcolest(?:ase|ático|atica|áticos|aticas)\b", ["cholestasis", "cholestatic"]),
    (r"\bursodesoxic[óo]lic(?:o|a)\b|\buds?ca\b", ["ursodeoxycholic acid", "ursodiol"]),
    (r"\bsilimarina\b|\bsame\b|\bs-adenosilmetionina\b", ["silymarin", "SAMe", "S-adenosylmethionine"]),
    (r"\bfratur(?:a|as|ado|ados|ada|adas)\b", ["fracture", "fractures"]),
    (r"\bfixa(?:dor|ção|cao|ções|coes)\b", ["fixation", "fixator"]),
    (r"\besquel[ée]tic(?:o|a|os|as)\b", ["skeletal"]),
    (r"\bextern(?:o|a|os|as)\b", ["external"]),
    (r"\bcirurg(?:ia|ias|ico|icos|ica|icas|úrgico|úrgicos|úrgica|úrgicas)\b", ["surgery", "surgical"]),
    (r"\bp[óo]s[-\s]?operat[óo]ri(?:o|a|os|as)\b", ["postoperative", "postoperative care"]),
    (r"\bcuidad(?:o|os)\b", ["care"]),
    (r"\bferid(?:a|as)\b", ["wound", "wounds"]),
    (r"\bsutur(?:a|as|ar)\b", ["suture", "suturing"]),
    (r"\banalgesi(?:a|co|cos|ca|cas)\b", ["analgesia", "analgesic"]),
    (r"\bren(?:al|ais)|\brim\b|\brins\b", ["renal", "kidney"]),
    (r"\bcard[ií]ac(?:o|a|os|as)|\bcora[çc][aã]o\b", ["cardiac", "heart"]),
]
_SEIZURE_PROTOCOL_HINTS = [
    "status epilepticus",
    "acute repetitive seizures",
    "benzodiazepine",
    "diazepam",
    "midazolam",
    "anticonvulsant",
]
_DOMAIN_ACRONYM_ALIASES = {
    "drc": "doença renal crônica",
    "irc": "insuficiência renal crônica",
    "dut": "doença do trato urinário",
    "itu": "infecção do trato urinário",
    "ircf": "insuficiência renal crônica felina",
}

CLINICAL_CATEGORY_KEYWORDS = {
    "referencias": [
        "bibliography", "reference", "references", "referencia", "referencias",
        "textbook", "doi", "isbn",
    ],
    "tratamento_cirurgico": [
        "cirurgia", "cirurgico", "cirurgica", "surgical", "surgery",
        "ovariohisterectomia", "ovariohysterectomy", "cateterizacao",
        "catheterization", "intervencional", "interventional",
        "enterotomy", "gastrotomy", "laparotomy", "abdominal surgery",
        "peritonitis",
    ],
    "tratamento_clinico": [
        "tratamento", "therapy", "therapeutic", "fluidoterapia", "fluid therapy",
        "analgesia", "analgesic", "antiemetico", "antiemetic", "antibiotico",
        "antibiotic", "dose", "dosagem", "medicacao", "medication", "manejo",
        "stabilization", "resuscitation",
    ],
    "exames_complementares": [
        "hemograma", "cbc", "ureia", "creatinina", "ultrassom", "ultrasound",
        "radiografia", "radiography", "x-ray", "hemogasometria", "blood gas",
        "exame", "exames", "diagnostic", "diagnostico", "laboratorio", "laboratory",
        "abdominal radiographs", "abdominal radiography", "contrast radiography",
    ],
    "sinais_sintomas": [
        "vomito", "vomiting", "diarreia", "diarrhea", "dor", "pain",
        "letargia", "lethargy", "sinal", "sinais", "symptom", "symptoms",
        "anorexia", "febre", "fever", "desidratacao", "dehydration",
        "obstruction",
    ],
    "historico_resenha": [
        "historico", "history", "resenha", "idade", "age", "raca", "breed",
        "sexo", "sex", "macho", "femea", "male", "female",
    ],
    "proximos_passos": [
        "proximo", "proximos", "monitorar", "monitoring", "follow-up",
        "reavaliacao", "recheck", "retorno", "next step", "next steps",
    ],
    "resumo": [
        "overview", "summary", "resumo", "definition", "definicao",
        "etiologia", "pathophysiology", "fisiopatologia",
        "linear foreign body", "gastrointestinal foreign body", "intestinal obstruction",
    ],
}

CLINICAL_CATEGORY_PRIORITY = [
    "referencias",
    "tratamento_cirurgico",
    "tratamento_clinico",
    "exames_complementares",
    "sinais_sintomas",
    "historico_resenha",
    "proximos_passos",
    "resumo",
]

CLINICAL_DIVERSITY_CATEGORY_ORDER = [
    "historico_resenha",
    "sinais_sintomas",
    "exames_complementares",
    "tratamento_clinico",
    "tratamento_cirurgico",
    "proximos_passos",
    "referencias",
    "resumo",
]

CLINICAL_DOMAIN_SIGNALS = [
    " veterinaria ", " veterinary ", " paciente ", " patient ", " clinico ", " clinical ",
    " diagnostico ", " diagnosis ", " diagnostic ", " tratamento ", " treatment ",
    " therapy ", " terapeutico ", " doenca ", " disease ", " sinais ", " signs ",
    " sintomas ", " symptoms ", " exame ", " exam ", " hemograma ", " cbc ",
    " ureia ", " creatinina ", " ultrassom ", " ultrasound ", " radiografia ",
    " radiography ", " hemogasometria ", " blood gas ", " dose ", " dosage ",
    " medicacao ", " medication ", " cirurgia ", " surgery ", " analgesia ",
    " antibiotic ", " antibiotico ", " fluidoterapia ", " fluid therapy ",
    " caes ", " cao ", " canino ", " canine ", " dog ", " gato ", " felino ",
    " feline ", " cat ",
]


def _answer_is_abstention(answer: str) -> bool:
    normalized = (answer or "").strip().lower()
    if not normalized:
        return True
    return normalized.startswith("não sei") or normalized.startswith(
        "não tenho informações suficientes"
    )


def _expand_domain_acronyms(query: str) -> str:
    expanded = query
    for acronym, replacement in _DOMAIN_ACRONYM_ALIASES.items():
        expanded = re.sub(
            rf"\b{re.escape(acronym)}\b",
            replacement,
            expanded,
            flags=re.IGNORECASE,
        )
    return expanded


def _query_is_acronym_heavy(query: str) -> bool:
    tokens = re.findall(r"\b[\wÀ-ÿ]{2,}\b", query)
    if not tokens:
        return False
    acronym_like = [
        token for token in tokens
        if len(token) <= 4 and token.upper() == token and token.isalpha()
    ]
    if acronym_like:
        return True
    lower_tokens = [token.lower() for token in tokens]
    return any(token in _DOMAIN_ACRONYM_ALIASES for token in lower_tokens)


def _should_expand_adaptive(query: str) -> tuple[bool, str]:
    """
    Adaptive heuristic: decide whether HyDE expansion should run for a given query.

    Returns (should_expand: bool, reason: str).
    The reason string is one of the decision labels below, used for observability.

    Heuristic rules (evaluated in order):
    1. Skip if query looks like a specific identifier/lookup:
       - contains a number ≥ 4 digits, date-like pattern, uppercase code, or reference term
    2. Expand if query is short or ambiguous:
       - fewer than 3 words, or fewer than 12 chars
       - is a natural language question (contains ? or interrogative words)
    3. Default: expand (better recall for open queries)
    """
    import re

    # Rule 1: specific lookup patterns → skip
    if re.search(_PROTOCOL_LOOKUP_PATTERN, query, re.IGNORECASE):
        return False, "specific_lookup"
    for pattern in _SPECIFIC_LOOKUP_PATTERNS:
        if re.search(pattern, query, re.IGNORECASE):
            return False, "specific_lookup"

    # Rule 2a: very short query → expand
    words = query.strip().split()
    if len(words) < 3:
        return True, "short_query"

    # Rule 2b: very short char length → expand
    if len(query.strip()) < 12:
        return True, "short_query"

    # Rule 3: natural language question → expand
    question_words = {"o que", "o quê", "quem", "quando", "onde", "como", "por quê",
                      "porque", "qual", "quais", "existe", "existem", "o que é", "quem é",
                      "what", "who", "when", "where", "how", "why", "which", "does",
                      "is there", "are there", "can i", "posso", "pode", "existe"}
    q_lower = query.lower().strip()
    if "?" in q_lower or any(q_lower.startswith(w) or f" {w} " in f" {q_lower} " for w in question_words):
        return True, "natural_language_question"

    # Default: expand for general queries
    return True, "general_query"


def _expand_query(query: str) -> tuple[str, int]:
    """
    HyDE-like query expansion: generate a short hypothetical answer
    and append it to the original query to improve dense retrieval.

    Uses the existing generate_answer infrastructure with a minimal prompt.
    Returns (expanded_query, latency_ms). On any failure returns ("", 0).
    Latency is in milliseconds.
    """
    import time
    from services.llm_service import generate_answer

    hyde_chunks = [{"text": "", "chunk_id": "hyde", "score": 0.0}]
    start = time.time()
    try:
        answer_text, _, _ = generate_answer(
            query=query,
            chunks=hyde_chunks,
            system_prompt=HYDE_SYSTEM_PROMPT,
        )
        latency_ms = int((time.time() - start) * 1000)
        if not answer_text or len(answer_text.strip()) < 10:
            return "", latency_ms
        return f"{query} {answer_text.strip()}", latency_ms
    except Exception:
        return "", 0


def _finalize_low_confidence(
    retrieval_low_confidence: bool,
    has_results: bool,
    grounding_result: GroundingReport | None,
    *,
    allow_grounding_override: bool = True,
) -> tuple[bool, str]:
    """
    Convert retrieval heuristics into the final user-facing low_confidence signal.

    Retrieval may be conservative. If chunks were found and the generated answer
    ends up grounded with strong citation coverage, the final signal is cleared.
    """
    if not has_results:
        return True, "no_results"
    if not retrieval_low_confidence:
        return False, "retrieval_ok"
    if not allow_grounding_override:
        return True, "weak_query_support"
    if grounding_result and grounding_result.grounded and not grounding_result.needs_review:
        if grounding_result.citation_coverage >= LOW_CONFIDENCE_GROUNDING_OVERRIDE_THRESHOLD:
            return False, "grounding_override"
    return True, "retrieval_low_confidence"


def _query_has_minimal_support(query: str, chunks: list[dict]) -> bool:
    """
    Require at least one non-numeric lexical bridge between the question and the
    retrieved context before we allow a low-confidence retrieval to be upgraded.
    """
    from services.vector_service import _content_query_terms, _tokenize_terms

    query_terms = _content_query_terms(query)
    if not query_terms:
        query_terms = {
            token
            for token in _tokenize_terms(query, min_len=2)
            if not token.isdigit()
        }
    else:
        query_terms = {
            token
            for token in query_terms
            if not token.isdigit()
        }
    if not query_terms:
        return True

    for chunk in chunks:
        chunk_terms = set(_tokenize_terms(str(chunk.get("text", "")), min_len=2))
        if query_terms.intersection(chunk_terms):
            return True
    return False


def _resolve_search_profile(
    retrieval_profile: str | None,
    query_expansion_mode: str | None,
    default_query_expansion_mode: str,
) -> tuple[str | None, str, bool]:
    """Map retrieval profile to concrete retrieval knobs while preserving legacy defaults."""
    if retrieval_profile:
        return (
            retrieval_profile,
            RETRIEVAL_PROFILE_TO_EXPANSION_MODE[retrieval_profile],
            retrieval_profile in SEMANTIC_RETRIEVAL_PROFILES,
        )
    return None, (query_expansion_mode or default_query_expansion_mode), False


def _merge_retrieval_filters(filters: dict | None, semantic_only: bool) -> dict | None:
    merged = dict(filters or {})
    if semantic_only:
        merged["strategy"] = "semantic"
    return merged or None


def _should_try_neural_query_retry(request: QueryRequest, search_resp: SearchResponse) -> bool:
    """Limit expensive neural reranking fallback to ambiguous query-time failures."""
    if request.reranking is not None:
        return False
    if request.reranking_method is not None:
        return False
    if search_resp.reranking_applied:
        return False
    if not search_resp.results:
        return False
    if _query_is_acronym_heavy(request.query):
        return False
    from services.vector_service import _has_minimal_query_support

    if any(_has_minimal_query_support(request.query, item.text) for item in search_resp.results[:3]):
        return False
    return bool(search_resp.low_confidence)


def _should_accept_neural_retry(original: SearchResponse, retry: SearchResponse) -> bool:
    """Accept a retry when it materially improves the candidate set."""
    if not retry.results:
        return False
    if not original.results:
        return True
    if original.low_confidence and not retry.low_confidence:
        return True

    original_top = float(original.results[0].score or 0.0)
    retry_top = float(retry.results[0].score or 0.0)
    original_ids = [item.chunk_id for item in original.results[:3]]
    retry_ids = [item.chunk_id for item in retry.results[:3]]

    if retry_top > original_top + 0.01:
        return True
    if retry_top > original_top and retry_ids != original_ids:
        return True
    if retry_ids and retry_ids != original_ids:
        return True
    return False


def _build_crosslingual_retrieval_query(query: str) -> tuple[str | None, str | None]:
    """
    Build a lightweight multilingual bridge query for low-confidence retrieval.

    This is intentionally conservative and only appends a small glossary of
    English aliases when the original query already carries matching Portuguese
    concepts. It helps Portuguese questions hit English medical corpora without
    changing the user-visible query or globally enabling aggressive expansion.
    """
    import re

    normalized_query = query.strip()
    if not normalized_query:
        return None, None

    lowered_query = normalized_query.lower()
    additions: list[str] = []

    for pattern, aliases in _CROSSLINGUAL_QUERY_ALIASES:
        if not re.search(pattern, lowered_query, re.IGNORECASE):
            continue
        for alias in aliases:
            if alias.lower() in lowered_query:
                continue
            if alias not in additions:
                additions.append(alias)

    if (
        re.search(_SEIZURE_QUERY_PATTERN, lowered_query, re.IGNORECASE)
        and (
            re.search(_CANINE_QUERY_PATTERN, lowered_query, re.IGNORECASE)
            or re.search(_FELINE_QUERY_PATTERN, lowered_query, re.IGNORECASE)
        )
        and re.search(_TREATMENT_QUERY_PATTERN, lowered_query, re.IGNORECASE)
    ):
        for hint in _SEIZURE_PROTOCOL_HINTS:
            if hint not in additions and hint.lower() not in lowered_query:
                additions.append(hint)

    if (
        re.search(r"\bfratur(?:a|as|ado|ados|ada|adas)\b", lowered_query, re.IGNORECASE)
        and re.search(r"\bfixa(?:dor|ção|cao|ções|coes)\b", lowered_query, re.IGNORECASE)
    ):
        for hint in ["external skeletal fixation", "external fixator"]:
            if hint not in additions and hint.lower() not in lowered_query:
                additions.append(hint)

    if (
        re.search(r"\bp[óo]s[-\s]?operat[óo]ri(?:o|a|os|as)\b", lowered_query, re.IGNORECASE)
        and re.search(r"\bcirurg(?:ia|ias|ico|icos|ica|icas|úrgico|úrgicos|úrgica|úrgicas)\b", lowered_query, re.IGNORECASE)
    ):
        for hint in [
            "perioperative care",
            "postoperative complications",
            "surgical site infection",
            "wound healing",
            "analgesia",
        ]:
            if hint not in additions and hint.lower() not in lowered_query:
                additions.append(hint)

    if re.search(r"\bgastroenterit(?:e|es)\b", lowered_query, re.IGNORECASE):
        for hint in [
            "acute gastroenteritis",
            "acute diarrhea",
            "vomiting",
            "dehydration",
            "fluid therapy",
            "antiemetic",
        ]:
            if hint not in additions and hint.lower() not in lowered_query:
                additions.append(hint)

    if re.search(r"\bhepatopat(?:ia|ias)|\bhep[aá]tic(?:o|a|os|as)|\bf[ií]gad(?:o|os)\b", lowered_query, re.IGNORECASE):
        for hint in [
            "canine liver disease",
            "chronic hepatitis in dogs",
            "copper-associated hepatopathy",
            "hepatoprotective therapy",
            "SAMe",
            "ursodeoxycholic acid",
        ]:
            if hint not in additions and hint.lower() not in lowered_query:
                additions.append(hint)

    if not additions:
        return None, None

    return f"{normalized_query} {' '.join(additions)}", "crosslingual_glossary"


def _should_try_crosslingual_retry(request: QueryRequest, search_resp: SearchResponse) -> bool:
    """Use glossary-based recovery only after retrieval still looks ambiguous."""
    if not search_resp.low_confidence:
        return False
    retry_query, _ = _build_crosslingual_retrieval_query(request.query)
    return bool(retry_query and retry_query.strip() != request.query.strip())


def _should_try_grounded_reanswer(
    request: QueryRequest,
    retrieval_low_confidence: bool,
    grounding_result: GroundingReport,
) -> bool:
    """
    Retry answer generation with a stricter extractive prompt when retrieval is
    good enough but the first answer still overreaches the citations.
    """
    import re

    if retrieval_low_confidence:
        return False
    if grounding_result.grounded:
        return False
    if not getattr(llm_client, "api_key", ""):
        return False
    _, adaptive_reason = _should_expand_adaptive(request.query)
    if adaptive_reason == "specific_lookup":
        return False
    if grounding_result.citation_coverage >= LOW_CONFIDENCE_GROUNDING_OVERRIDE_THRESHOLD:
        return False
    return bool(re.search(_TREATMENT_QUERY_PATTERN, request.query, re.IGNORECASE))


def _should_accept_grounded_reanswer(
    original: GroundingReport,
    retry: GroundingReport,
    retry_answer: str | None = None,
) -> bool:
    normalized_answer = (retry_answer or "").strip().lower()
    if len(normalized_answer) < 80:
        return False
    if normalized_answer in {
        "os trechos só sustentam uma orientação parcial.",
        "os trechos nao sustentam um protocolo completo.",
        "os trechos não sustentam um protocolo completo.",
    }:
        return False
    if retry.grounded and not original.grounded:
        return True
    if retry.citation_coverage >= original.citation_coverage + 0.15:
        return True
    if len(retry.uncited_claims) < len(original.uncited_claims):
        return True
    return False


def execute_search(
    request: SearchRequest,
    *,
    default_query_expansion_mode: str = "off",
) -> SearchResponse:
    """
    Execute retrieval for both /search and /query using the same profile contract.

    `/search` preserves its historical default of expansion disabled.
    `/query` can still opt into adaptive expansion by passing a different default.
    """
    (
        effective_profile,
        expansion_mode,
        semantic_only,
    ) = _resolve_search_profile(
        request.retrieval_profile,
        request.query_expansion_mode,
        default_query_expansion_mode,
    )

    expansion_requested = False
    expansion_decision_reason: str | None = None
    expansion_applied = False
    expansion_fallback = False
    expansion_method: str | None = None
    search_query = _expand_domain_acronyms(request.query)

    if expansion_mode == "always":
        expansion_requested = True
        expansion_decision_reason = "always_mode"
        expanded, _ = _expand_query(request.query)
        if expanded:
            search_query = expanded
            expansion_applied = True
            expansion_method = "hyde"
        else:
            expansion_fallback = True
    elif expansion_mode == "adaptive":
        should_expand, heuristic_reason = _should_expand_adaptive(request.query)
        if should_expand:
            expansion_requested = True
            expansion_decision_reason = f"adaptive:{heuristic_reason}"
            expanded, _ = _expand_query(request.query)
            if expanded:
                search_query = expanded
                expansion_applied = True
                expansion_method = "hyde"
            else:
                expansion_fallback = True
        else:
            expansion_decision_reason = f"adaptive:{heuristic_reason}"

    bridged_query, _ = _build_crosslingual_retrieval_query(search_query)
    if bridged_query:
        search_query = bridged_query

    resolved_request = request.model_copy(
        update={
            "query": search_query,
            "filters": _merge_retrieval_filters(request.filters, semantic_only),
        }
    )
    search_resp = search_hybrid(resolved_request)
    search_resp.query_expansion_applied = expansion_applied
    search_resp.query_expansion_method = expansion_method
    search_resp.query_expansion_fallback = expansion_fallback
    search_resp.query_expansion_requested = expansion_requested
    search_resp.query_expansion_mode = expansion_mode
    search_resp.query_expansion_decision_reason = expansion_decision_reason
    search_resp.retrieval_profile = effective_profile
    return search_resp


def execute_clinical_fanout_search(
    request: SearchRequest,
    *,
    use_llm: bool = True,
    per_variant_top_k: int | None = None,
) -> SearchResponse:
    """Run retrieval once per safe clinical query variant."""
    if use_llm:
        return _execute_clinical_translation_search(
            request,
            per_variant_top_k=per_variant_top_k,
        )

    start = time.time()
    plan, planner_latency = plan_clinical_query(request.query, use_llm=use_llm)
    safe_variants = [
        variant for variant in plan.query_variants
        if not variant.blocked and variant.context_preserved is not False
    ]

    raw_results = []
    total_candidates = 0
    retrieval_time_ms = 0
    variant_debug = []
    for index, variant in enumerate(safe_variants):
        variant_request = request.model_copy(
            update={
                "query": variant.query,
                "top_k": per_variant_top_k or request.top_k,
                "reranking": False,
                "reranking_method": "none",
            }
        )
        variant_response = search_hybrid(variant_request)
        variant_snapshot = _safe_query_variant_snapshot(variant, index)
        variant_debug.append({
            **variant_snapshot,
            "executed": True,
            "results_count": len(variant_response.results),
            "total_candidates": variant_response.total_candidates,
            "low_confidence": variant_response.low_confidence,
            "retrieval_time_ms": variant_response.retrieval_time_ms,
        })
        total_candidates += variant_response.total_candidates
        retrieval_time_ms += variant_response.retrieval_time_ms
        for item in variant_response.results:
            classified = _classify_search_result_item(item)
            raw_results.append(classified.model_copy(update={
                "query_variant": variant_snapshot,
                "query_variants": [variant_snapshot],
            }))
    variant_debug.extend(
        {
            **_safe_query_variant_snapshot(variant, index),
            "executed": False,
            "results_count": 0,
            "total_candidates": 0,
            "low_confidence": None,
            "retrieval_time_ms": 0,
        }
        for index, variant in enumerate(plan.query_variants)
        if variant.blocked or variant.context_preserved is False
    )

    scoped_results, scope_filter_debug = _filter_clinical_scope_candidates(raw_results, plan)
    merged_results, duplicate_count = _merge_clinical_fanout_candidates(scoped_results)
    results, reranking_debug = _rerank_clinical_candidates_for_diversity(
        merged_results,
        desired_sections=plan.desired_sections,
    )
    fanout_summary = {
        "planner_latency_ms": int(planner_latency * 1000),
        "variant_count": len(plan.query_variants),
        "executed_variant_count": len(safe_variants),
        "skipped_variant_count": len(plan.query_variants) - len(safe_variants),
        "raw_result_count": len(raw_results),
        "deduped_result_count": len(results),
        "duplicate_chunk_count": duplicate_count,
        "scope_filtered_count": scope_filter_debug["removed_count"],
        "generated_by": plan.generated_by,
        "desired_sections": list(plan.desired_sections),
    }
    total_latency_ms = int((time.time() - start) * 1000)
    return SearchResponse(
        query=request.query,
        workspace_id=request.workspace_id,
        results=results,
        total_candidates=total_candidates,
        low_confidence=not results,
        retrieval_time_ms=retrieval_time_ms or total_latency_ms,
        method="clinical_fanout",
        scores_breakdown={
            "clinical_fanout": fanout_summary,
            "clinical_scope_filter": scope_filter_debug,
            "clinical_reranking": reranking_debug,
            "clinical_fanout_debug": _build_clinical_fanout_debug(
                variants=variant_debug,
                results=results,
                summary=fanout_summary,
            ),
        },
        reranking_applied=False,
        reranking_method=None,
        query_expansion_applied=False,
        query_expansion_method=None,
        query_expansion_fallback=False,
        query_expansion_requested=False,
        query_expansion_mode="off",
        query_expansion_decision_reason=None,
        retrieval_profile=request.retrieval_profile,
    )


def _execute_clinical_translation_search(
    request: SearchRequest,
    *,
    per_variant_top_k: int | None = None,
) -> SearchResponse:
    """Clinical v2 primary route: PT input becomes one EN retrieval query."""
    start = time.time()
    prepared = prepare_clinical_retrieval_query(request.query, use_llm=True)

    if prepared.get("blocked") or not prepared.get("retrieval_query"):
        total_latency_ms = int((time.time() - start) * 1000)
        fanout_summary = {
            "planner_latency_ms": total_latency_ms,
            "variant_count": 0,
            "executed_variant_count": 0,
            "skipped_variant_count": 1,
            "raw_result_count": 0,
            "deduped_result_count": 0,
            "duplicate_chunk_count": 0,
            "scope_filtered_count": 0,
            "generated_by": prepared.get("generated_by"),
            "desired_sections": list(DEFAULT_CLINICAL_SECTIONS),
            "detected_language": prepared.get("detected_language"),
            "translation_applied": bool(prepared.get("translated")),
            "translation_blocked": True,
            "translation_blocked_reason": prepared.get("blocked_reason"),
            "translated_query_hash": prepared.get("retrieval_query_hash"),
        }
        return SearchResponse(
            query=request.query,
            workspace_id=request.workspace_id,
            results=[],
            total_candidates=0,
            low_confidence=True,
            retrieval_time_ms=total_latency_ms,
            method="clinical_fanout",
            scores_breakdown={
                "clinical_fanout": fanout_summary,
                "clinical_scope_filter": {
                    "applied": True,
                    "kept_count": 0,
                    "removed_count": 0,
                    "removed_chunks": [],
                },
                "clinical_reranking": {
                    "applied": True,
                    "diversity_categories": [],
                    "selected_diversity_count": 0,
                    "remaining_count": 0,
                },
                "clinical_fanout_debug": {
                    "safe_for_admin_response": True,
                    "summary": fanout_summary,
                    "variants": [],
                    "chunks": [],
                },
            },
            retrieval_profile=request.retrieval_profile,
        )

    variant = ClinicalQueryVariant(
        variant_type="technical_en" if prepared.get("translated") else "original",
        query=str(prepared["retrieval_query"]),
        purpose=(
            "buscar na base vetorial com traducao clinica em ingles"
            if prepared.get("translated")
            else "buscar na base vetorial com a pergunta original em ingles"
        ),
        origin="llm" if prepared.get("translated") else "user_original",
    )
    variant_snapshot = _safe_query_variant_snapshot(variant, 0)
    variant_request = request.model_copy(
        update={
            "query": variant.query,
            "top_k": per_variant_top_k or max(request.top_k, 12),
            "reranking": False,
            "reranking_method": "none",
        }
    )
    variant_response = search_hybrid(variant_request)
    must_include_terms = _rick_professor_must_include_terms(prepared)
    gate_debug = _rick_professor_evidence_gate(
        variant_response.results,
        must_include_terms=must_include_terms,
    )
    raw_results = [
        _classify_search_result_item(item).model_copy(update={
            "query_variant": variant_snapshot,
            "query_variants": [variant_snapshot],
        })
        for item in variant_response.results
    ]
    plan = SimpleNamespace(
        species=prepared.get("species"),
        clinical_problem=prepared.get("clinical_problem"),
        canonical_terms_pt=[],
        canonical_terms_en=[str(prepared["retrieval_query"])],
        synonyms=[],
        desired_sections=list(DEFAULT_CLINICAL_SECTIONS),
        generated_by=prepared.get("generated_by"),
    )
    scope_filter_debug = {
        "applied": False,
        "kept_count": len(raw_results),
        "removed_count": 0,
        "removed_chunks": [],
        "mode": "rick_professor_passthrough",
    }
    merged_results, duplicate_count = _merge_clinical_fanout_candidates(raw_results)
    ranked_results = _rank_rick_professor_candidates(
        merged_results,
        must_include_terms=must_include_terms,
    )
    results, selection_debug = _select_rick_professor_evidence(
        ranked_results,
        max_total=6,
        max_per_source=2,
        min_distinct_sources=3,
    )
    reranking_debug = {
        "applied": True,
        "method": "rick_professor_source_diversity",
        "selected_count": len(results),
        "remaining_count": max(len(ranked_results) - len(results), 0),
    }
    fanout_summary = {
        "planner_latency_ms": int((time.time() - start) * 1000) - int(variant_response.retrieval_time_ms or 0),
        "variant_count": 1,
        "executed_variant_count": 1,
        "skipped_variant_count": 0,
        "raw_result_count": len(raw_results),
        "deduped_result_count": len(results),
        "duplicate_chunk_count": duplicate_count,
        "scope_filtered_count": scope_filter_debug["removed_count"],
        "generated_by": prepared.get("generated_by"),
        "desired_sections": list(DEFAULT_CLINICAL_SECTIONS),
        "detected_language": prepared.get("detected_language"),
        "translation_applied": bool(prepared.get("translated")),
        "translation_blocked": False,
        "translation_blocked_reason": None,
        "translated_query_hash": prepared.get("retrieval_query_hash") or _safe_text_hash(variant.query),
        "rick_professor_gate": gate_debug,
        "must_include_terms": must_include_terms,
    }
    total_latency_ms = int((time.time() - start) * 1000)
    return SearchResponse(
        query=request.query,
        workspace_id=request.workspace_id,
        results=results,
        total_candidates=variant_response.total_candidates,
        low_confidence=not results,
        retrieval_time_ms=variant_response.retrieval_time_ms or total_latency_ms,
        method="clinical_fanout",
        scores_breakdown={
            "clinical_fanout": fanout_summary,
            "clinical_scope_filter": scope_filter_debug,
            "clinical_reranking": reranking_debug,
            "clinical_rick_professor_selection": selection_debug,
            "clinical_fanout_debug": _build_clinical_fanout_debug(
                variants=[{
                    **variant_snapshot,
                    "executed": True,
                    "results_count": len(variant_response.results),
                    "total_candidates": variant_response.total_candidates,
                    "low_confidence": variant_response.low_confidence,
                    "retrieval_time_ms": variant_response.retrieval_time_ms,
                }],
                results=results,
                summary=fanout_summary,
            ),
        },
        reranking_applied=False,
        reranking_method=None,
        query_expansion_applied=False,
        query_expansion_method=None,
        query_expansion_fallback=False,
        query_expansion_requested=False,
        query_expansion_mode="off",
        query_expansion_decision_reason=None,
        retrieval_profile=request.retrieval_profile,
    )


def _safe_query_variant_snapshot(variant, index: int) -> dict:
    return {
        "variant_index": index,
        "variant_type": variant.variant_type,
        "origin": variant.origin,
        "purpose": variant.purpose,
        "context_preserved": variant.context_preserved,
        "blocked": variant.blocked,
        "blocked_reason": variant.blocked_reason,
    }


def _safe_text_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _build_clinical_fanout_debug(*, variants: list[dict], results: list, summary: dict) -> dict:
    return {
        "safe_for_admin_response": True,
        "summary": dict(summary),
        "variants": variants,
        "chunks": [
            {
                "chunk_id": item.chunk_id,
                "document_id": item.document_id,
                "document_filename": item.document_filename,
                "page_hint": item.page_hint,
                "best_score": item.score,
                "primary_clinical_category": item.primary_clinical_category,
                "clinical_categories": item.clinical_categories,
                "best_variant": item.query_variant,
                "matched_variants": item.query_variants,
            }
            for item in results
        ],
    }


def classify_clinical_candidate(text: str) -> dict:
    normalized = _normalize_text_for_clinical_category(text)
    matches = {}
    for category, keywords in CLINICAL_CATEGORY_KEYWORDS.items():
        matched_terms = [
            keyword for keyword in keywords
            if _normalize_text_for_clinical_category(keyword) in normalized
        ]
        if matched_terms:
            matches[category] = matched_terms

    categories = [
        category for category in CLINICAL_CATEGORY_PRIORITY
        if category in matches
    ]
    return {
        "primary_category": categories[0] if categories else None,
        "categories": categories,
        "matched_terms": matches,
    }


def _classify_search_result_item(item):
    classification = classify_clinical_candidate(item.text or "")
    return item.model_copy(update={
        "clinical_categories": classification["categories"],
        "primary_clinical_category": classification["primary_category"],
        "clinical_category_matches": classification["matched_terms"],
    })


def _normalize_text_for_clinical_category(text: str) -> str:
    normalized = re.sub(r"[\W_]+", " ", (text or "").lower(), flags=re.UNICODE)
    return f" {normalized.strip()} "


def _filter_clinical_scope_candidates(results: list, plan) -> tuple[list, dict]:
    kept = []
    removed = []
    for item in results:
        reason = _clinical_scope_rejection_reason(item, plan)
        if reason:
            removed.append({
                "chunk_id": item.chunk_id,
                "document_id": item.document_id,
                "score": item.score,
                "primary_clinical_category": item.primary_clinical_category,
                "clinical_categories": item.clinical_categories,
                "reason": reason,
                "best_variant": item.query_variant,
            })
            continue
        kept.append(item)
    return kept, {
        "applied": True,
        "kept_count": len(kept),
        "removed_count": len(removed),
        "removed_chunks": removed,
    }


def _clinical_scope_rejection_reason(item, plan) -> str | None:
    normalized = _normalize_text_for_clinical_category(item.text or "")
    if _looks_like_index_or_toc(normalized):
        return "index_or_toc"
    if _looks_like_table_or_figure_only(normalized):
        return "table_or_figure_only"
    if _looks_like_bibliography_only(normalized):
        return "bibliography_only"
    if not plan.clinical_problem and not _uses_llm_translation_retrieval(plan):
        return "clinical_plan_missing_problem"
    if _looks_nonclinical_operational_text(normalized) and _lacks_clinical_domain_signal(normalized, plan):
        return "nonclinical_domain"
    if _missing_expected_clinical_problem_signal(normalized, plan):
        return "missing_clinical_problem_signal"
    if _clinical_subject_mismatch(normalized, plan):
        return "clinical_scope_mismatch"
    return None


def _uses_llm_translation_retrieval(plan) -> bool:
    return getattr(plan, "generated_by", None) in {"llm_translation", "passthrough"}


def _looks_like_index_or_toc(normalized_text: str) -> bool:
    signals = [" table of contents ", " contents ", " index ", " list of figures ", " chapter "]
    if sum(1 for signal in signals if signal in normalized_text) >= 2:
        return True
    page_number_count = len(re.findall(r"\b\d{2,4}[tf]?\b", normalized_text))
    comma_like_entry_count = normalized_text.count(" ")
    if " see also " in normalized_text and page_number_count >= 8:
        return True
    return page_number_count >= 24 and comma_like_entry_count >= 160


def _looks_like_table_or_figure_only(normalized_text: str) -> bool:
    table_signals = [
        " figure ",
        " table ",
        " common causes ",
        " differential diagnoses ",
    ]
    if not any(signal in normalized_text for signal in table_signals):
        return False
    number_count = len(re.findall(r"\b\d+(?:\s|$)", normalized_text))
    return number_count >= 10


def _looks_like_bibliography_only(normalized_text: str) -> bool:
    reference_signals = [" references ", " bibliography ", " doi ", " isbn ", " journal "]
    clinical_signals = [
        " treatment ", " tratamento ", " therapy ", " exame ", " diagnostic ",
        " vomito ", " vomiting ", " pancreatite ", " pancreatitis ", " fluidoterapia ",
        " ultrassom ", " ultrasound ", " dor ", " pain ",
    ]
    if (
        sum(1 for signal in reference_signals if signal in normalized_text) >= 2
        and not any(signal in normalized_text for signal in clinical_signals)
    ):
        return True
    year_count = len(re.findall(r"\b(?:19|20)\d{2}\b", normalized_text))
    numbered_reference_count = len(re.findall(r"\b\d{1,3}\s+[a-z][a-z]+", normalized_text))
    reference_journal_signal = any(
        signal in normalized_text
        for signal in [" j vet ", " assoc ", " elsevier ", " veterinary record ", " vet med "]
    )
    return year_count >= 4 and numbered_reference_count >= 4 and reference_journal_signal


def _lacks_clinical_domain_signal(normalized_text: str, plan) -> bool:
    if any(signal in normalized_text for signal in CLINICAL_DOMAIN_SIGNALS):
        return False
    if any(term and term in normalized_text for term in _expected_clinical_problem_terms(plan)):
        return False
    if plan.species and not _contains_conflicting_species(normalized_text, plan.species):
        species_terms = {
            "cao": [" cao ", " caes ", " cachorro ", " canino ", " canine ", " dog "],
            "cadela": [" cadela ", " cachorra ", " cao ", " canino ", " canine ", " dog "],
            "gato": [" gato ", " gata ", " felino ", " feline ", " cat "],
        }
        if any(term in normalized_text for term in species_terms.get(plan.species, [])):
            return False
    return True


def _looks_nonclinical_operational_text(normalized_text: str) -> bool:
    operational_signals = [
        " reembolso ", " refund ", " pagamento ", " payment ", " nota fiscal ",
        " invoice ", " centro de custo ", " cost center ", " financeiro ",
        " billing ", " boleto ", " cartao ", " credit card ", " politica de ",
        " policy ", " fluxo de pagamento ", " fluxpay ",
    ]
    return any(signal in normalized_text for signal in operational_signals)


def _clinical_subject_mismatch(normalized_text: str, plan) -> bool:
    if plan.species and _contains_conflicting_species(normalized_text, plan.species):
        return True
    expected_terms = _clinical_problem_identity_terms(plan)
    has_expected = any(term in normalized_text for term in expected_terms)
    has_current_problem_conflict = any(
        term in normalized_text
        for term in _current_clinical_problem_conflict_terms(plan)
    )
    if has_current_problem_conflict and not has_expected:
        return True
    if len(normalized_text.split()) < 24:
        return False
    conflicting_terms = _conflicting_clinical_problem_terms(plan)
    has_conflict = any(term in normalized_text for term in conflicting_terms)
    if has_conflict and not has_expected:
        return True
    return False


def _missing_expected_clinical_problem_signal(normalized_text: str, plan) -> bool:
    if not plan.clinical_problem:
        return False
    # Keep unit-test fixtures and very short snippets usable; enforce strict
    # problem support on real book-sized candidates where drift is common.
    if len(normalized_text.split()) < 24:
        return False
    expected_terms = _clinical_problem_identity_terms(plan)
    if any(term and term in normalized_text for term in expected_terms):
        return False
    return True


def _contains_conflicting_species(normalized_text: str, species: str) -> bool:
    conflicts = {
        "cao": [" gato ", " gata ", " gatos ", " felino ", " felinos ", " feline ", " cat ", " cats "],
        "cadela": [" gato ", " gata ", " gatos ", " felino ", " felinos ", " feline ", " cat ", " cats "],
        "gato": [" cao ", " caes ", " cachorro ", " cachorros ", " canino ", " canine ", " dog ", " dogs "],
    }
    return any(term in normalized_text for term in conflicts.get(species, []))


def _expected_clinical_problem_terms(plan) -> list[str]:
    terms = [plan.clinical_problem or ""]
    terms.extend(plan.canonical_terms_pt)
    terms.extend(plan.canonical_terms_en)
    terms.extend(plan.synonyms)
    return [
        _normalize_text_for_clinical_category(term).strip()
        for term in terms
        if term
    ]


def _clinical_problem_identity_terms(plan) -> list[str]:
    terms = [plan.clinical_problem or ""]
    for rule in CLINICAL_PROBLEM_RULES:
        if rule.get("problem") != plan.clinical_problem:
            continue
        terms.extend(rule.get("patterns", []))
        terms.extend(rule.get("synonyms", []))
        canonical_en = rule.get("en", [])
        if canonical_en:
            terms.append(canonical_en[0])
        break
    return [
        _normalize_text_for_clinical_category(term).strip()
        for term in terms
        if term
    ]


def _conflicting_clinical_problem_terms(plan) -> list[str]:
    current_problem = plan.clinical_problem
    terms = []
    for rule in CLINICAL_PROBLEM_RULES:
        if rule.get("problem") == current_problem:
            continue
        terms.append(rule.get("problem", ""))
        terms.extend(rule.get("patterns", []))
        terms.extend(rule.get("pt", []))
        terms.extend(rule.get("en", []))
        terms.extend(rule.get("synonyms", []))
        terms.extend(rule.get("conflicts", []))
    return [
        _normalize_text_for_clinical_category(term).strip()
        for term in terms
        if term
    ]


def _current_clinical_problem_conflict_terms(plan) -> list[str]:
    terms = []
    for rule in CLINICAL_PROBLEM_RULES:
        if rule.get("problem") == plan.clinical_problem:
            terms.extend(rule.get("conflicts", []))
            break
    return [
        _normalize_text_for_clinical_category(term).strip()
        for term in terms
        if term
    ]


def _rerank_clinical_candidates_for_diversity(results: list, *, desired_sections: list[str]) -> tuple[list, dict]:
    if not results:
        return [], {
            "applied": True,
            "diversity_categories": [],
            "selected_diversity_count": 0,
            "remaining_count": 0,
        }

    category_order = _clinical_diversity_order(desired_sections)
    selected = []
    selected_categories = []
    selected_chunk_ids = set()
    for category in category_order:
        candidates = [
            item for item in results
            if item.chunk_id not in selected_chunk_ids and category in item.clinical_categories
        ]
        if not candidates:
            continue
        best = max(candidates, key=lambda item: float(item.score or 0.0))
        selected.append(best)
        selected_categories.append(category)
        selected_chunk_ids.add(best.chunk_id)

    remaining = [
        item for item in sorted(results, key=lambda item: float(item.score or 0.0), reverse=True)
        if item.chunk_id not in selected_chunk_ids
    ]
    reranked = selected + remaining
    return reranked, {
        "applied": True,
        "diversity_categories": selected_categories,
        "selected_diversity_count": len(selected),
        "remaining_count": len(remaining),
    }


def _clinical_diversity_order(desired_sections: list[str]) -> list[str]:
    requested = [
        section for section in desired_sections
        if section in CLINICAL_DIVERSITY_CATEGORY_ORDER
    ]
    return requested + [
        category for category in CLINICAL_DIVERSITY_CATEGORY_ORDER
        if category not in requested
    ]


def _merge_clinical_fanout_candidates(results: list) -> tuple[list, int]:
    by_chunk = {}
    origin_order = {}
    duplicate_count = 0
    for result in results:
        chunk_id = result.chunk_id
        variant_snapshot = result.query_variant or {}
        if chunk_id not in by_chunk:
            by_chunk[chunk_id] = result
            origin_order[chunk_id] = [variant_snapshot] if variant_snapshot else []
            continue

        duplicate_count += 1
        current = by_chunk[chunk_id]
        origin_order[chunk_id].append(variant_snapshot)
        if float(result.score or 0.0) > float(current.score or 0.0):
            by_chunk[chunk_id] = result

    merged = []
    for chunk_id, result in by_chunk.items():
        origins = _dedupe_query_variant_origins(origin_order.get(chunk_id, []))
        merged.append(result.model_copy(update={
            "query_variants": origins,
            "query_variant": result.query_variant or (origins[0] if origins else None),
        }))
    return sorted(merged, key=lambda item: float(item.score or 0.0), reverse=True), duplicate_count


def _rick_professor_must_include_terms(prepared: dict) -> list[str]:
    explicit_terms = [
        str(term).strip()
        for term in prepared.get("must_include_terms", [])
        if str(term).strip()
    ]
    if explicit_terms:
        return _dedupe_text_terms(explicit_terms)

    terms = []
    clinical_problem = str(prepared.get("clinical_problem") or "").strip()
    if clinical_problem:
        terms.append(clinical_problem)
    species = str(prepared.get("species") or "").strip()
    if species:
        species_terms = {
            "cao": ["dog", "canine"],
            "cadela": ["dog", "canine"],
            "gato": ["cat", "feline"],
        }
        terms.extend(species_terms.get(species, [species]))
    for rule in CLINICAL_PROBLEM_RULES:
        if rule.get("problem") != clinical_problem:
            continue
        terms.extend(rule.get("en", [])[:4])
        terms.extend(rule.get("synonyms", [])[:3])
        break
    if not terms and prepared.get("retrieval_query"):
        terms.extend(str(prepared["retrieval_query"]).split()[:6])
    return _dedupe_text_terms(terms)


def _dedupe_text_terms(terms: list[str]) -> list[str]:
    deduped = []
    seen = set()
    for term in terms:
        normalized = _normalize_text_for_clinical_category(term).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(term)
    return deduped


def _rick_professor_evidence_gate(results: list, *, must_include_terms: list[str]) -> dict:
    has_hits = bool(results)
    top_score = float(getattr(results[0], "score", 0.0) or 0.0) if has_hits else 0.0
    context = _normalize_text_for_clinical_category(
        "\n\n".join(getattr(item, "text", "") or "" for item in results)
    )
    normalized_terms = [
        _normalize_text_for_clinical_category(term).strip()
        for term in must_include_terms
        if term
    ]
    hit_count = sum(1 for term in normalized_terms if term and term in context)
    must_coverage = hit_count / len(normalized_terms) if normalized_terms else 0.0
    approved_strong = must_coverage >= 0.125 or top_score >= 0.62
    approved_soft = has_hits and top_score >= 0.55
    approved = approved_strong or approved_soft
    return {
        "approved": approved,
        "approved_strong": approved_strong,
        "approved_soft": approved_soft,
        "has_hits": has_hits,
        "top_score": top_score,
        "must_coverage": must_coverage,
        "must_hit_count": hit_count,
        "must_term_count": len(normalized_terms),
    }


def _rank_rick_professor_candidates(results: list, *, must_include_terms: list[str]) -> list:
    normalized_terms = [
        _normalize_text_for_clinical_category(term).strip()
        for term in must_include_terms
        if term
    ]
    ranked = []
    for item in results:
        normalized_text = _normalize_text_for_clinical_category(item.text or "")
        must_hits = sum(1 for term in normalized_terms if term and term in normalized_text)
        rank_score = float(item.score or 0.0) + (must_hits * 0.08)
        ranked.append((rank_score, must_hits, item))
    ranked.sort(key=lambda entry: entry[0], reverse=True)
    return [
        item.model_copy(update={
            "score": item.score,
        })
        for _, _, item in ranked
    ]


def _select_rick_professor_evidence(
    items: list,
    *,
    max_total: int = 6,
    max_per_source: int = 2,
    min_distinct_sources: int = 3,
) -> tuple[list, dict]:
    deduped = _dedupe_rick_professor_evidence(items)
    selected = []
    per_source: dict[str, int] = {}

    for item in deduped:
        source = _rick_professor_source_key(item)
        if per_source.get(source, 0) >= 1:
            continue
        selected.append(item)
        per_source[source] = per_source.get(source, 0) + 1
        if len(selected) >= max_total:
            break

    distinct_sources = len(per_source)
    for item in deduped:
        if len(selected) >= max_total:
            break
        if any(existing.chunk_id == item.chunk_id for existing in selected):
            continue
        source = _rick_professor_source_key(item)
        used = per_source.get(source, 0)
        allowed_per_source = max_per_source if distinct_sources >= min_distinct_sources else 1
        if used >= allowed_per_source:
            continue
        selected.append(item)
        per_source[source] = used + 1

    if len(selected) < max_total:
        for item in deduped:
            if len(selected) >= max_total:
                break
            if any(existing.chunk_id == item.chunk_id for existing in selected):
                continue
            source = _rick_professor_source_key(item)
            used = per_source.get(source, 0)
            if used >= max_per_source:
                continue
            selected.append(item)
            per_source[source] = used + 1

    return selected, {
        "applied": True,
        "selected_count": len(selected),
        "candidate_count": len(items),
        "deduped_count": len(deduped),
        "max_total": max_total,
        "max_per_source": max_per_source,
        "source_counts": per_source,
    }


def _dedupe_rick_professor_evidence(items: list) -> list:
    seen = set()
    deduped = []
    for item in items:
        text = " ".join((item.text or "").split())
        if not text:
            continue
        key = (_rick_professor_source_key(item), text[:280])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _rick_professor_source_key(item) -> str:
    return str(
        getattr(item, "document_filename", None)
        or getattr(item, "document_id", None)
        or getattr(item, "source", None)
        or "fonte_desconhecida"
    )


def _dedupe_query_variant_origins(origins: list[dict]) -> list[dict]:
    deduped = []
    seen = set()
    for origin in origins:
        if not origin:
            continue
        key = (
            origin.get("variant_index"),
            origin.get("variant_type"),
            origin.get("origin"),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(origin)
    return deduped


def search_and_answer_clinical_v2(request: QueryRequest) -> QueryResponse:
    """Clinical RAG v2 pipeline: translation-gated retrieval -> evidence pack -> structured answer."""
    start_total = time.time()
    search_req = SearchRequest(
        query=request.query,
        workspace_id=request.workspace_id,
        top_k=request.top_k,
        threshold=request.threshold,
        retrieval_mode="clinical_fanout",
        reranking=request.reranking,
        reranking_method=request.reranking_method,
        query_expansion_mode="off",
        retrieval_profile="clinical_v2",
    )
    search_resp = execute_clinical_fanout_search(search_req)
    evidence_pack = build_clinical_evidence_pack(
        search_resp,
        required_sections=_clinical_desired_sections_from_search(search_resp),
    )
    generated = generate_clinical_answer_from_evidence_pack(evidence_pack, use_llm=True)
    generated = reduce_unsupported_clinical_answer(generated, evidence_pack)

    citations = _clinical_citations_from_evidence_pack(evidence_pack)
    citation_coverage = 1.0 if generated.bibliography and generated.guardrails.bibliographic_grounding else 0.0
    grounded = bool(generated.guardrails.bibliographic_grounding and not generated.guardrails.unsupported_claims)
    final_low_confidence = not search_resp.results or not grounded
    confidence = _clinical_confidence(
        has_results=bool(search_resp.results),
        grounded=grounded,
        completeness_status=generated.completeness_status,
    )
    grounding_result = GroundingReport(
        grounded=grounded,
        citation_coverage=citation_coverage,
        uncited_claims=list(generated.guardrails.unsupported_claims),
        needs_review=not grounded,
        reason=_clinical_grounding_reason(
            grounded=grounded,
            generated=generated,
            search_resp=search_resp,
        ),
    )
    total_latency = int((time.time() - start_total) * 1000)

    _log_query({
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "workspace_id": request.workspace_id,
        "query": request.query,
        "answer": generated.answer_markdown,
        "confidence": confidence,
        "grounded": grounded,
        "chunks_used": generated.evidence_chunk_ids,
        "citation_coverage": citation_coverage,
        "low_confidence": final_low_confidence,
        "retrieval_low_confidence": search_resp.low_confidence,
        "retrieval_time_ms": search_resp.retrieval_time_ms,
        "total_latency_ms": total_latency,
        "results_count": len(search_resp.results),
        "top_result_score": search_resp.results[0].score if search_resp.results else None,
        "threshold": request.threshold,
        "grounding_reason": grounding_result.reason,
        "uncited_claims_count": len(generated.guardrails.unsupported_claims),
        "needs_review": grounding_result.needs_review,
        "reranking_applied": search_resp.reranking_applied,
        "reranking_method": search_resp.reranking_method,
        "candidate_count": search_resp.total_candidates,
        "query_expansion_applied": False,
        "query_expansion_method": None,
        "query_expansion_fallback": False,
        "query_expansion_requested": False,
        "query_expansion_mode": "off",
        "query_expansion_decision_reason": None,
        "retrieval_profile": "clinical_v2",
        "detected_language": _clinical_translation_summary(search_resp).get("detected_language"),
        "translation_applied": _clinical_translation_summary(search_resp).get("translation_applied"),
        "translation_blocked": _clinical_translation_summary(search_resp).get("translation_blocked"),
        "translation_blocked_reason": _clinical_translation_summary(search_resp).get("translation_blocked_reason"),
        "translated_query_hash": _clinical_translation_summary(search_resp).get("translated_query_hash"),
    })

    return QueryResponse(
        answer=generated.answer_markdown,
        answer_markdown=generated.answer_markdown,
        chunks_used=generated.evidence_chunk_ids,
        citations=citations,
        confidence=confidence,
        grounded=grounded,
        grounding=grounding_result,
        citation_coverage=citation_coverage,
        low_confidence=final_low_confidence,
        retrieval={
            **search_resp.model_dump(),
            "retrieval_low_confidence": search_resp.low_confidence,
            "low_confidence_reason": "clinical_v2_no_results" if not search_resp.results else None,
            "clinical_evidence_pack": evidence_pack.model_dump(),
            "clinical_generation": {
                "generated_by": generated.generated_by,
                "completeness_status": generated.completeness_status,
                "completeness_note": generated.completeness_note,
                "section_citation_map": generated.section_citation_map,
                "section_grounding": generated.section_grounding,
                "guardrail_reasons": _clinical_guardrail_reasons(
                    generated=generated,
                    search_resp=search_resp,
                ),
            },
        },
        latency_ms=total_latency,
        query_expansion_applied=False,
        query_expansion_method=None,
        query_expansion_fallback=False,
        query_expansion_requested=False,
        query_expansion_mode="off",
        query_expansion_decision_reason=None,
        retrieval_profile="clinical_v2",
        sections=generated.sections,
        bibliography=generated.bibliography,
        bibliography_footer=generated.bibliography_footer,
        missing_sections=generated.missing_sections,
        guardrails=generated.guardrails,
        completeness_status=generated.completeness_status,
        completeness_note=generated.completeness_note,
        section_citation_map=generated.section_citation_map,
        section_grounding=generated.section_grounding,
    )


def _clinical_translation_summary(search_resp: SearchResponse) -> dict:
    return (search_resp.scores_breakdown or {}).get("clinical_fanout", {})


def _clinical_citations_from_evidence_pack(evidence_pack) -> list[Citation]:
    citations_by_chunk: dict[str, Citation] = {}
    section_order: dict[str, list[str]] = {}
    for section_key, section in evidence_pack.sections.items():
        for item in section.items:
            if item.chunk_id not in citations_by_chunk:
                citations_by_chunk[item.chunk_id] = Citation(
                    chunk_id=item.chunk_id,
                    document_id=item.document_id,
                    document_filename=item.document_filename,
                    page=item.page,
                    text=item.text[:300] + "..." if len(item.text) > 300 else item.text,
                    score=item.score,
                    section=section_key,
                    sections=[section_key],
                )
                section_order[item.chunk_id] = [section_key]
                continue
            if section_key not in section_order[item.chunk_id]:
                section_order[item.chunk_id].append(section_key)

    return [
        citation.model_copy(update={"sections": section_order[citation.chunk_id]})
        for citation in citations_by_chunk.values()
    ]


def _clinical_desired_sections_from_search(search_resp: SearchResponse) -> list[str] | None:
    desired_sections = (
        (search_resp.scores_breakdown or {})
        .get("clinical_fanout", {})
        .get("desired_sections")
    )
    if not isinstance(desired_sections, list):
        return None
    return [section for section in desired_sections if isinstance(section, str)]


def _clinical_guardrail_reasons(*, generated, search_resp: SearchResponse) -> list[str]:
    reasons = []
    if not generated.guardrails.scope_preserved:
        reasons.append("scope_not_preserved")
    if not generated.guardrails.translation_context_preserved:
        reasons.append("translation_context_not_preserved")
    if generated.guardrails.unsupported_claims:
        reasons.append(f"unsupported_claims:{len(generated.guardrails.unsupported_claims)}")
    if not generated.guardrails.bibliographic_grounding:
        reasons.append("missing_bibliographic_grounding")
    if generated.completeness_status == "partial":
        reasons.append(f"partial_evidence:{','.join(generated.missing_sections)}")

    scope_filter = (search_resp.scores_breakdown or {}).get("clinical_scope_filter", {})
    removed_count = int(scope_filter.get("removed_count") or 0)
    if removed_count:
        removed_reasons = sorted({
            item.get("reason", "unknown")
            for item in scope_filter.get("removed_chunks", [])
        })
        reasons.append(f"scope_filter_removed:{removed_count}:{','.join(removed_reasons)}")
    return reasons or ["clinical_v2_grounded"]


def _clinical_grounding_reason(*, grounded: bool, generated, search_resp: SearchResponse) -> str:
    status = "clinical_v2_grounded" if grounded else "clinical_v2_unsupported_or_missing_bibliography"
    reasons = _clinical_guardrail_reasons(generated=generated, search_resp=search_resp)
    return (
        f"{status}; completeness={generated.completeness_status}; "
        f"missing_sections={','.join(generated.missing_sections) or 'none'}; "
        f"guardrail_reasons={'|'.join(reasons)}"
    )


def _clinical_confidence(*, has_results: bool, grounded: bool, completeness_status: str) -> str:
    if not has_results or not grounded:
        return "low"
    if completeness_status == "partial":
        return "medium"
    return "high"


def search_and_answer(
    request: QueryRequest
) -> QueryResponse:
    """
    Full pipeline:
    1. Hybrid search (dense + sparse + RRF)
    2. If low confidence → return low confidence response
    3. Generate answer using LLM
    4. Verify grounding (citations coverage)
    5. Log query
    6. Return response
    """
    if request.retrieval_profile == "clinical_v2":
        return search_and_answer_clinical_v2(request)

    start_total = time.time()

    # ── Step 0/1: Retrieval profile + optional query expansion ─────────────
    if request.query_expansion_mode is not None:
        expansion_mode_override = request.query_expansion_mode
    elif request.query_expansion is not None:
        expansion_mode_override = "always" if request.query_expansion else "off"
    else:
        expansion_mode_override = None

    search_req = SearchRequest(
        query=request.query,
        workspace_id=request.workspace_id,
        top_k=request.top_k,
        threshold=request.threshold,
        retrieval_mode="híbrida",
        reranking=request.reranking,
        reranking_method=request.reranking_method,
        query_expansion_mode=expansion_mode_override,
        retrieval_profile=request.retrieval_profile,
    )
    search_resp = execute_search(
        search_req,
        default_query_expansion_mode="adaptive" if QUERY_EXPANSION_ENABLED else "off",
    )
    if _should_try_neural_query_retry(request, search_resp):
        retry_req = search_req.model_copy(
            update={
                "reranking": True,
                "reranking_method": "neural",
            }
        )
        retry_resp = execute_search(
            retry_req,
            default_query_expansion_mode="adaptive" if QUERY_EXPANSION_ENABLED else "off",
        )
        if _should_accept_neural_retry(search_resp, retry_resp):
            search_resp = retry_resp
    if _should_try_crosslingual_retry(request, search_resp):
        retry_query, _ = _build_crosslingual_retrieval_query(request.query)
        if retry_query:
            recovery_updates = {"query": retry_query}
            if request.reranking is None and request.reranking_method is None:
                recovery_updates["reranking"] = True
                recovery_updates["reranking_method"] = "neural"
            recovery_req = search_req.model_copy(update=recovery_updates)
            recovery_resp = execute_search(
                recovery_req,
                default_query_expansion_mode="adaptive" if QUERY_EXPANSION_ENABLED else "off",
            )
            if _should_accept_neural_retry(search_resp, recovery_resp):
                search_resp = recovery_resp

    expansion_requested = search_resp.query_expansion_requested
    expansion_decision_reason = search_resp.query_expansion_decision_reason
    expansion_applied = search_resp.query_expansion_applied
    expansion_fallback = search_resp.query_expansion_fallback
    expansion_method = search_resp.query_expansion_method
    expansion_mode = search_resp.query_expansion_mode
    effective_profile = search_resp.retrieval_profile

    # ── Step 2: Build answer from chunks ─────────────────────
    chunks_data = []
    answer_results = [
        result for result in search_resp.results
        if float(result.score or 0.0) >= float(request.threshold or 0.0)
    ]
    if not answer_results:
        answer_results = list(search_resp.results)

    for result in answer_results:
        chunks_data.append({
            "chunk_id": result.chunk_id,
            "document_id": result.document_id,
            "document_filename": result.document_filename,
            "text": result.text,
            "score": result.score,
            "page_hint": result.page_hint,
            "source": result.source
        })

    retrieval_low_confidence = bool(search_resp.low_confidence)
    retrieval_has_minimal_support = True
    if retrieval_low_confidence:
        retrieval_has_minimal_support = _query_has_minimal_support(request.query, chunks_data)

    # ── Step 3: Generate answer ───────────────────────────────
    if not search_resp.results:
        answer = "Não tenho informações suficientes para responder a esta pergunta de forma precisa."
        confidence = "low"
        grounded = False
        chunks_used = []
        citations = []
        grounding_result = GroundingReport(
            grounded=False,
            citation_coverage=0.0,
            uncited_claims=[],
            needs_review=True,
            reason="No results retrieved or low confidence",
        )
        citation_coverage = 0.0
        final_low_confidence = True
        low_confidence_reason = "no_results"
    elif retrieval_low_confidence and not retrieval_has_minimal_support:
        answer = "Não tenho informações suficientes para responder a esta pergunta de forma precisa."
        confidence = "low"
        grounded = False
        chunks_used = []
        citations = []
        grounding_result = GroundingReport(
            grounded=False,
            citation_coverage=0.0,
            uncited_claims=[],
            needs_review=True,
            reason="Retrieved context does not support the query terms",
        )
        citation_coverage = 0.0
        final_low_confidence = True
        low_confidence_reason = "weak_query_support"
    else:
        answer_text, chunk_ids, llm_latency = generate_answer(
            query=request.query,
            chunks=chunks_data
        )
        answer = answer_text
        chunks_used = chunk_ids
        # RRF scores are rank-based, not probabilities
        # low_confidence already handles quality gating, so here we just use "high"
        confidence = "high"

        # Build citations with full text (not truncated for internal use)
        citations = []
        for c in chunks_data:
            citations.append(Citation(
                chunk_id=c["chunk_id"],
                document_id=c.get("document_id"),
                document_filename=c.get("document_filename"),
                page=c.get("page_hint"),
                text=c["text"],
                score=c["score"]
            ))

        document_filenames = {
            c["document_id"]: c.get("document_filename")
            for c in chunks_data
            if c.get("document_id") and c.get("document_filename")
        }
        citations = enrich_citations_with_filename(citations, document_filenames)

        # ── Step 4: Verify grounding ─────────────────────────
        grounding_result = GroundingReport(**verify_grounding(answer, citations))
        if _should_try_grounded_reanswer(request, retrieval_low_confidence, grounding_result):
            strict_answer_text, strict_chunk_ids, _ = generate_answer(
                query=request.query,
                chunks=chunks_data,
                system_prompt=STRICT_GROUNDED_SYSTEM_PROMPT,
            )
            strict_grounding = GroundingReport(**verify_grounding(strict_answer_text, citations))
            if _should_accept_grounded_reanswer(grounding_result, strict_grounding, strict_answer_text):
                answer = strict_answer_text
                chunks_used = strict_chunk_ids
                grounding_result = strict_grounding
        grounded = grounding_result.grounded
        citation_coverage = grounding_result.citation_coverage
        final_low_confidence, low_confidence_reason = _finalize_low_confidence(
            retrieval_low_confidence=retrieval_low_confidence,
            has_results=bool(search_resp.results),
            grounding_result=grounding_result,
            allow_grounding_override=retrieval_has_minimal_support,
        )
        if _answer_is_abstention(answer):
            final_low_confidence = True
            low_confidence_reason = "abstained"
            confidence = "low"
        elif not grounding_result.grounded or grounding_result.needs_review:
            final_low_confidence = True
            low_confidence_reason = "grounding_needs_review"
            confidence = "medium"
        else:
            confidence = "medium" if final_low_confidence else ("medium" if retrieval_low_confidence else "high")

        # Truncate citation text for response (keep first 300 chars)
        citations = [
            Citation(
                chunk_id=c.chunk_id,
                document_id=c.document_id,
                document_filename=c.document_filename,
                page=c.page,
                text=c.text[:300] + "..." if len(c.text) > 300 else c.text,
                score=c.score
            )
            for c in citations
        ]

    total_latency = int((time.time() - start_total) * 1000)

    # ── Step 5: Log query ──────────────────────────────────────
    _log_query({
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "workspace_id": request.workspace_id,
        "query": request.query,
        "answer": answer,
        "confidence": confidence,
        "grounded": grounded,
        "chunks_used": chunks_used,
        "citation_coverage": citation_coverage,
        "low_confidence": final_low_confidence,
        "retrieval_low_confidence": retrieval_low_confidence,
        "retrieval_time_ms": search_resp.retrieval_time_ms,
        "total_latency_ms": total_latency,
        "results_count": len(search_resp.results),
        "top_result_score": search_resp.results[0].score if search_resp.results else None,
        "threshold": request.threshold,
        "grounding_reason": (
            f"{grounding_result.reason}; low_confidence={low_confidence_reason}"
            if grounding_result and grounding_result.reason
            else f"low_confidence={low_confidence_reason}"
        ),
        "uncited_claims_count": len(grounding_result.uncited_claims) if grounding_result else 0,
        "needs_review": grounding_result.needs_review if grounding_result else None,
        "reranking_applied": search_resp.reranking_applied,
        "reranking_method": search_resp.reranking_method,
        "candidate_count": search_resp.total_candidates,
        "query_expansion_applied": expansion_applied,
        "query_expansion_method": expansion_method,
        "query_expansion_fallback": expansion_fallback,
        "query_expansion_requested": expansion_requested,
        "query_expansion_mode": expansion_mode,
        "query_expansion_decision_reason": expansion_decision_reason,
        "retrieval_profile": effective_profile,
    })

    return QueryResponse(
        answer=answer,
        chunks_used=chunks_used,
        citations=citations,
        confidence=confidence,
        grounded=grounded,
        grounding=grounding_result,
        citation_coverage=citation_coverage,
        low_confidence=final_low_confidence,
        retrieval={
            **search_resp.model_dump(),
            "retrieval_low_confidence": retrieval_low_confidence,
            "low_confidence_reason": low_confidence_reason,
        },
        latency_ms=total_latency,
        query_expansion_applied=expansion_applied,
        query_expansion_method=expansion_method,
        query_expansion_fallback=expansion_fallback,
        query_expansion_requested=expansion_requested,
        query_expansion_mode=expansion_mode,
        query_expansion_decision_reason=expansion_decision_reason,
        retrieval_profile=effective_profile,
    )


def _log_query(log_entry: dict):
    """Log query to JSON Lines file."""
    try:
        telemetry = get_telemetry()
        telemetry.log_query(
            query=log_entry.get("query", ""),
            workspace_id=log_entry.get("workspace_id", "default"),
            answer=log_entry.get("answer", ""),
            confidence=log_entry.get("confidence", "low"),
            grounded=log_entry.get("grounded", False),
            chunks_used=log_entry.get("chunks_used", []),
            retrieval_time_ms=log_entry.get("retrieval_time_ms", 0),
            total_latency_ms=log_entry.get("total_latency_ms", 0),
            low_confidence=log_entry.get("low_confidence", False),
            results_count=log_entry.get("results_count", 0),
            citation_coverage=log_entry.get("citation_coverage", 0.0),
            top_result_score=log_entry.get("top_result_score"),
            threshold=log_entry.get("threshold"),
            grounding_reason=log_entry.get("grounding_reason"),
            uncited_claims_count=log_entry.get("uncited_claims_count", 0),
            needs_review=log_entry.get("needs_review"),
            request_id=log_entry.get("request_id") or get_request_id(),
            reranking_applied=log_entry.get("reranking_applied", False),
            reranking_method=log_entry.get("reranking_method"),
            candidate_count=log_entry.get("candidate_count"),
            query_expansion_applied=log_entry.get("query_expansion_applied", False),
            query_expansion_method=log_entry.get("query_expansion_method"),
            query_expansion_fallback=log_entry.get("query_expansion_fallback", False),
            query_expansion_requested=log_entry.get("query_expansion_requested", False),
            expansion_latency_ms=log_entry.get("expansion_latency_ms", 0),
            query_expansion_mode=log_entry.get("query_expansion_mode"),
            query_expansion_decision_reason=log_entry.get("query_expansion_decision_reason"),
            retrieval_profile=log_entry.get("retrieval_profile"),
            detected_language=log_entry.get("detected_language"),
            translation_applied=log_entry.get("translation_applied"),
            translation_blocked=log_entry.get("translation_blocked"),
            translation_blocked_reason=log_entry.get("translation_blocked_reason"),
            translated_query_hash=log_entry.get("translated_query_hash"),
        )
    except Exception:
        pass  # Non-critical
