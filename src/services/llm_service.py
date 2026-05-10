"""
LLM Service — GPT-4o-mini for answer generation with grounding.
"""
import os
import time
import re
from typing import Optional

from openai import OpenAI

from core.config import LLM_MODEL


client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))


SYSTEM_PROMPT = """Você é um assistente de IA que responde perguntas
usando SOMENTE o contexto fornecido abaixo.

Se o contexto cobrir apenas parte da pergunta, responda somente essa parte
e deixe claro que os trechos não trazem um protocolo completo.
Só diga "Não sei" quando os trechos não trouxerem nenhum fato útil
para a pergunta.
Responda em português."""

USER_PROMPT_TEMPLATE = """Contexto:
{context}

Pergunta: {query}

Resposta (use apenas informações do contexto):"""


STOPWORDS = {
    "a", "o", "os", "as", "de", "da", "do", "das", "dos", "e", "em", "no", "na", "nos", "nas",
    "para", "por", "com", "sem", "um", "uma", "uns", "umas", "que", "qual", "quais", "como",
    "onde", "quando", "porquê", "porque", "sobre", "ser", "ter", "mais", "menos",
}


def _has_usable_api_key() -> bool:
    api_key = (getattr(client, "api_key", "") or "").strip()
    if not api_key:
        return False
    placeholder_values = {
        "test-key",
        "sk-your-key-here",
        "sk-...your-key...",
        "your-api-key",
        "changeme",
    }
    return api_key.lower() not in placeholder_values


def _normalize_query_terms(query: str) -> list[str]:
    tokens = re.findall(r"\b[\wÀ-ÿ]{3,}\b", query.lower())
    return [token for token in tokens if token not in STOPWORDS]


def _split_chunk_units(text: str) -> list[str]:
    units = []
    for raw_line in text.splitlines():
        line = raw_line.strip(" -*\t")
        if not line:
            continue
        parts = re.split(r"(?<=[.!?])\s+", line)
        for part in parts:
            sentence = part.strip()
            if sentence:
                units.append(sentence)
    return units


def _query_prefers_numeric_evidence(query: str, query_terms: list[str]) -> bool:
    if re.search(r"\d", query):
        return True
    numeric_intent_terms = {
        "prazo", "prazos", "tempo", "dias", "meses", "anos", "idade",
        "idades", "dose", "doses", "dosagem", "dosagens", "quantos",
        "quantas", "quanto", "valores", "valor", "percentual", "percentuais",
    }
    return any(term in numeric_intent_terms for term in query_terms)


def _score_unit(
    unit: str,
    query_terms: list[str],
    *,
    prefer_numeric_evidence: bool,
) -> tuple[int, int, int, int, int]:
    lower = unit.lower()
    distinct_term_hits = sum(1 for term in query_terms if term in lower)
    repeated_term_hits = sum(lower.count(term) for term in query_terms)
    has_number = 1 if re.search(r"\d", unit) else 0
    numeric_alignment = has_number if prefer_numeric_evidence else -has_number
    starts_like_definition = 1 if re.match(r"^[A-ZÀ-Ý0-9].{0,120}$", unit.strip()) else 0
    length_score = min(len(unit), 220)
    return (
        distinct_term_hits,
        repeated_term_hits,
        numeric_alignment,
        starts_like_definition,
        length_score,
    )


def _offline_answer_from_chunks(query: str, chunks: list[dict]) -> tuple[str, list[str]]:
    """
    Deterministic extractive fallback for environments without OpenAI access.

    The answer is assembled from the highest scoring chunk units so the query
    pipeline remains operational and grounded during local/UI validation.
    """
    if not chunks:
        return "Não sei — nenhum contexto relevante encontrado.", []

    query_terms = _normalize_query_terms(query)
    prefer_numeric_evidence = _query_prefers_numeric_evidence(query, query_terms)
    candidates: list[tuple[tuple[int, int, int, int, int], float, int, str, str]] = []

    for chunk_index, chunk in enumerate(chunks[:5]):
        chunk_id = chunk.get("chunk_id", f"chunk_{chunk_index}")
        chunk_score = float(chunk.get("score", 0.0) or 0.0)
        for unit in _split_chunk_units(chunk.get("text", "")):
            if len(unit) < 24:
                continue
            candidates.append((
                _score_unit(
                    unit,
                    query_terms,
                    prefer_numeric_evidence=prefer_numeric_evidence,
                ),
                chunk_score,
                chunk_index,
                chunk_id,
                unit,
            ))

    if not candidates:
        top = chunks[0]
        text = (top.get("text") or "").strip()
        fallback = text[:320] + ("..." if len(text) > 320 else "")
        return fallback or "Não sei — nenhum contexto relevante encontrado.", [top.get("chunk_id", "chunk_0")]

    candidates.sort(
        key=lambda item: (
            item[0][0],
            item[0][1],
            item[1],
            item[0][2],
            item[0][3],
            -item[2],
        ),
        reverse=True,
    )

    selected_units: list[str] = []
    selected_chunk_ids: list[str] = []
    seen_units: set[str] = set()
    best_candidate = candidates[0]
    best_query_hits = best_candidate[0][0]
    best_chunk_score = best_candidate[1]
    best_chunk_id = best_candidate[3]

    for score, chunk_score, _, chunk_id, unit in candidates:
        normalized = unit.lower()
        if normalized in seen_units:
            continue
        if selected_units:
            # Keep the offline answer concise and avoid mixing unrelated chunks.
            if chunk_id != best_chunk_id:
                continue
            introduces_new_terms = any(
                term in normalized and term not in selected_units[0].lower()
                for term in query_terms
            )
            if not introduces_new_terms:
                continue
            if score[0] < max(best_query_hits - 1, 1):
                continue
            if chunk_score + 0.05 < best_chunk_score:
                continue
        seen_units.add(normalized)
        selected_units.append(unit)
        if chunk_id not in selected_chunk_ids:
            selected_chunk_ids.append(chunk_id)
        # One sentence is enough for most direct lookups; a second one is only
        # helpful when it comes from the same chunk and adds missing query terms.
        if len(selected_units) >= 2 or (selected_units and best_query_hits >= 2):
            break

    answer = " ".join(selected_units).strip()
    if answer and answer[-1] not in ".!?":
        answer += "."

    return answer or "Não sei — nenhum contexto relevante encontrado.", selected_chunk_ids


def generate_answer(
    query: str,
    chunks: list[dict],
    model: str = LLM_MODEL,
    system_prompt: str = SYSTEM_PROMPT
) -> tuple[str, list[str], float]:
    """
    Generate answer grounded in retrieved chunks.

    Returns:
        (answer_text, chunk_ids_used, latency_seconds)
    """
    if not chunks:
        return "Não sei — nenhum contexto relevante encontrado.", [], 0.0

    if not _has_usable_api_key():
        start = time.time()
        answer, chunk_ids = _offline_answer_from_chunks(query, chunks)
        latency = time.time() - start
        return answer, chunk_ids, latency

    # Build context from chunks
    context_parts = []
    chunk_ids = []

    for i, chunk in enumerate(chunks):
        chunk_id = chunk.get("chunk_id", f"chunk_{i}")
        text = chunk.get("text", "")
        source = chunk.get("source", "")
        score = chunk.get("score", 0.0)
        page = chunk.get("page_hint")

        context_parts.append(
            f"[Trecho {i+1}] (score: {score:.2f}, page: {page or '?'})\n{text}"
        )
        chunk_ids.append(chunk_id)

    context = "\n\n".join(context_parts)

    user_prompt = USER_PROMPT_TEMPLATE.format(
        context=context,
        query=query
    )

    start = time.time()

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.2,
        max_tokens=1000
    )

    latency = time.time() - start

    answer = response.choices[0].message.content or ""

    return answer, chunk_ids, latency


def estimate_answer_cost(query: str, chunks: list[dict], model: str = LLM_MODEL) -> float:
    """
    Estimate cost of generating an answer.
    GPT-4o-mini: ~$0.15 per 1M input tokens, $0.60 per 1M output tokens.
    """
    # Estimate tokens (rough: 1 token ≈ 4 chars)
    context_tokens = sum(len(c.get("text", "")) for c in chunks) // 4
    query_tokens = len(query) // 4
    # Output estimate
    estimated_output_tokens = 500  # average answer length

    input_cost = ((context_tokens + query_tokens) / 1_000_000) * 0.15
    output_cost = (estimated_output_tokens / 1_000_000) * 0.60

    return input_cost + output_cost
