# Sprint 3.1 - Unificacao Dos Caminhos PDF

## Objetivo

Eliminar caminhos inseguros que ainda carregam PDF inteiro em memoria.

## Tasks

### IMR-008 - Remover caminho PDF inseguro do parser antigo

- Executado: [x]
- O QUE: impedir que `_parse_pdf()` seja usado para livros grandes carregando todas as paginas.
- ONDE: parser documental e chamadas de ingestao PDF.
- COMO: redirecionar PDF para pipeline controlado ou limitar parser antigo a casos pequenos explicitamente seguros.
- DEPENDENCIA: Sprint 2.1 concluido.
- CRITERIO DE PRONTO: nenhum PDF grande passa pelo parser all-in-memory.
- EVIDENCIA: `src/services/document_parser.py` passou a bloquear PDF no `parse_document()` com orientacao para pipeline controlado; teste `test_pdf_parser_path_is_blocked_for_memory_safety` confirma que o parser legado all-in-memory nao e usado para PDF.
- REGRA POS-TASK: marcar `Executado: [x]`, registrar evidencia, atualizar `docs/99_runtime_state.md`, `docs/20_master_execution_log.md` e este sprint antes da proxima task.

### IMR-009 - Unificar PDF operacional, canonico e reindex

- Executado: [x]
- O QUE: garantir uma unica politica segura para qualquer PDF.
- ONDE: ingestao operacional, corpus canonico e reindex.
- COMO: usar o mesmo extrator/lote/commit para upload e reprocessamento.
- DEPENDENCIA: IMR-008.
- CRITERIO DE PRONTO: todos os caminhos PDF relevantes usam pipeline memory-safe.
- EVIDENCIA: `src/services/ingestion_service.py` passou a usar `_ingest_pdf_controlled()` para qualquer PDF, com `catalog_scope` canonico/operacional calculado pelo caminho; metadata registra `ingestion_mode=controlled_pdf`, `raw_text_persisted=false` e `source_path`; `reindex_document()` e `src/scripts/reindex_corpus.py` reutilizam chunks persistidos para PDF em vez de rechunkar raw pages. Verificacao: `py_compile` passou; `pytest` focado passou `32 passed, 207 deselected`; backend reiniciado e `/health` permaneceu `healthy`.
- REGRA POS-TASK: marcar `Executado: [x]`, registrar evidencia, atualizar `docs/99_runtime_state.md`, `docs/20_master_execution_log.md` e este sprint antes da proxima task.

## Gate Do Sprint

- [x] nao existe caminho PDF grande all-in-memory
- [x] comportamento e documentado para PDF pequeno e grande
