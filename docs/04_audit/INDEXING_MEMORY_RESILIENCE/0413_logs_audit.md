# Logs Audit - Indexing Memory Resilience

## Resultado

Status: ADERENTE

## Evidencias

| Fonte | Resultado |
|---|---|
| `src/logs/ingestion_batches.jsonl` | `421` eventos para `imr-real-book-2026-05-01` |
| ultimo lote | paginas `841-842`, `chunks_created=8`, `points_indexed=8` |
| RSS no ultimo lote | `rss_mb=157.4`, `rss_peak_mb=157.6` |
| status do ultimo lote | `success` |

## Campos Auditaveis

Os eventos possuem `ingestion_id`, `document_id`, `workspace_id`, `filename`, `batch_index`, intervalo de paginas, caracteres, chunks, embeddings, pontos, RSS atual/pico, duracao, status e erro.

## Conclusao

Os logs permitem diagnosticar progresso, memoria e falhas por lote sem entrar no codigo.
