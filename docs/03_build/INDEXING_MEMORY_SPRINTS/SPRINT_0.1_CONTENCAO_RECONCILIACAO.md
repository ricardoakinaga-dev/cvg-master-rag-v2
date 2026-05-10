# Sprint 0.1 - Contencao E Reconciliacao

## Objetivo

Impedir nova tentativa pesada antes da limpeza do estado parcial e definir limites conservadores iniciais.

## Tasks

### IMR-001 - Bloquear nova indexacao grande ate reconciliacao

- Executado: [x]
- O QUE: impedir operacionalmente novas cargas de livros grandes ate finalizar limpeza e limites.
- ONDE: runtime/configuracao operacional, documentacao de operacao e fluxo de upload.
- COMO: definir bloqueio temporario ou limite de tamanho/paginas para PDF grande; documentar mensagem esperada ao usuario.
- DEPENDENCIA: auditoria `INDEXING_MEMORY_AUDIT`.
- CRITERIO DE PRONTO: nova tentativa de livro grande nao e aceita sem autorizacao de ciclo.
- EVIDENCIA: `MAX_UPLOAD_BYTES=26214400` aplicado em `src/.env`; backend reiniciado; `curl http://127.0.0.1:8000/health` retornou `healthy`; import com `.env` confirmou `MAX_UPLOAD_BYTES=26214400`. O PDF pendente de 37MB passa a ser bloqueado pelo limite existente de upload.
- REGRA POS-TASK: marcar `Executado: [x]`, registrar evidencia, atualizar `docs/99_runtime_state.md`, `docs/20_master_execution_log.md` e este sprint antes da proxima task.

### IMR-002 - Limpar artefatos parciais e pontos orfaos

- Executado: [x]
- O QUE: reconciliar disco, registry e Qdrant apos OOM.
- ONDE: `src/data/documents/default`, Qdrant collection ativa e documentos de auditoria.
- COMO: identificar documento parcial `d057d3c6-13e1-4fd9-bdf9-9b1c26ea7d38`, decidir arquivar/remover chunks invalidos e remover pontos Qdrant por `document_id`.
- DEPENDENCIA: IMR-001.
- CRITERIO DE PRONTO: `/health` nao deve reportar divergencia causada pelos pontos orfaos conhecidos.
- EVIDENCIA: artefatos parciais movidos para `.runtime/indexing_memory_quarantine/2026-04-30_imr-002/` (`d057..._chunks.json` corrompido e PDF de 37MB); pontos Qdrant do `document_id=d057d3c6-13e1-4fd9-bdf9-9b1c26ea7d38` removidos de `2312` para `0`; `/health` passou de `workspace_points=2524` para `workspace_points=212`.
- REGRA POS-TASK: marcar `Executado: [x]`, registrar evidencia, atualizar `docs/99_runtime_state.md`, `docs/20_master_execution_log.md` e este sprint antes da proxima task.

### IMR-003 - Definir limites temporarios conservadores

- Executado: [x]
- O QUE: reduzir risco ate o pipeline definitivo estar pronto.
- ONDE: variaveis operacionais e runbook.
- COMO: definir valores iniciais para `PDF_INGESTION_PAGE_BATCH_SIZE`, `INGESTION_INDEX_BATCH_SIZE`, `QDRANT_UPSERT_BATCH_SIZE` e limite de memoria do processo/worker.
- DEPENDENCIA: IMR-002.
- CRITERIO DE PRONTO: limites documentados, aplicados e verificaveis no runtime.
- EVIDENCIA: `src/.env` e `src/.env.example` atualizados com `PDF_INGESTION_PAGE_BATCH_SIZE=1`, `INGESTION_INDEX_BATCH_SIZE=8`, `QDRANT_UPSERT_BATCH_SIZE=32`, `INGESTION_WORKER_MEMORY_LIMIT_MB=3072`, `INGESTION_ABORT_ON_MEMORY_LIMIT=true`; `systemctl set-property cvg-master-rag-backend.service MemoryMax=3G`; backend reiniciado; import com `.env` confirmou os tres limites usados pelo codigo; `systemctl show` confirmou `MemoryMax=3221225472`; `/health` retornou `healthy`.
- REGRA POS-TASK: marcar `Executado: [x]`, registrar evidencia, atualizar `docs/99_runtime_state.md`, `docs/20_master_execution_log.md` e este sprint antes da proxima task.

## Gate Do Sprint

- todos os artefatos parciais conhecidos tratados: [x]
- limite temporario ativo: [x]
- documentacao atualizada: [x]

## Verificacao Final

- `/health`: `healthy`, `workspace_points=212`
- Qdrant: `d057d3c6-13e1-4fd9-bdf9-9b1c26ea7d38` com `0` pontos
- runtime config: `MAX_UPLOAD_BYTES=26214400`, `PDF_INGESTION_PAGE_BATCH_SIZE=1`, `INGESTION_INDEX_BATCH_SIZE=8`, `QDRANT_UPSERT_BATCH_SIZE=32`
- systemd: `MemoryMax=3221225472`, `ActiveState=active`
- status: Sprint 0.1 concluida
