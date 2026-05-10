# 0106 — Contratos de Aplicação

## Comandos (Commands)

### CMD-01: UploadDocument

**Input:**
```python
{
    "file": bytes,
    "workspace_id": str,
    "tags": list[str] | None
}
```

**Output:**
```python
{
    "document_id": UUID,
    "status": "parsed",
    "chunk_count": int,
    "pages": int | None
}
```

**Validações:**
- file extension in ["pdf", "docx", "md", "txt"]
- file size <= 50MB
- workspace_id exists and is active

**Erros:**
- 400: invalid_format
- 400: file_too_large
- 404: workspace_not_found

---

### CMD-02: Login

**Input:**
```python
{
    "email": str,
    "password": str
}
```

**Output:**
```python
{
    "session_id": str,
    "user": {
        "id": UUID,
        "email": str,
        "role": str,
        "workspace_id": UUID
    }
}
```

**Validações:**
- email format valid
- password non-empty
- user exists and is_active

**Erros:**
- 401: invalid_credentials
- 403: account_disabled

---

### CMD-03: Logout

**Input:**
```python
{
    "session_id": str
}
```

**Output:**
```python
{
    "success": true
}
```

**Erros:**
- 401: session_not_found

---

### CMD-04: CreateTenant

**Input:**
```python
{
    "name": str,
    "settings": dict | None
}
```

**Output:**
```python
{
    "tenant_id": UUID,
    "name": str,
    "created_at": datetime
}
```

**Validações:**
- name unique
- session has admin role

**Erros:**
- 401: unauthorized
- 409: name_conflict

---

### CMD-05: CreateUser

**Input:**
```python
{
    "email": str,
    "password": str,
    "role": str,  # admin, operator, viewer
    "tenant_id": UUID,
    "workspace_id": UUID  # optional, creates default
}
```

**Output:**
```python
{
    "user_id": UUID,
    "email": str,
    "role": str,
    "created_at": datetime
}
```

**Validações:**
- email unique
- role valid
- tenant exists
- session has admin role

**Erros:**
- 401: unauthorized
- 409: email_conflict

---

## Queries

### QRY-01: Search

**Input:**
```python
{
    "query": str,
    "workspace_id": str,
    "top_k": int | 5,
    "threshold": float | 0.25,
    "filters": {
        "document_id": UUID | None,
        "source_type": str | None,
        "tags": list[str] | None,
        "page_hint_min": int | None,
        "page_hint_max": int | None
    } | None
}
```

**Output:**
```python
{
    "query": str,
    "results": list[SearchResult],
    "total_candidates": int,
    "low_confidence": bool,
    "retrieval_time_ms": int,
    "method": "híbrida"
}
```

---

### QRY-02: Query (RAG)

**Input:**
```python
{
    "query": str,
    "workspace_id": str,
    "top_k": int | 5,
    "threshold": float | 0.25,
    "model": str | "gpt-4o-mini"
}
```

**Output:**
```python
{
    "answer": str,
    "chunks_used": list[str],
    "citations": list[Citation],
    "confidence": "high" | "medium" | "low",
    "grounded": bool,
    "low_confidence": bool,
    "retrieval": SearchOutput,
    "latency_ms": int
}
```

---

### QRY-03: GetMetrics

**Input:**
```python
{
    "workspace_id": str,
    "days": int | 7
}
```

**Output:**
```python
{
    "retrieval": {
        "hit_rate_top1": float,
        "hit_rate_top3": float,
        "hit_rate_top5": float,
        "avg_score": float,
        "low_confidence_rate": float
    },
    "answer": {
        "grounded_rate": float,
        "citation_coverage_avg": float,
        "avg_latency_ms": int
    },
    "evaluation": {
        "total_questions": int,
        "hit_rate": float
    }
}
```

---

### QRY-04: GetHealth

**Input:** None

**Output:**
```python
{
    "status": "healthy" | "degraded" | "unhealthy",
    "version": str,
    "qdrant": {
        "status": "ok" | "error",
        "points": int
    },
    "corpus": {
        "workspace_id": str,
        "documents": int,
        "chunks": int
    },
    "telemetry": {...},
    "timestamp": datetime
}
```

---

## Regras de Idempotência

- CMD-01 (Upload): idempotente se mesmo file hash para mesmo workspace
- CMD-02 (Login): não idempotente (cria sessão)
- CMD-03 (Logout): idempotente (session invalidada)
- CMD-04 (CreateTenant): não idempotente (name unique)
- CMD-05 (CreateUser): não idempotente (email unique)

---

## Próximo Passo

Avançar para 0107_contratos_de_api.md
