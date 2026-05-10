# Remediation Plan - Indexing 400MB

## Remediacoes Obrigatorias Antes Do Release

Nenhuma pendente.

## Controles Permanentes

- Manter `MAX_CONCURRENT_LARGE_INGESTION_JOBS=1`.
- Manter `INGESTION_JOB_TIMEOUT_SECONDS=21600`.
- Manter `INGESTION_WORKER_MEMORY_LIMIT_MB=2560`.
- Usar health leve no frontend.
- Monitorar `operational_alerts` em jobs.

## Futuro Obrigatorio Antes De Aumentar Limite

- Se `chunk_count > 100000`, criar SPEC/BUILD para shards JSONL.
- Se chunks previstos > `524288000` bytes, criar SPEC/BUILD para shards JSONL.

## Status

Release 400MB/500MiB aprovado sem remediacao adicional.
