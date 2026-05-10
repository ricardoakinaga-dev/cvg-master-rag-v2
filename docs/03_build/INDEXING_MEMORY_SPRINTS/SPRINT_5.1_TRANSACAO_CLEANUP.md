# Sprint 5.1 - Transacao, Cleanup E Reconciliacao

## Objetivo

Garantir que falha, abort ou OOM nao deixem disco e Qdrant inconsistentes.

## Tasks

### IMR-012 - Implementar arquivos temporarios e commit atomico

- Executado: [x]
- O QUE: escrever raw/chunks em temporarios e promover apenas ao final.
- ONDE: persistencia de documentos e chunks.
- COMO: usar staging file, validar JSON e renomear para nome final somente no commit.
- DEPENDENCIA: Sprint 4.1 concluido.
- CRITERIO DE PRONTO: falha no meio nao produz `*_chunks.json` final invalido.
- EVIDENCIA: `src/services/ingestion_service.py` passou a escrever chunks/raw em `*.tmp`, validar JSON e promover por `Path.replace()` apenas no commit; teste `test_controlled_pdf_does_not_expose_final_chunks_before_commit` confirma que `*_chunks.json` final nao aparece durante processamento e que o JSON final e valido.
- REGRA POS-TASK: marcar `Executado: [x]`, registrar evidencia, atualizar `docs/99_runtime_state.md`, `docs/20_master_execution_log.md` e este sprint antes da proxima task.

### IMR-013 - Implementar cleanup por ingestion_id

- Executado: [x]
- O QUE: remover pontos Qdrant e temporarios de uma ingestao falha.
- ONDE: Qdrant payload, cleanup/reconciler e job store.
- COMO: indexar pontos com `ingestion_id`; cleanup remove por `ingestion_id` ou `document_id` antes de marcar falha final.
- DEPENDENCIA: IMR-012.
- CRITERIO DE PRONTO: falha simulada nao deixa pontos orfaos.
- EVIDENCIA: `src/services/vector_service.py` passou a gravar `ingestion_id` no payload dos pontos e adicionou `delete_ingestion_points()`; `src/services/ingestion_job_service.py` passa `ingestion_id` ao worker quando suportado e executa `cleanup_ingestion_artifacts()` em falha/abort, removendo pontos, temporarios e upload. Testes `test_failed_ingestion_job_cleans_temporary_files_and_ingestion_points` e `test_indexed_points_carry_ingestion_id` passaram.
- REGRA POS-TASK: marcar `Executado: [x]`, registrar evidencia, atualizar `docs/99_runtime_state.md`, `docs/20_master_execution_log.md` e este sprint antes da proxima task.

## Gate Do Sprint

- [x] commit atomico implementado
- [x] cleanup comprovado por falha simulada
