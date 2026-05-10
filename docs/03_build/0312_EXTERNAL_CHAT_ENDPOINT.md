# 0312 External Chat Endpoint

## Objetivo

Disponibilizar consulta server-to-server para outro programa em outra VPS consumir a mesma resposta do chat clinico validado.

## Endpoint

`POST /external/chat`

Em producao publica via Caddy:

`POST https://www.master.rag.centroveterinarioguarapiranga.com/api/external/chat`

## Autenticacao

Enviar header obrigatorio:

`X-API-Key: <token-da-integracao>`

O backend compara esse valor com a variavel de ambiente:

`EXTERNAL_CHAT_API_KEY`

Se a chave nao estiver configurada, o endpoint retorna `503 external_chat_not_configured`.
Se a chave estiver ausente ou errada, retorna `401 invalid_api_key`.

## Request

```json
{
  "question": "me de um protocolo de corpo estranho linear em gatos",
  "workspace_id": "default",
  "top_k": 8,
  "threshold": 0.25
}
```

Campos:

- `question`: pergunta em portugues do Brasil.
- `workspace_id`: workspace consultado. Padrao: `default`.
- `top_k`: quantidade solicitada de resultados base. Padrao: `8`, minimo `1`, maximo `20`.
- `threshold`: corte de score. Padrao: `0.25`, minimo `0`, maximo `1`.

## Comportamento

- Sempre usa `retrieval_profile=clinical_v2`.
- Sempre usa o pipeline do chat validado.
- Nao expoe debug interno de retrieval.
- Resposta final vem em portugues do Brasil.
- A busca clinica segue o fluxo pt-BR -> ingles -> RAG -> resposta pt-BR.

## Response

```json
{
  "answer": "direct_answer\n...",
  "confidence": "high",
  "grounded": true,
  "low_confidence": false,
  "citation_coverage": 1.0,
  "citations": [],
  "bibliography": [],
  "chunks_used": [],
  "retrieval_profile": "clinical_v2",
  "latency_ms": 1234,
  "completeness_status": "sufficient",
  "missing_sections": []
}
```

## Exemplo curl

```bash
curl -X POST "https://www.master.rag.centroveterinarioguarapiranga.com/api/external/chat" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <token-da-integracao>" \
  -d '{
    "question": "me de um protocolo de corpo estranho linear em gatos",
    "top_k": 8,
    "threshold": 0.25
  }'
```
