# 0107 — Contratos de API

## Endpoints REST

### Grupo: Auth

#### POST /auth/login
**Request:**
```json
{
    "email": "user@example.com",
    "password": "string"
}
```
**Response 200:**
```json
{
    "session_id": "abc123...",
    "user": {
        "id": "uuid",
        "email": "user@example.com",
        "role": "admin|operator|viewer",
        "workspace_id": "uuid"
    }
}
```
**Errors:** 401, 403

---

#### POST /auth/logout
**Headers:** X-Session-ID
**Response 200:**
```json
{
    "success": true
}
```

---

#### POST /auth/recovery
**Request:**
```json
{
    "email": "user@example.com"
}
```
**Response 200:**
```json
{
    "message": "Email de recuperação enviado"
}
```

---

#### GET /auth/me
**Headers:** X-Session-ID
**Response 200:**
```json
{
    "user_id": "uuid",
    "email": "user@example.com",
    "role": "admin|operator|viewer",
    "workspace_id": "uuid",
    "tenant_id": "uuid"
}
```

---

### Grupo: Documents

#### POST /documents/upload
**Headers:** X-Session-ID
**Request:** multipart/form-data
- file: bytes
- workspace_id: string
**Response 201:**
```json
{
    "document_id": "uuid",
    "status": "parsed",
    "chunk_count": 12,
    "pages": 5
}
```

---

#### GET /documents/{document_id}
**Headers:** X-Session-ID
**Query:** workspace_id (required)
**Response 200:**
```json
{
    "document_id": "uuid",
    "workspace_id": "uuid",
    "source_type": "pdf",
    "filename": "relatorio.pdf",
    "page_count": 47,
    "char_count": 89400,
    "chunk_count": 89,
    "status": "parsed",
    "created_at": "ISO8601",
    "tags": ["fiscal", "2024"],
    "embeddings_model": "text-embedding-3-small",
    "chunking_strategy": "recursive",
    "indexed_at": "ISO8601"
}
```

---

### Grupo: Search

#### POST /search
**Headers:** X-Session-ID
**Request:**
```json
{
    "query": "Qual o prazo para reembolso?",
    "workspace_id": "workspace_001",
    "top_k": 5,
    "threshold": 0.25,
    "filters": {
        "document_id": "uuid",
        "source_type": "pdf",
        "tags": ["tag1"],
        "page_hint_min": 1,
        "page_hint_max": 50
    },
    "include_raw_scores": false
}
```
**Response 200:**
```json
{
    "query": "Qual o prazo para reembolso?",
    "results": [...],
    "total_candidates": 20,
    "low_confidence": false,
    "retrieval_time_ms": 145,
    "method": "híbrida"
}
```

---

### Grupo: Query (RAG)

#### POST /query
**Headers:** X-Session-ID
**Request:**
```json
{
    "query": "Qual o prazo para reembolso?",
    "workspace_id": "workspace_001",
    "top_k": 5,
    "threshold": 0.25,
    "model": "gpt-4o-mini"
}
```
**Response 200:**
```json
{
    "answer": "O prazo é de 30 dias corridos...",
    "chunks_used": ["chunk_uuid_1", "chunk_uuid_2"],
    "citations": [...],
    "confidence": "high",
    "grounded": true,
    "low_confidence": false,
    "retrieval": {...},
    "latency_ms": 1890
}
```

---

### Grupo: Admin

#### GET /tenants
**Headers:** X-Session-ID
**Response 200:**
```json
{
    "tenants": [
        {
            "id": "uuid",
            "name": "Empresa A",
            "is_active": true,
            "created_at": "ISO8601"
        }
    ]
}
```

---

#### POST /tenants
**Headers:** X-Session-ID (admin only)
**Request:**
```json
{
    "name": "Empresa B",
    "settings": {}
}
```
**Response 201:**
```json
{
    "id": "uuid",
    "name": "Empresa B",
    "created_at": "ISO8601"
}
```

---

#### GET /users
**Headers:** X-Session-ID
**Response 200:**
```json
{
    "users": [
        {
            "id": "uuid",
            "email": "user@example.com",
            "role": "admin",
            "is_active": true
        }
    ]
}
```

---

#### POST /users
**Headers:** X-Session-ID (admin only)
**Request:**
```json
{
    "email": "newuser@example.com",
    "password": "string",
    "role": "operator",
    "tenant_id": "uuid"
}
```
**Response 201:**
```json
{
    "id": "uuid",
    "email": "newuser@example.com",
    "role": "operator",
    "created_at": "ISO8601"
}
```

---

### Grupo: Telemetry

#### GET /health
**Response 200:**
```json
{
    "status": "healthy",
    "version": "0.1.0",
    "qdrant": {"status": "ok", "points": 21},
    "corpus": {
        "workspace_id": "default",
        "documents": 3,
        "chunks": 21
    },
    "telemetry": {...},
    "timestamp": "ISO8601"
}
```

---

#### GET /metrics
**Query:** workspace_id, days
**Response 200:**
```json
{
    "retrieval": {...},
    "answer": {...},
    "evaluation": {...}
}
```

---

## Error Codes

| Code | HTTP | Description |
|---|---|---|
| invalid_format | 400 | File type not supported |
| file_too_large | 400 | File exceeds 50MB |
| invalid_query | 400 | Query empty or too long |
| workspace_not_found | 404 | Workspace ID does not exist |
| document_not_found | 404 | Document ID does not exist |
| invalid_credentials | 401 | Email or password wrong |
| account_disabled | 403 | User account inactive |
| unauthorized | 403 | Role not allowed |
| session_not_found | 401 | Session invalid or expired |
| name_conflict | 409 | Tenant/User already exists |
| parse_failed | 413 | Could not extract text |
| retrieval_error | 500 | Qdrant error |
| llm_error | 500 | OpenAI API error |

---

## Próximo Passo

Avançar para 0108_contratos_de_eventos_e_assincronismo.md
