# 0415 - INTEGRATIONS AUDIT

## Resultado

Classificacao geral: aderente.

## Integracoes

| Integracao | Evidencia | Status |
|---|---|---|
| Qdrant | Container live `qdrant/qdrant:v1.11.5`; suite `260 passed` | Aderente |
| Embeddings | `EMBEDDING_MODEL` corrigido; fallback offline deterministico nos testes | Aderente |
| FastAPI/Next.js | Playwright smoke com backend em `127.0.0.1:8010` e frontend de teste | Aderente |
| Docker security scan | Gitleaks container executado com sucesso | Aderente |
| CI security surface | Scanner interno e Gitleaks documentados no fechamento | Aderente |

## Qdrant Reindex

Resultado do reindex:

- documentos canonicos: 5
- pontos indexados: 11
- verificacao: `PASS - workspace Qdrant matches disk`

## Findings

Sem gap bloqueante de integracao.
