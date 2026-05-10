# Backlog - Indexacao PDF Resiliente A Memoria

## Status

- backlog_status: COMPLETED_READY_FOR_AUDIT
- origem: `INDEXING_MEMORY_AUDIT`
- SPEC: `docs/02_spec/0121_indexing_memory_resilience_spec.md`
- roadmap: `docs/03_build/0303_ROADMAP_INDEXING_MEMORY_RESILIENCE.md`

## Convencao De Task

Cada task deve manter:
- `Executado: [ ]` enquanto pendente
- `Executado: [x]` apos conclusao
- evidencia objetiva
- arquivos alterados
- comandos de verificacao
- atualizacao obrigatoria de `docs/99_runtime_state.md` e `docs/20_master_execution_log.md`

## Backlog Priorizado

| ID | Fase | Sprint | Titulo | Prioridade | Status |
|---|---|---|---|---|---|
| IMR-001 | 0 | 0.1 | Bloquear nova indexacao grande ate reconciliacao | P0 | DONE |
| IMR-002 | 0 | 0.1 | Limpar artefatos parciais e pontos orfaos | P0 | DONE |
| IMR-003 | 0 | 0.1 | Definir limites temporarios conservadores | P0 | DONE |
| IMR-004 | 1 | 1.1 | Criar extracao PDF por pagina/lote com liberacao de cache | P0 | DONE |
| IMR-005 | 1 | 1.1 | Medir memoria por pagina/lote | P0 | DONE |
| IMR-006 | 2 | 2.1 | Transformar upload pesado em job | P0 | DONE |
| IMR-007 | 2 | 2.1 | Criar worker isolado com limite de memoria | P0 | DONE |
| IMR-008 | 3 | 3.1 | Remover caminho PDF inseguro do parser antigo | P1 | DONE |
| IMR-009 | 3 | 3.1 | Unificar PDF operacional, canonico e reindex | P1 | DONE |
| IMR-010 | 4 | 4.1 | Tornar reindex_corpus batch-safe | P1 | DONE |
| IMR-011 | 4 | 4.1 | Tornar reindex_document batch-safe | P1 | DONE |
| IMR-012 | 5 | 5.1 | Implementar arquivos temporarios e commit atomico | P0 | DONE |
| IMR-013 | 5 | 5.1 | Implementar cleanup por ingestion_id | P0 | DONE |
| IMR-014 | 6 | 6.1 | Expor logs/metricas por lote | P1 | DONE |
| IMR-015 | 6 | 6.1 | Validar com livro real e falha simulada | P0 | DONE |

## Sprint Files

- `docs/03_build/INDEXING_MEMORY_SPRINTS/SPRINT_0.1_CONTENCAO_RECONCILIACAO.md`
- `docs/03_build/INDEXING_MEMORY_SPRINTS/SPRINT_1.1_PDF_MEMORY_SAFE.md`
- `docs/03_build/INDEXING_MEMORY_SPRINTS/SPRINT_2.1_WORKER_ISOLADO.md`
- `docs/03_build/INDEXING_MEMORY_SPRINTS/SPRINT_3.1_UNIFICACAO_PDF.md`
- `docs/03_build/INDEXING_MEMORY_SPRINTS/SPRINT_4.1_REINDEX_BATCH_SAFE.md`
- `docs/03_build/INDEXING_MEMORY_SPRINTS/SPRINT_5.1_TRANSACAO_CLEANUP.md`
- `docs/03_build/INDEXING_MEMORY_SPRINTS/SPRINT_6.1_OBSERVABILIDADE_VALIDACAO.md`
