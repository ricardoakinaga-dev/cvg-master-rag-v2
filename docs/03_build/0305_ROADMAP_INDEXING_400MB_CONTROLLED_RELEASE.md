# Roadmap - Indexacao 400MB Com Margem Segura

## Objetivo

Liberar indexacao sob demanda de PDFs ate `400MB/400MiB`, com limite seguro de `500MiB`, mantendo API saudavel e controlando CPU/RAM/IO do worker.

## Ordem De Execucao

| Fase | Sprint | Nome | Dependencia | Saida |
|---|---|---|---|---|
| 7 | 7.1 | Gate Operacional 400MB | SPEC 0122 | limite seguro, preflight, concorrencia e timeout |
| 7 | 7.2 | Worker Com Cgroup | 7.1 | CPU/RAM/IO controlados por perfil |
| 7 | 7.3 | Canary 400MB | 7.2 | validacao progressiva 100MB/250MB/391,5MiB |
| 7 | 7.4 | Hardening Operacional | 7.3 | heartbeat, alertas e criterio de shards |

## Gates

### Gate 7.1 - Antes De Aumentar Limite

- `MAX_UPLOAD_BYTES` definido como `524288000` apenas apos preflight e concorrencia existirem
- disco livre minimo validado
- timeout finito configurado
- docs/runbook atualizados

### Gate 7.2 - Antes De Rodar Arquivo Real

- worker grande roda com cgroup ou fallback registrado
- `CPUQuota`, `MemoryMax`, `MemorySwapMax`, `IOWeight`, `Nice` aplicados quando systemd estiver disponivel
- job registra modo de isolamento

### Gate 7.3 - Antes De Liberar Permanente

- canario `100MB` concluido
- canario `250MB` concluido
- canario do arquivo real `410.562.000 bytes` concluido
- health permaneceu saudavel
- Qdrant e JSON finais consistentes

### Gate 7.4 - Fechamento

- [x] heartbeat/alertas documentados
- [x] limites de shard futuro definidos
- [x] runtime/log/backlog atualizados

Resultado: ciclo tecnico `400MB` pronto para decisao operacional/auditoria de liberacao permanente do limite `500MiB`.

## Regra Para Agente Executor

Antes de cada task:

- ler `docs/99_runtime_state.md`
- ler `docs/02_spec/0122_indexing_400mb_controlled_release_spec.md`
- ler sprint correspondente

Depois de cada task:

- marcar `Executado: [x]`
- registrar evidencia na propria task
- atualizar `docs/99_runtime_state.md`
- atualizar `docs/20_master_execution_log.md`
- atualizar backlog aplicavel
