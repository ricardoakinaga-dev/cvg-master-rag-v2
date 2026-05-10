"""
Clinical pre-retrieval planner.

The planner creates a structured search plan. It must not answer the user.
"""
import hashlib
import json
import re
import time
import unicodedata
from typing import Any

from core.config import LLM_MODEL
from models.schemas import ClinicalQueryPlan, ClinicalQueryVariant
from services.llm_service import client as llm_client
from services.llm_service import _has_usable_api_key


CLINICAL_PLANNER_SYSTEM_PROMPT = """Você é um planejador de busca para RAG clínico veterinário.
Sua função é transformar a mensagem do usuário em um plano de busca JSON.

Regras obrigatórias:
- NÃO responda à pergunta do usuário.
- NÃO recomende tratamento, dose, diagnóstico ou conduta.
- NÃO invente informação ausente.
- Preserve espécie, doença, intenção, gravidade e contexto temporal.
- A pergunta original deve ser mantida como variante de busca.
- Gere termos técnicos em português e inglês apenas para retrieval.
- Retorne somente JSON válido."""

CLINICAL_PLANNER_USER_PROMPT = """Mensagem do usuário:
{query}

Retorne JSON com estes campos:
original_query, detected_language, species, clinical_problem, organ_system, intent,
canonical_terms_pt, canonical_terms_en, synonyms, required_terms, low_signal_terms,
desired_sections, query_variants, scope_warning, planner_notes, answers_user."""

CLINICAL_RETRIEVAL_TRANSLATION_SYSTEM_PROMPT = """Voce prepara queries para retrieval clinico veterinario.
Sua funcao e traduzir fielmente a pergunta do usuario para ingles quando ela estiver em portugues.

Regras obrigatorias:
- NAO responda ao usuario.
- NAO recomende conduta, dose, tratamento ou diagnostico.
- Preserve especie, problema clinico, intencao, gravidade e contexto temporal.
- Retorne uma query curta em ingles para buscar em base vetorial.
- Nao adicione detalhes clinicos que nao estejam implicitos na pergunta.
- Retorne somente JSON valido."""

CLINICAL_RETRIEVAL_TRANSLATION_USER_PROMPT = """Pergunta original:
{query}

Retorne JSON com estes campos:
retrieval_query, species, clinical_problem, intent."""
RICK_PROFESSOR_PREPROCESSOR_PROMPT = """Voce e um PRE-PROCESSADOR de perguntas clinicas veterinarias para um sistema RAG.

Voce NAO responde a pergunta final.
Voce prepara a consulta de forma segura, clara e estruturada.
===========================================
Tarefas obrigatorias:

1) Identificar o foco principal da pergunta (primary_focus).
2) Reescrever a pergunta em PT-BR clinico e claro (canonical_question_ptbr).
3) Gerar query tecnica em ingles (query_en) quando aplicavel.
4) Identificar se a pergunta EXIGE resposta numerica
   (dose, CRI, diluicao, taxa, mg/kg, mcg/kg/min, mL/h).
5) Identificar medicamentos e normalizar nomes PT <-> EN.
6) Definir termos que DEVEM aparecer na evidencia (must_include_terms).
7) Identificar termos que DEVEM SER EVITADOS para nao confundir o contexto (exclude_terms).
8) Detectar se faltam informacoes clinicas essenciais e gerar perguntas de clarificacao.
9) Gerar o campo input para embedding
   (usar ingles se query_en existir, senao PT-BR).
===============================================
Regras clinicas:

- Nao invente dados clinicos.
- Nao estime doses.
- Seja curto e tecnico.
- Se a pergunta envolver dose/CRI/diluicao, marque expects_numeric=true.
- Se faltar especie ou cenario em perguntas numericas, gere clarify_questions.
- Diferencie obrigatoriamente:
  - noradrenalina / norepinefrina -> norepinephrine (vasopressor)
  - adrenalina -> epinephrine
  - evitar associacao com glandula adrenal quando o foco for droga.
==============================================
Regra obrigatoria de foco clinico:
- Quando a pergunta mencionar uma doenca especifica (ex: parvovirose, cinomose, pancreatite),
  essa entidade DEVE aparecer em must_include_terms.
- Para parvovirose, incluir termos como:
  ["parvovirose", "canine parvovirus", "CPV", "parvo"]
============================================

A saida DEVE ser APENAS um JSON valido, sem texto extra.

Formato JSON obrigatorio:
{
  "canonical_question_ptbr": "...",
  "primary_focus": "...",
  "intent": "definicao|mecanismo|indicacao|dose|cri|diluicao|protocolo|diagnostico|outros",
  "expects_numeric": true|false,
  "drug": {
    "name_pt": "...|null",
    "name_en": "...|null",
    "synonyms": ["..."]
  },
  "must_include_terms": ["..."],
  "exclude_terms": ["..."],
  "clarify_questions": ["..."],
  "query_lang": "pt-BR|en",
  "query_en": "...",
  "input": "..."
}"""

DEFAULT_CLINICAL_SECTIONS = [
    "resumo",
    "historico_resenha",
    "sinais_sintomas",
    "exames_complementares",
    "tratamento_clinico",
    "proximos_passos",
    "referencias",
]

LOW_SIGNAL_TERMS = ["protocolo", "conduta", "manejo", "tratamento", "orientacao"]

SPECIES_TRANSLATION_TERMS = {
    "cao": ["dog", "canine"],
    "cadela": ["female dog", "dog", "canine"],
    "gato": ["cat", "feline"],
}

CONFLICTING_SPECIES_TERMS = {
    "cao": ["cat", "feline"],
    "cadela": ["cat", "feline"],
    "gato": ["dog", "canine"],
}

INTENT_TRANSLATION_TERMS = {
    "diagnostico": ["diagnosis"],
    "protocolo": ["protocol", "management"],
    "tratamento": ["treatment", "therapy"],
    "exames": ["diagnostic tests", "diagnosis"],
    "resumo": ["overview"],
}

CONTEXT_MARKER_TRANSLATIONS = {
    "acute": {
        "pt": ["aguda", "agudo"],
        "en": ["acute"],
    },
    "chronic": {
        "pt": ["cronica", "cronico"],
        "en": ["chronic"],
    },
    "initial": {
        "pt": ["inicial", "iniciais"],
        "en": ["initial"],
    },
    "severe": {
        "pt": ["grave", "severa", "severo"],
        "en": ["severe"],
    },
    "emergency": {
        "pt": ["emergencia", "urgencia"],
        "en": ["emergency"],
    },
    "recurrent": {
        "pt": ["recorrente", "recidivante"],
        "en": ["recurrent"],
    },
}

REQUIRED_LLM_PLAN_FIELDS = {
    "original_query",
    "detected_language",
    "species",
    "clinical_problem",
    "organ_system",
    "intent",
    "canonical_terms_pt",
    "canonical_terms_en",
    "synonyms",
    "required_terms",
    "low_signal_terms",
    "desired_sections",
    "query_variants",
    "scope_warning",
    "planner_notes",
    "answers_user",
}

CLINICAL_PROBLEM_RULES = [
    {
        "patterns": ["gastroenterite", "vomito", "diarreia"],
        "problem": "gastroenterite aguda",
        "organ_system": "gastrointestinal",
        "pt": ["gastroenterite", "vomito", "diarreia", "desidratacao", "fluidoterapia"],
        "en": ["gastroenteritis", "vomiting", "diarrhea", "dehydration", "fluid therapy"],
        "synonyms": ["enterite", "acute gastroenteritis", "acute diarrhea"],
    },
    {
        "patterns": ["hepatopatia", "hepatite", "figado", "hepatico"],
        "problem": "hepatopatia",
        "organ_system": "hepatobiliar",
        "pt": ["hepatopatia", "hepatite cronica", "figado", "acido ursodesoxicolico"],
        "en": ["hepatopathy", "chronic hepatitis", "liver disease", "ursodeoxycholic acid"],
        "synonyms": ["copper-associated hepatopathy", "hepatoprotective therapy", "SAMe"],
    },
    {
        "patterns": [
            "cardiomiopatia hipertrofica",
            "cardiomiopatia hipertrofica",
            "hcm",
            "hypertrophic cardiomyopathy",
        ],
        "problem": "cardiomiopatia hipertrofica",
        "organ_system": "cardiovascular",
        "pt": [
            "cardiomiopatia hipertrofica",
            "ecocardiografia",
            "sopro",
            "arritmia",
            "insuficiencia cardiaca",
        ],
        "en": [
            "hypertrophic cardiomyopathy",
            "echocardiography",
            "heart murmur",
            "arrhythmia",
            "heart failure",
        ],
        "synonyms": ["HCM", "feline hypertrophic cardiomyopathy", "cardiomyopathy"],
    },
    {
        "patterns": ["convulsao", "convulsao", "epilepsia"],
        "problem": "convulsao",
        "organ_system": "neurologico",
        "pt": ["convulsao", "epilepsia", "diazepam", "midazolam", "anticonvulsivante"],
        "en": ["seizure", "status epilepticus", "diazepam", "midazolam", "anticonvulsant"],
        "synonyms": ["crise convulsiva", "acute seizure", "epileptic seizure"],
    },
    {
        "patterns": [
            "trauma cranio encefalico",
            "trauma cranioencefalico",
            "traumatismo cranio encefalico",
            "traumatismo cranioencefalico",
            "tce",
            "head trauma",
            "traumatic brain injury",
        ],
        "problem": "trauma cranioencefalico",
        "organ_system": "neurologico",
        "pt": [
            "trauma cranioencefalico",
            "traumatismo cranioencefalico",
            "pressao intracraniana",
            "edema cerebral",
            "convulsao",
            "hipertensao intracraniana",
        ],
        "en": [
            "traumatic brain injury",
            "head trauma",
            "intracranial pressure",
            "cerebral edema",
            "seizure",
            "intracranial hypertension",
        ],
        "synonyms": ["TCE", "TBI", "brain trauma", "cranioencephalic trauma"],
        "conflicts": [
            "femoral head luxation",
            "hip joint",
            "luxation",
            "atlas",
            "axis",
            "spinal cord",
            "orthopedic",
        ],
    },
    {
        "patterns": ["drc", "doenca renal cronica", "renal cronica"],
        "problem": "doenca renal cronica",
        "organ_system": "renal",
        "pt": ["DRC", "doenca renal cronica", "creatinina", "ureia"],
        "en": ["chronic kidney disease", "creatinine", "blood urea nitrogen", "renal diet"],
        "synonyms": ["CKD", "chronic renal disease"],
    },
    {
        "patterns": ["pancreatite"],
        "problem": "pancreatite",
        "organ_system": "gastrointestinal",
        "pt": ["pancreatite", "ultrassom abdominal", "analgesia", "fluidoterapia"],
        "en": ["pancreatitis", "abdominal ultrasound", "analgesia", "fluid therapy"],
        "synonyms": ["canine pancreatitis", "pancreatic inflammation"],
    },
    {
        "patterns": ["piometra"],
        "problem": "piometra",
        "organ_system": "reprodutivo",
        "pt": ["piometra", "ultrassom", "ovariohisterectomia", "antibiotico"],
        "en": ["pyometra", "abdominal ultrasound", "ovariohysterectomy", "antibiotic"],
        "synonyms": ["uterine infection", "uterine pus"],
        "sections": DEFAULT_CLINICAL_SECTIONS + ["tratamento_cirurgico"],
    },
    {
        "patterns": [
            "corpo estranho linear",
            "corpo estranho gastrointestinal",
            "obstrucao gastrointestinal",
            "linear foreign body",
            "linear foreign bodies",
            "gastrointestinal foreign body",
            "gastrointestinal foreign bodies",
        ],
        "problem": "corpo estranho linear",
        "organ_system": "gastrointestinal",
        "pt": [
            "corpo estranho linear",
            "corpo estranho gastrointestinal",
            "obstrucao intestinal",
            "vomito",
            "dor abdominal",
            "peritonite",
        ],
        "en": [
            "linear foreign body",
            "gastrointestinal foreign body",
            "intestinal obstruction",
            "enterotomy",
            "gastrotomy",
            "peritonitis",
        ],
        "synonyms": ["string foreign body", "linear foreign bodies", "gastrointestinal foreign bodies"],
        "sections": DEFAULT_CLINICAL_SECTIONS + ["tratamento_cirurgico"],
        "conflicts": [
            "urethral obstruction",
            "urinary catheterization",
            "hyperkalemia",
            "obstrucao uretral",
            "cateterizacao",
        ],
    },
    {
        "patterns": ["obstrucao uretral", "obstrucao urinaria"],
        "problem": "obstrucao uretral",
        "organ_system": "urinario",
        "pt": ["obstrucao uretral", "hipercalemia", "cateterizacao", "fluidoterapia"],
        "en": ["urethral obstruction", "hyperkalemia", "urinary catheterization", "fluid therapy"],
        "synonyms": ["feline urethral obstruction", "blocked cat"],
        "sections": DEFAULT_CLINICAL_SECTIONS + ["tratamento_cirurgico"],
    },
]


class ClinicalQueryPlanValidationError(ValueError):
    """Raised when a clinical query plan is unsafe for retrieval."""


def plan_clinical_query(query: str, *, use_llm: bool = True) -> tuple[ClinicalQueryPlan, float]:
    """Create a structured clinical retrieval plan without answering the user."""
    start = time.time()
    fallback_reason = None
    if use_llm and _has_usable_api_key():
        try:
            plan = _plan_with_llm(query)
            latency = time.time() - start
            _log_planner_event(
                plan,
                latency_ms=int(latency * 1000),
                validation_status="accepted",
            )
            return plan, latency
        except ClinicalQueryPlanValidationError as exc:
            fallback_reason = str(exc)
        except Exception as exc:
            fallback_reason = exc.__class__.__name__
    plan = _deterministic_plan(query)
    latency = time.time() - start
    _log_planner_event(
        plan,
        latency_ms=int(latency * 1000),
        validation_status="accepted",
        fallback_reason=fallback_reason,
    )
    return plan, latency


def prepare_clinical_retrieval_query(query: str, *, use_llm: bool = True) -> dict[str, Any]:
    """Prepare the single query used by clinical_v2 retrieval.

    Portuguese input is translated to English before vector/hybrid retrieval.
    English input is passed through unchanged.
    """
    normalized = _normalize_text(query)
    if not _looks_portuguese(normalized):
        return {
            "original_query": query,
            "retrieval_query": query,
            "detected_language": "en",
            "translated": False,
            "generated_by": "passthrough",
            "blocked": False,
            "blocked_reason": None,
            "species": _detect_species(normalized),
            "clinical_problem": None,
            "intent": _detect_intent(normalized),
        }

    if not use_llm or not _has_usable_api_key():
        return _blocked_translation(query, "translation_unavailable")

    try:
        response = llm_client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": RICK_PROFESSOR_PREPROCESSOR_PROMPT},
                {"role": "user", "content": query},
            ],
            temperature=0.2,
            max_tokens=400,
            response_format={"type": "json_object"},
        )
        payload = json.loads(response.choices[0].message.content or "{}")
    except Exception:
        return _blocked_translation(query, "translation_failed")

    retrieval_query = _resolve_english_retrieval_query(payload, normalized_original=normalized)
    if not retrieval_query:
        return _blocked_translation(query, "translation_empty")
    normalized_payload = _normalize_translation_payload(
        payload,
        normalized_original=normalized,
        retrieval_query=retrieval_query,
    )
    blocked_reason = _translation_scope_block_reason(
        normalized_original=normalized,
        retrieval_query=retrieval_query,
        payload=normalized_payload,
    )
    if blocked_reason:
        return _blocked_translation(query, blocked_reason)

    return {
        "original_query": query,
        "retrieval_query": retrieval_query,
        "detected_language": "pt-BR",
        "translated": True,
        "generated_by": "llm_translation",
        "blocked": False,
        "blocked_reason": None,
        "species": normalized_payload.get("species") or _detect_species(normalized),
        "clinical_problem": normalized_payload.get("clinical_problem"),
        "intent": normalized_payload.get("intent") or _detect_intent(normalized),
        "canonical_question_ptbr": payload.get("canonical_question_ptbr") or query,
        "primary_focus": payload.get("primary_focus"),
        "expects_numeric": bool(payload.get("expects_numeric")),
        "drug": payload.get("drug") if isinstance(payload.get("drug"), dict) else None,
        "must_include_terms": _normalize_string_list(payload.get("must_include_terms")),
        "exclude_terms": _normalize_string_list(payload.get("exclude_terms")),
        "clarify_questions": _normalize_string_list(payload.get("clarify_questions")),
        "retrieval_query_hash": _safe_query_hash(retrieval_query),
    }


def _blocked_translation(query: str, reason: str) -> dict[str, Any]:
    return {
        "original_query": query,
        "retrieval_query": None,
        "detected_language": "pt-BR",
        "translated": False,
        "generated_by": reason,
        "blocked": True,
        "blocked_reason": reason,
        "species": _detect_species(_normalize_text(query)),
        "clinical_problem": None,
        "intent": _detect_intent(_normalize_text(query)),
        "retrieval_query_hash": None,
    }


def _normalize_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [
        str(item).strip()
        for item in value
        if str(item).strip()
    ]


def _resolve_english_retrieval_query(payload: dict[str, Any], *, normalized_original: str) -> str:
    query_en = str(payload.get("query_en") or "").strip()
    if query_en and not _looks_portuguese(_normalize_text(query_en)):
        return query_en

    retrieval_query = str(payload.get("retrieval_query") or "").strip()
    if retrieval_query and not _looks_portuguese(_normalize_text(retrieval_query)):
        return retrieval_query

    input_query = str(payload.get("input") or "").strip()
    if input_query and not _looks_portuguese(_normalize_text(input_query)):
        return input_query

    deterministic = _deterministic_english_query_from_original(normalized_original)
    if deterministic:
        return deterministic

    return ""


def _deterministic_english_query_from_original(normalized_original: str) -> str:
    rule = _match_problem_rule(normalized_original)
    species = _detect_species(normalized_original)
    intent = _detect_intent(normalized_original)
    terms = []
    if species:
        terms.extend(SPECIES_TRANSLATION_TERMS.get(species, [species]))
    terms.extend(INTENT_TRANSLATION_TERMS.get(intent, []))
    if rule:
        terms.extend(rule.get("en", []))
        terms.extend(rule.get("synonyms", []))
    context_terms = _context_marker_terms(normalized_original, "en")
    terms.extend(context_terms)
    return " ".join(_dedupe_preserving_order([
        str(term).strip()
        for term in terms
        if str(term).strip()
    ]))


def _dedupe_preserving_order(values: list[str]) -> list[str]:
    deduped = []
    seen = set()
    for value in values:
        key = _normalize_text(value)
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(value)
    return deduped


def _translation_scope_block_reason(
    *,
    normalized_original: str,
    retrieval_query: str,
    payload: dict[str, Any],
) -> str | None:
    original_species = _detect_species(normalized_original)
    translated_species = payload.get("species")
    if original_species and translated_species and translated_species != original_species:
        return "translation_species_conflict"

    translated_problem = str(payload.get("clinical_problem") or "").strip()
    if not translated_problem:
        return "translation_missing_clinical_problem"

    original_rule = _match_problem_rule(normalized_original)
    if original_rule and translated_problem != original_rule.get("problem"):
        return "translation_clinical_problem_conflict"

    original_intent = _detect_intent(normalized_original)
    translated_intent = str(payload.get("intent") or "").strip()
    if (
        original_intent != "unknown"
        and translated_intent
        and translated_intent != original_intent
        and not _retrieval_intents_are_compatible(original_intent, translated_intent)
        and not (original_rule and _retrieval_query_contains_problem_terms(retrieval_query, original_rule))
    ):
        return "translation_intent_conflict"

    if original_rule and not _retrieval_query_contains_problem_terms(retrieval_query, original_rule):
        return "translation_missing_clinical_problem_terms"

    return None


def _normalize_translation_payload(
    payload: dict[str, Any],
    *,
    normalized_original: str,
    retrieval_query: str,
) -> dict[str, Any]:
    normalized = dict(payload)
    normalized["species"] = _normalize_species_label(payload.get("species"))
    normalized["clinical_problem"] = _normalize_clinical_problem_label(
        payload.get("clinical_problem") or payload.get("primary_focus")
    )
    normalized["intent"] = _normalize_intent_label(payload.get("intent"))
    original_rule = _match_problem_rule(normalized_original)
    if (
        original_rule
        and _retrieval_query_contains_problem_terms(retrieval_query, original_rule)
        and _translation_problem_label_is_generic(normalized.get("clinical_problem"), original_rule)
    ):
        normalized["clinical_problem"] = original_rule.get("problem")
    return normalized


def _translation_problem_label_is_generic(value: Any, original_rule: dict[str, Any]) -> bool:
    if not value:
        return True
    if value == original_rule.get("problem"):
        return True
    normalized = _normalize_text(str(value))
    generic_terms = ["foreign body", "corpo estranho", "obstruction", "obstrucao"]
    return _contains_any(normalized, generic_terms)


def _retrieval_intents_are_compatible(original_intent: str, translated_intent: str) -> bool:
    if original_intent == "resumo":
        return True
    management_intents = {"resumo", "protocolo", "tratamento"}
    if original_intent in management_intents and translated_intent in management_intents:
        return True
    return False


def _normalize_species_label(value: Any) -> str | None:
    normalized = _normalize_text(str(value or ""))
    if normalized in {"cao", "caes", "canino", "canine", "dog", "dogs"}:
        return "cao"
    if normalized in {"cadela", "bitch"}:
        return "cadela"
    if normalized in {"gato", "gata", "gatos", "felino", "felinos", "feline", "cat", "cats"}:
        return "gato"
    return str(value).strip() if value else None


def _normalize_clinical_problem_label(value: Any) -> str | None:
    normalized = _normalize_text(str(value or ""))
    if not normalized:
        return None
    for rule in CLINICAL_PROBLEM_RULES:
        terms = [rule.get("problem", "")]
        terms.extend(rule.get("patterns", []))
        terms.extend(rule.get("pt", []))
        terms.extend(rule.get("en", []))
        terms.extend(rule.get("synonyms", []))
        if _contains_any(normalized, terms):
            return rule.get("problem")
    return str(value).strip()


def _normalize_intent_label(value: Any) -> str | None:
    normalized = _normalize_text(str(value or ""))
    if not normalized:
        return None
    if normalized in {"protocol", "protocolo", "approach", "management", "conduta", "manejo", "orientation", "orientacao"}:
        return "protocolo"
    if normalized in {"treatment", "therapy", "tratamento", "tratar"}:
        return "tratamento"
    if normalized in {"exam", "exams", "diagnostics", "exames"}:
        return "exames"
    if normalized in {"diagnosis", "diagnostico"}:
        return "diagnostico"
    if normalized in {"summary", "overview", "resumo", "explique"}:
        return "resumo"
    return str(value).strip()


def _retrieval_query_contains_problem_terms(retrieval_query: str, rule: dict[str, Any]) -> bool:
    normalized_retrieval = _normalize_text(retrieval_query)
    identity_terms = []
    identity_terms.extend(rule.get("en", []))
    identity_terms.extend(rule.get("synonyms", []))
    identity_terms.extend(rule.get("patterns", []))
    return _contains_any(normalized_retrieval, identity_terms)


def _safe_query_hash(query: str) -> str:
    return hashlib.sha256(query.encode("utf-8")).hexdigest()


def _plan_with_llm(query: str) -> ClinicalQueryPlan:
    response = llm_client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": CLINICAL_PLANNER_SYSTEM_PROMPT},
            {"role": "user", "content": CLINICAL_PLANNER_USER_PROMPT.format(query=query)},
        ],
        temperature=0,
        max_tokens=900,
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content or "{}"
    payload = json.loads(content)
    _validate_llm_payload_shape(payload)
    payload["original_query"] = query
    payload["answers_user"] = False
    payload["generated_by"] = "llm"
    payload["query_variants"] = _coerce_query_variants(query, payload.get("query_variants", []))
    plan = ClinicalQueryPlan(**payload)
    plan.query_variants = generate_clinical_query_fanout(plan)
    validate_translation_context_preserved(plan)
    validate_fanout_scope_preserved(plan)
    return validate_clinical_query_plan(plan, query)


def _deterministic_plan(query: str) -> ClinicalQueryPlan:
    normalized = _normalize_text(query)
    species = _detect_species(normalized)
    intent = _detect_intent(normalized)
    rule = _match_problem_rule(normalized)

    clinical_problem = rule.get("problem") if rule else None
    organ_system = rule.get("organ_system") if rule else None
    terms_pt = list(rule.get("pt", [])) if rule else []
    terms_en = list(rule.get("en", [])) if rule else []
    synonyms = list(rule.get("synonyms", [])) if rule else []
    sections = list(rule.get("sections", DEFAULT_CLINICAL_SECTIONS)) if rule else list(DEFAULT_CLINICAL_SECTIONS)

    variants = _build_variants(
        original_query=query,
        species=species,
        clinical_problem=clinical_problem,
        terms_pt=terms_pt,
        terms_en=terms_en,
        synonyms=synonyms,
    )
    plan = ClinicalQueryPlan(
        original_query=query,
        detected_language="pt-BR" if _looks_portuguese(normalized) else "unknown",
        species=species,
        clinical_problem=clinical_problem,
        organ_system=organ_system,
        intent=intent,
        canonical_terms_pt=terms_pt,
        canonical_terms_en=terms_en,
        synonyms=synonyms,
        required_terms=[term for term in [species, clinical_problem] if term],
        low_signal_terms=[term for term in LOW_SIGNAL_TERMS if term in normalized],
        desired_sections=sections,
        query_variants=variants,
        scope_warning=None if clinical_problem and species else "Pergunta ambigua: especie ou problema clinico incompleto.",
        planner_notes="Plano deterministico; nao responde ao usuario.",
        answers_user=False,
        generated_by="deterministic_fallback",
    )
    plan.query_variants = generate_clinical_query_fanout(plan)
    validate_translation_context_preserved(plan)
    validate_fanout_scope_preserved(plan)
    return validate_clinical_query_plan(plan, query)


def validate_clinical_query_plan(plan: ClinicalQueryPlan, original_query: str) -> ClinicalQueryPlan:
    """Validate that a plan can safely proceed to retrieval."""
    errors: list[str] = []
    if plan.original_query != original_query:
        errors.append("original_query_changed")
    if plan.answers_user:
        errors.append("answers_user_true")
    if not plan.desired_sections:
        errors.append("desired_sections_required")
    if not plan.query_variants:
        errors.append("query_variants_required")

    has_original_variant = any(
        variant.variant_type == "original" and variant.query == original_query
        for variant in plan.query_variants
    )
    if not has_original_variant:
        errors.append("original_variant_required")
    if any(not variant.origin for variant in plan.query_variants):
        errors.append("variant_origin_required")
    if any(not variant.purpose for variant in plan.query_variants):
        errors.append("variant_purpose_required")

    missing_scope = not plan.species or not plan.clinical_problem
    if missing_scope and not plan.scope_warning:
        errors.append("scope_warning_required")

    if not any([plan.canonical_terms_pt, plan.canonical_terms_en, plan.synonyms, plan.required_terms, plan.scope_warning]):
        errors.append("clinical_signal_required")

    if errors:
        raise ClinicalQueryPlanValidationError(",".join(errors))
    return plan


def _validate_llm_payload_shape(payload: Any) -> None:
    if not isinstance(payload, dict):
        raise ClinicalQueryPlanValidationError("payload_not_object")

    missing = sorted(field for field in REQUIRED_LLM_PLAN_FIELDS if field not in payload)
    if missing:
        raise ClinicalQueryPlanValidationError(f"missing_fields:{','.join(missing)}")


def generate_clinical_query_fanout(plan: ClinicalQueryPlan) -> list[ClinicalQueryVariant]:
    """Create ordered retrieval variants without replacing the user's query."""
    species_term_pt = plan.species or ""
    species_term_en = _translated_species_term(plan.species)
    context_terms_pt = _context_marker_terms(plan.original_query, "pt")
    context_terms_en = _context_marker_terms(plan.original_query, "en")
    intent_terms_pt = _intent_terms(plan.intent, "pt")
    intent_terms_en = _intent_terms(plan.intent, "en")
    variants = [
        ClinicalQueryVariant(
            variant_type="original",
            query=plan.original_query,
            purpose="preservar a frase original do usuario",
            origin="user_original",
        )
    ]
    if plan.canonical_terms_pt:
        variants.append(ClinicalQueryVariant(
            variant_type="technical_pt",
            query=" ".join([
                plan.clinical_problem or "",
                species_term_pt,
                *intent_terms_pt,
                *context_terms_pt,
                *plan.canonical_terms_pt,
            ]).strip(),
            purpose="buscar livros e chunks em portugues com termos tecnicos",
            origin="planner_terms_pt",
        ))
    if plan.canonical_terms_en:
        variants.append(ClinicalQueryVariant(
            variant_type="technical_en",
            query=" ".join([
                species_term_en,
                *intent_terms_en,
                *context_terms_en,
                *plan.canonical_terms_en,
            ]).strip(),
            purpose="buscar livros e chunks em ingles como rota adicional",
            origin="planner_terms_en",
        ))
    if plan.synonyms:
        variants.append(ClinicalQueryVariant(
            variant_type="synonyms",
            query=" ".join(plan.synonyms),
            purpose="aumentar recall com sinonimos sem alterar escopo clinico",
            origin="planner_synonyms",
        ))
    return _dedupe_variants(variants)


def validate_translation_context_preserved(plan: ClinicalQueryPlan) -> ClinicalQueryPlan:
    """Mark translated variants that alter species, clinical problem, intent, or temporal/severity context."""
    expected_problem_terms = [_normalize_text(term) for term in plan.canonical_terms_en]
    expected_problem_terms.extend(_normalize_text(term) for term in plan.synonyms)
    expected_markers = _detected_context_markers(plan.original_query)

    for variant in plan.query_variants:
        if variant.variant_type != "technical_en":
            continue

        normalized_query = _normalize_text(variant.query)
        errors = []
        if plan.species and not _contains_any(normalized_query, SPECIES_TRANSLATION_TERMS.get(plan.species, [])):
            errors.append("species_context_changed")
        if _contains_any(normalized_query, CONFLICTING_SPECIES_TERMS.get(plan.species or "", [])):
            errors.append("species_context_changed")
        if expected_problem_terms and not _contains_any(normalized_query, expected_problem_terms):
            errors.append("clinical_problem_context_changed")
        if not _contains_any(normalized_query, INTENT_TRANSLATION_TERMS.get(plan.intent, [])):
            errors.append("intent_context_changed")

        for marker in expected_markers:
            if not _contains_any(normalized_query, CONTEXT_MARKER_TRANSLATIONS[marker]["en"]):
                errors.append(f"{marker}_context_changed")

        if errors:
            variant.context_preserved = False
            variant.blocked = True
            variant.blocked_reason = ",".join(sorted(set(errors)))
        else:
            variant.context_preserved = True
            variant.blocked = False
            variant.blocked_reason = None
    return plan


def validate_fanout_scope_preserved(plan: ClinicalQueryPlan) -> ClinicalQueryPlan:
    """Reject a clinical plan whose fan-out would search outside the requested scope."""
    errors = []
    normalized_original = _normalize_text(plan.original_query)
    if plan.species and not _query_mentions_species(normalized_original, plan.species):
        errors.append("species_scope_changed")
    if plan.clinical_problem and not _query_mentions_clinical_problem(normalized_original, plan.clinical_problem):
        errors.append("clinical_problem_scope_changed")

    blocked_reasons = [
        variant.blocked_reason or "variant_blocked"
        for variant in plan.query_variants
        if variant.blocked or variant.context_preserved is False
    ]
    if blocked_reasons:
        errors.append(f"fanout_scope_changed:{';'.join(blocked_reasons)}")

    if errors:
        raise ClinicalQueryPlanValidationError(",".join(errors))
    return plan


def _log_planner_event(
    plan: ClinicalQueryPlan,
    *,
    latency_ms: int,
    validation_status: str,
    validation_error: str | None = None,
    fallback_reason: str | None = None,
) -> None:
    try:
        from services.telemetry_service import get_telemetry

        get_telemetry().log_clinical_query_plan(
            original_query=plan.original_query,
            detected_language=plan.detected_language,
            species=plan.species,
            clinical_problem=plan.clinical_problem,
            organ_system=plan.organ_system,
            intent=plan.intent,
            canonical_terms_pt=plan.canonical_terms_pt,
            canonical_terms_en=plan.canonical_terms_en,
            synonyms=plan.synonyms,
            required_terms=plan.required_terms,
            low_signal_terms=plan.low_signal_terms,
            desired_sections=list(plan.desired_sections),
            query_variants=plan.query_variants,
            scope_warning=plan.scope_warning,
            planner_notes=plan.planner_notes,
            answers_user=plan.answers_user,
            generated_by=plan.generated_by,
            latency_ms=latency_ms,
            validation_status=validation_status,
            validation_error=validation_error,
            fallback_reason=fallback_reason,
        )
    except Exception:
        pass


def _build_variants(
    *,
    original_query: str,
    species: str | None,
    clinical_problem: str | None,
    terms_pt: list[str],
    terms_en: list[str],
    synonyms: list[str],
) -> list[ClinicalQueryVariant]:
    species_term = species or ""
    variants = [
        ClinicalQueryVariant(
            variant_type="original",
            query=original_query,
            purpose="preservar a frase original do usuario",
            origin="user_original",
        )
    ]
    if terms_pt:
        variants.append(ClinicalQueryVariant(
            variant_type="technical_pt",
            query=" ".join([clinical_problem or "", species_term, *terms_pt]).strip(),
            purpose="buscar livros e chunks em portugues",
            origin="planner_terms_pt",
        ))
    if terms_en:
        variants.append(ClinicalQueryVariant(
            variant_type="technical_en",
            query=" ".join([species_term, *terms_en]).strip(),
            purpose="buscar livros e chunks em ingles",
            origin="planner_terms_en",
        ))
    if synonyms:
        variants.append(ClinicalQueryVariant(
            variant_type="synonyms",
            query=" ".join(synonyms),
            purpose="aumentar recall sem alterar escopo clinico",
            origin="planner_synonyms",
        ))
    return variants


def _coerce_query_variants(query: str, raw_variants: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_variants, list):
        return [{
            "variant_type": "original",
            "query": query,
            "purpose": "preservar a frase original",
            "origin": "user_original",
        }]
    variants = []
    has_original = False
    for item in raw_variants:
        if not isinstance(item, dict) or not item.get("query"):
            continue
        variant = {
            "variant_type": item.get("variant_type") or "synonyms",
            "query": str(item["query"]),
            "purpose": item.get("purpose"),
            "origin": item.get("origin") or "llm",
        }
        if variant["variant_type"] == "original":
            has_original = True
            variant["query"] = query
            variant["origin"] = "user_original"
        variants.append(variant)
    if not has_original:
        variants.insert(0, {
            "variant_type": "original",
            "query": query,
            "purpose": "preservar a frase original",
            "origin": "user_original",
        })
    return variants


def _dedupe_variants(variants: list[ClinicalQueryVariant]) -> list[ClinicalQueryVariant]:
    deduped = []
    seen = set()
    for variant in variants:
        normalized_query = _normalize_text(variant.query).strip()
        if not normalized_query or normalized_query in seen:
            continue
        seen.add(normalized_query)
        deduped.append(variant)
    return deduped


def _translated_species_term(species: str | None) -> str:
    terms = SPECIES_TRANSLATION_TERMS.get(species or "")
    return terms[0] if terms else (species or "")


def _intent_terms(intent: str, language: str) -> list[str]:
    if language == "en":
        return INTENT_TRANSLATION_TERMS.get(intent, [])
    return {
        "diagnostico": ["diagnostico"],
        "protocolo": ["protocolo"],
        "tratamento": ["tratamento"],
        "exames": ["exames"],
        "resumo": ["resumo"],
    }.get(intent, [])


def _detected_context_markers(text: str) -> list[str]:
    normalized = _normalize_text(text)
    markers = []
    for marker, terms in CONTEXT_MARKER_TRANSLATIONS.items():
        if _contains_any(normalized, terms["pt"] + terms["en"]):
            markers.append(marker)
    return markers


def _context_marker_terms(text: str, language: str) -> list[str]:
    key = "en" if language == "en" else "pt"
    terms = []
    for marker in _detected_context_markers(text):
        terms.append(CONTEXT_MARKER_TRANSLATIONS[marker][key][0])
    return terms


def _contains_any(normalized_text: str, terms: list[str]) -> bool:
    return any(_normalize_text(term) in normalized_text for term in terms if term)


def _query_mentions_species(normalized_query: str, species: str) -> bool:
    species_terms = {
        "cao": ["cao", "caes", "canino", "caninos", "cachorro", "cachorra"],
        "cadela": ["cadela", "cachorra", "cao", "canino"],
        "gato": ["gato", "gata", "gatos", "felino", "felinos"],
    }
    return _contains_any(normalized_query, species_terms.get(species, [species]))


def _query_mentions_clinical_problem(normalized_query: str, clinical_problem: str) -> bool:
    terms = [_normalize_text(clinical_problem)]
    for rule in CLINICAL_PROBLEM_RULES:
        if rule.get("problem") == clinical_problem:
            terms.extend(rule.get("patterns", []))
            terms.extend(rule.get("pt", []))
            terms.extend(rule.get("en", []))
            terms.extend(rule.get("synonyms", []))
            break
    return _contains_any(normalized_query, terms)


def _match_problem_rule(normalized_query: str) -> dict[str, Any] | None:
    for rule in CLINICAL_PROBLEM_RULES:
        if any(pattern in normalized_query for pattern in rule["patterns"]):
            return rule
    return None


def _detect_species(normalized_query: str) -> str | None:
    if re.search(r"\b(cao|caes|canino|caninos|cachorro|cachorra|cadela)\b", normalized_query):
        return "cadela" if "cadela" in normalized_query else "cao"
    if re.search(r"\b(gato|gata|gatos|felino|felinos)\b", normalized_query):
        return "gato"
    return None


def _detect_intent(normalized_query: str) -> str:
    if any(term in normalized_query for term in ["exame", "exames", "avaliacao", "diagnostico"]):
        return "exames" if "exame" in normalized_query or "exames" in normalized_query else "diagnostico"
    if any(term in normalized_query for term in ["tratamento", "tratar", "manejo"]):
        return "tratamento"
    if any(term in normalized_query for term in ["protocolo", "conduta", "orientacao", "conduzir", "prioridade", "prioridades"]):
        return "protocolo"
    if any(term in normalized_query for term in ["resumo", "explique"]):
        return "resumo"
    return "unknown"


def _looks_portuguese(normalized_query: str) -> bool:
    return any(
        term in normalized_query
        for term in [
            "cao",
            "caes",
            "gato",
            "gata",
            "gatos",
            "felino",
            "felina",
            "felinos",
            "como",
            "qual",
            "quais",
            "fale",
            "sobre",
            "conduta",
            "tratamento",
            "suspeita",
            "protocolo",
            "pancreatite",
            "trauma",
            "cranio",
        ]
    )


def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    without_accents = "".join(char for char in normalized if not unicodedata.combining(char))
    return without_accents.lower()
