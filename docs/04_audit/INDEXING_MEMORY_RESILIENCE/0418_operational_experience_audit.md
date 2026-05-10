# Operational Experience Audit - Indexing Memory Resilience

## Resultado

Status: ADERENTE PARA CANARIO

## Operabilidade

O operador agora consegue acompanhar:

- status geral por `/health`
- progresso agregado por `/metrics`
- progresso detalhado por lote em `src/logs/ingestion_batches.jsonl`
- pico de memoria por lote
- paginas, chunks, embeddings e pontos indexados
- falhas com `ingestion_id`

## Runbook Minimo Para Canario

1. Elevar `MAX_UPLOAD_BYTES` apenas para o tamanho alvo do canario.
2. Reiniciar backend.
3. Enviar um livro grande.
4. Monitorar `/health`, `/metrics` e `src/logs/ingestion_batches.jsonl`.
5. Confirmar job `committed`.
6. Confirmar ausencia de pontos orfaos e JSON valido.
7. Se houver erro, rebaixar `MAX_UPLOAD_BYTES` para `26214400` e acionar cleanup.

## Conclusao

A experiencia operacional saiu de caixa preta para fluxo observavel e reversivel.
