# Remediation Plan - Indexing Memory Resilience Audit

## Decisao Tecnica

Status: APROVADO PARA LIBERACAO CONTROLADA, AGUARDANDO DECISAO HUMANA

## Plano De Liberacao Controlada

### Passo 1 - Aprovar Canario

- Decisao humana requerida: sim.
- Alteracao proposta: elevar `MAX_UPLOAD_BYTES` de `26214400` para um limite canario suficiente para o livro validado.
- Valor sugerido inicial: `52428800` (`50 MB`).

### Passo 2 - Manter Limites Conservadores

Manter:

- `INGESTION_ASYNC_PDF_ENABLED=true`
- `INGESTION_ASYNC_PDF_MIN_BYTES=5242880`
- `PDF_INGESTION_PAGE_BATCH_SIZE=1`
- `INGESTION_INDEX_BATCH_SIZE=8`
- `QDRANT_UPSERT_BATCH_SIZE=32`
- `INGESTION_WORKER_MEMORY_LIMIT_MB=3072`

### Passo 3 - Executar Upload Real Pelo Endpoint

Executar o mesmo livro grande pelo fluxo de usuario/API, com monitoramento ativo.

### Passo 4 - Criterios De Rollback

Rebaixar `MAX_UPLOAD_BYTES` para `26214400` se ocorrer qualquer item:

- backend deixa de responder `/health`
- `ingestion_batches.errors > 0`
- RSS do worker ultrapassa patamar operacional definido para canario
- job termina `failed` ou `aborted`
- Qdrant fica com pontos orfaos apos cleanup
- JSON final invalido

### Passo 5 - Criterios De Promocao

Manter limite canario se:

- upload via endpoint retorna job corretamente
- worker conclui `committed`
- `/health` permanece `healthy`
- `/metrics` mostra lotes completos sem erro
- Qdrant e disco ficam consistentes
