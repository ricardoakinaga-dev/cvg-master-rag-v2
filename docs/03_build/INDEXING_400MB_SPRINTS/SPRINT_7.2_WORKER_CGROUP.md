# Sprint 7.2 - Worker Com Cgroup

## Objetivo

Controlar CPU, RAM e IO do worker de ingestao grande usando systemd/cgroup quando disponivel.

## Tasks

### I400-005 - Executar worker com systemd/cgroup

- Executado: [x]
- O QUE: substituir ou complementar `subprocess.Popen` com isolamento via `systemd-run`.
- ONDE: `src/services/ingestion_job_service.py`, `src/scripts/ingestion_worker.py`.
- COMO: aplicar perfil `normal`: `CPUQuota=70%`, `MemoryMax=2560M`, `MemorySwapMax=512M`, `IOWeight=100`, `Nice=10`, `TasksMax=128`.
- DEPENDENCIA: Sprint 7.1.
- CRITERIO DE PRONTO: worker grande inicia em unidade systemd propria quando disponivel.
- EVIDENCIA: `spawn_ingestion_worker()` agora usa `systemd-run` para `large_job=true`; probe real `systemd-run --unit=cvg-ingestion-probe-7-2 ... /bin/true` concluiu com `result: success`.
- REGRA POS-TASK: marcar `Executado: [x]`, registrar evidencia e atualizar runtime/log/backlog antes da proxima task.

### I400-006 - Registrar perfil e modo de isolamento no job

- Executado: [x]
- O QUE: tornar auditavel se o job rodou com cgroup ou fallback.
- ONDE: job JSON, telemetry e logs.
- COMO: adicionar `resource_profile`, `resource_isolation_mode`, `resource_limits`.
- DEPENDENCIA: I400-005.
- CRITERIO DE PRONTO: status do job mostra perfil e limites aplicados.
- EVIDENCIA: job grande registra `resource_isolation_mode=systemd_run`, `resource_limits.CPUQuota=70%`, `MemoryMax=2560M`, `MemorySwapMax=512M`, `IOWeight=100`, `Nice=10`, `TasksMax=128` e `systemd_unit`; stdout/stderr do worker systemd vao para `src/logs/ingestion_worker.log`; fallback registra `resource_isolation_mode=rlimit_only`.
- REGRA POS-TASK: marcar `Executado: [x]`, registrar evidencia e atualizar runtime/log/backlog antes da proxima task.

### I400-007 - Testar fallback/abort por limite de memoria

- Executado: [x]
- O QUE: validar que falha de recurso nao derruba API.
- ONDE: testes e runtime controlado.
- COMO: simular limite baixo e confirmar job `aborted/failed`, cleanup e health saudavel.
- DEPENDENCIA: I400-006.
- CRITERIO DE PRONTO: teste automatizado ou reproducao direta confirma isolamento.
- EVIDENCIA: teste simula `MemoryError`, job finaliza `aborted` com `error_code=memory_limit_reached`, upload staging e limpo; backend reiniciado e `/health` retornou `healthy`.
- REGRA POS-TASK: marcar `Executado: [x]`, registrar evidencia e atualizar runtime/log/backlog antes da proxima task.

## Gate Do Sprint

- [x] worker grande com controle de recurso
- [x] fallback registrado
- [x] falha de recurso nao derruba API

## Verificacao

- `src/.venv/bin/pytest -q src/tests/test_ingestion_jobs.py` -> `8 passed`
- `src/.venv/bin/pytest -q src/tests/test_ingestion_jobs.py src/tests/test_ingestion_transaction_cleanup.py` -> `11 passed`
- `src/.venv/bin/python -m py_compile src/services/ingestion_job_service.py src/scripts/ingestion_worker.py src/tests/test_ingestion_jobs.py` -> OK
- `systemd-run --unit=cvg-ingestion-probe-7-2 --collect --wait --property=CPUQuota=70% --property=MemoryMax=2560M --property=MemorySwapMax=512M --property=IOWeight=100 --property=Nice=10 --property=TasksMax=128 /bin/true` -> `result: success`
- `systemctl restart cvg-master-rag-backend.service` + `curl http://127.0.0.1:8000/health` -> backend `healthy`

## Resultado

Sprint 7.2 concluida. Jobs grandes agora tentam rodar em unidade systemd propria com perfil `normal`; quando `systemd-run` nao estiver disponivel ou falhar, o job registra fallback `rlimit_only` e ainda aplica limite de memoria via worker. O canario real de `391,5MiB` continua pendente para Sprint 7.3 com canarios progressivos.
