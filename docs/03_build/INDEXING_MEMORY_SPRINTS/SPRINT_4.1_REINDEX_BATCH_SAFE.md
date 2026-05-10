# Sprint 4.1 - Reindexacao Batch-Safe

## Objetivo

Garantir que scripts e rotas admin de reindexacao nao recriem o mesmo problema de memoria.

## Tasks

### IMR-010 - Tornar reindex_corpus batch-safe

- Executado: [x]
- O QUE: reindexar corpus sem carregar todos os chunks/texts/embeddings de documento grande.
- ONDE: script de reindexacao de corpus.
- COMO: processar por documento e por lote, persistindo e indexando incrementalmente.
- DEPENDENCIA: Sprint 3.1 concluido.
- CRITERIO DE PRONTO: reindex nao cria lista completa `texts` para documento grande.
- EVIDENCIA: `src/scripts/reindex_corpus.py` passou a usar `REINDEX_INDEX_BATCH_SIZE`, `_embed_and_index_chunk_batches()` e `_embed_and_index_persisted_chunk_file()`; o script nao cria mais `texts = [c.text for c in chunks]` para documento inteiro e processa embeddings/indexacao por lote. Teste `test_reindex_corpus_indexes_document_chunks_in_batches` confirma batches `[2, 2, 1]`.
- REGRA POS-TASK: marcar `Executado: [x]`, registrar evidencia, atualizar `docs/99_runtime_state.md`, `docs/20_master_execution_log.md` e este sprint antes da proxima task.

### IMR-011 - Tornar reindex_document batch-safe

- Executado: [x]
- O QUE: reindexar documento individual sem carregar chunks existentes inteiros quando grande.
- ONDE: servico de ingestao/reindexacao.
- COMO: ler chunks por stream/lote quando houver arquivo persistido e regenerar embeddings em batches pequenos.
- DEPENDENCIA: IMR-010.
- CRITERIO DE PRONTO: reindex individual respeita limites de memoria e falha limpo.
- EVIDENCIA: `src/services/ingestion_service.py` ganhou `_reindex_persisted_chunks_file()` para ler `*_chunks.json` com `iter_json_array_batches()`, restaurar embeddings por lote, escrever arquivo temporario e indexar em batches de `INGESTION_INDEX_BATCH_SIZE`; `reindex_document()` usa esse caminho para PDFs/chunks persistidos. Teste `test_reindex_document_streams_persisted_chunks_in_batches` confirma batches `[2, 2, 1]`.
- REGRA POS-TASK: marcar `Executado: [x]`, registrar evidencia, atualizar `docs/99_runtime_state.md`, `docs/20_master_execution_log.md` e este sprint antes da proxima task.

## Gate Do Sprint

- [x] reindex amplo e individual sao batch-safe
- [x] rotas/scripts admin nao podem travar VPS com corpus grande
