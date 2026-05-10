# Audit Plan - Indexing 400MB Controlled Release

## Plano

1. Validar aderencia a SPEC 0122.
2. Validar runtime e configuracao efetiva.
3. Validar dados finais do canario `410562000` bytes.
4. Validar Qdrant por `document_id` e `ingestion_id`.
5. Validar health leve/completo e DNS publico.
6. Validar logs de kernel contra OOM.
7. Validar testes automatizados focados.
8. Registrar gaps e decisao operacional.

## Evidencias Base

- `MAX_UPLOAD_BYTES=524288000`
- `INGESTION_JOB_TIMEOUT_SECONDS=21600`
- `MAX_CONCURRENT_LARGE_INGESTION_JOBS=1`
- `INGESTION_WORKER_MEMORY_LIMIT_MB=2560`
- `CHUNKS_JSONL_SHARD_TRIGGER_CHUNK_COUNT=100000`
- `CHUNKS_JSONL_SHARD_TRIGGER_FILE_BYTES=524288000`

## Criterio De Aprovacao

Liberar permanentemente somente se nao houver gap critico, OOM, inconsistencia Qdrant/JSON ou falha de runtime publica.
