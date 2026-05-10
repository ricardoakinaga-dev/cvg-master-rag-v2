# Audit Report - Indexing 400MB Controlled Release

## Decisao

`APPROVED_FOR_PERMANENT_CONTROLLED_RELEASE`

## Limite Aprovado

- `MAX_UPLOAD_BYTES=524288000`
- Escopo: PDFs ate o limite de `500MiB`, com alvo operacional validado em `410562000` bytes.

## Evidencia Principal

- Canario final `410562000` bytes concluiu `committed`.
- `3109` paginas processadas.
- `18679` chunks gerados.
- `18679` pontos Qdrant por `document_id`.
- `18679` pontos Qdrant por `ingestion_id`.
- `rss_peak_mb=418.52`.
- Nenhum OOM/memory cgroup no kernel.
- `/health` completo `healthy`.
- `/health?light=true` `healthy`, `mode=light`.
- `/documents` publico `HTTP/2 200`.
- API publica `/api/health?light=true` `healthy`.
- Testes focados: `13 passed`.

## Gaps

- Criticos: nenhum.
- Importantes: nenhum.
- Melhorias: shards JSONL antes de aumentar limite acima de `500MiB`.

## Condicoes De Operacao

- Concorrencia de jobs grandes deve permanecer `1`.
- Worker deve permanecer isolado por `systemd_run` ou fallback registrado.
- Health leve deve continuar sendo usado pelo frontend.
- Aumento futuro de limite exige novo ciclo CVG.

## Conclusao

O ciclo tecnico e operacional de indexacao 400MB esta aprovado para liberacao permanente controlada com limite `500MiB`.
