# GAP Analysis - Indexing 400MB

## Gaps Criticos

Nenhum.

## Gaps Importantes

Nenhum para release 400MB/500MiB.

## Melhorias Futuras

- Implementar shards JSONL antes de qualquer aumento acima de `500MiB`.
- Considerar dashboard historico de throughput por job.
- Considerar limpeza agendada de logs antigos de worker.

## Decisao

Sem gap bloqueante para liberacao permanente controlada de `MAX_UPLOAD_BYTES=524288000`.
