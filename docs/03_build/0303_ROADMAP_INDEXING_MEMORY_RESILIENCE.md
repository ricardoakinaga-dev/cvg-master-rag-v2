# Roadmap - Indexacao PDF Resiliente A Memoria

## Objetivo

Executar a remediacao da indexacao PDF em fases controladas para impedir novos travamentos da VPS e restaurar consistencia entre disco, registry e Qdrant.

## Ordem De Execucao

| Fase | Sprint | Nome | Dependencia | Saida |
|---|---|---|---|---|
| 0 | 0.1 | Contencao e Reconciliacao | auditoria concluida | estado parcial limpo e limites temporarios definidos |
| 1 | 1.1 | Extrator PDF Memory-Safe | Fase 0 | extracao por pagina/lote com cache liberado |
| 2 | 2.1 | Worker De Ingestao Isolado | Fase 1 | upload cria job e API nao bloqueia |
| 3 | 3.1 | Unificacao Dos Caminhos PDF | Fase 2 | PDF operacional/canonico/reindex usa pipeline seguro |
| 4 | 4.1 | Reindexacao Batch-Safe | Fase 3 | scripts/admin processam em lotes |
| 5 | 5.1 | Transacao, Cleanup E Reconciliacao | Fase 4 | falha nao deixa artefatos parciais |
| 6 | 6.1 | Observabilidade E Validacao Real | Fase 5 | evidencia com livro real e health consistente |

## Gates

### Gate 0 - Antes De Nova Tentativa Grande

Obrigatorio:
- pontos orfaos identificados e removidos ou isolados
- arquivo de chunks corrompido removido ou arquivado
- limite temporario documentado
- runtime_state atualizado

### Gate 1 - Antes De Expor Upload Grande Ao Usuario

Obrigatorio:
- extrator libera cache por pagina/lote
- memoria medida em teste controlado
- API continua saudavel durante processamento

### Gate 2 - Antes De Reindex Amplo

Obrigatorio:
- parser antigo nao e usado para PDF grande
- reindex usa lotes
- rollback/cleanup implementado

### Gate 3 - Fechamento

Obrigatorio:
- livro real indexado sem OOM
- falha simulada sem corrupcao de JSON
- Qdrant sem pontos orfaos
- `/health` sem divergencia relevante

## Regra Para O Agente Executor

Antes de iniciar cada task:
- ler `docs/99_runtime_state.md`
- ler o arquivo do sprint correspondente
- confirmar dependencias da task

Depois de concluir cada task:
- marcar `Executado: [x]` na task
- registrar evidencia da execucao na propria task
- atualizar `docs/99_runtime_state.md`
- atualizar `docs/20_master_execution_log.md`
- atualizar backlog aplicavel
- somente entao iniciar a proxima task
