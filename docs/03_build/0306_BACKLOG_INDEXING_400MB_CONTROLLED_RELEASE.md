# Backlog - Indexacao 400MB Com Margem Segura

## Status

- backlog_status: APPROVED_FOR_PERMANENT_CONTROLLED_RELEASE
- origem: `INDEXING_400MB_CONTROLLED_INGESTION_ANALYSIS`
- SPEC: `docs/02_spec/0122_indexing_400mb_controlled_release_spec.md`
- roadmap: `docs/03_build/0305_ROADMAP_INDEXING_400MB_CONTROLLED_RELEASE.md`
- limite_alvo: `MAX_UPLOAD_BYTES=524288000`
- arquivo_alvo: `410562000 bytes`

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
| I400-001 | 7 | 7.1 | Definir limite seguro de upload 500MiB | P0 | DONE |
| I400-002 | 7 | 7.1 | Implementar preflight de disco/capacidade | P0 | DONE |
| I400-003 | 7 | 7.1 | Limitar concorrencia de jobs grandes a 1 | P0 | DONE |
| I400-004 | 7 | 7.1 | Configurar timeout finito para job grande | P0 | DONE |
| I400-005 | 7 | 7.2 | Executar worker com systemd/cgroup | P0 | DONE |
| I400-006 | 7 | 7.2 | Registrar perfil e modo de isolamento no job | P1 | DONE |
| I400-007 | 7 | 7.2 | Testar fallback/abort por limite de memoria | P1 | DONE |
| I400-008 | 7 | 7.3 | Canary 100MB | P0 | DONE |
| I400-009 | 7 | 7.3 | Canary 250MB | P0 | DONE |
| I400-009R | 7 | 7.3 | Canary real aproximadamente 250MB | P0 | DONE |
| I400-010 | 7 | 7.3 | Canary arquivo real 391,5MiB | P0 | DONE |
| I400-011 | 7 | 7.4 | Adicionar heartbeat e alertas operacionais | P1 | DONE |
| I400-012 | 7 | 7.4 | Definir gatilho de shards JSONL futuro | P2 | DONE |

## Evidencia Sprint 7.1

- `MAX_UPLOAD_BYTES=524288000` configurado em `src/.env` e `src/.env.example`.
- Preflight de ingestao grande implementado com bloqueio por disco insuficiente, Qdrant indisponivel e concorrencia ocupada.
- Jobs grandes classificados a partir de `LARGE_INGESTION_MIN_BYTES=52428800` e limitados por `MAX_CONCURRENT_LARGE_INGESTION_JOBS=1`.
- Timeout operacional configurado em `INGESTION_JOB_TIMEOUT_SECONDS=21600`.
- Verificacao: `src/.venv/bin/pytest -q src/tests/test_ingestion_jobs.py` -> `5 passed`.
- Verificacao: `src/.venv/bin/python -m py_compile src/services/ingestion_job_service.py src/api/main.py src/scripts/ingestion_worker.py src/tests/test_ingestion_jobs.py` -> OK.
- Runtime: backend reiniciado e `/health` retornou `healthy`.

## Evidencia Sprint 7.2

- Worker grande passa a usar `systemd-run` quando disponivel, com perfil `normal`: `CPUQuota=70%`, `MemoryMax=2560M`, `MemorySwapMax=512M`, `IOWeight=100`, `Nice=10`, `TasksMax=128`.
- Job JSON registra `resource_isolation_mode`, `resource_limits` e unidade systemd aplicada; stdout/stderr do worker systemd vao para `src/logs/ingestion_worker.log`; fallback registra `rlimit_only` e motivo.
- Falha simulada por `MemoryError` finaliza job como `aborted`, grava `error_code=memory_limit_reached` e executa cleanup de upload staging.
- Verificacao: `src/.venv/bin/pytest -q src/tests/test_ingestion_jobs.py src/tests/test_ingestion_transaction_cleanup.py` -> `11 passed`.
- Verificacao: `systemd-run` probe com propriedades de cgroup -> `result: success`.
- Runtime: backend reiniciado e `/health` retornou `healthy`.

## Evidencia Sprint 7.3 Parcial

- I400-008: `canary_100MiB.pdf` (`104857600` bytes) enviado via `/documents/upload`; job `501e5ec9-d923-4833-9451-f2f0df3db27c` concluiu `committed`, `chunks_written=5`, `rss_peak_mb=128.24`, `resource_isolation_mode=systemd_run`, Qdrant `document_id=5` e `ingestion_id=5`.
- I400-009: `canary_250MiB.pdf` (`262144000` bytes) enviado via `/documents/upload`; job `f8edb9a1-a26b-4969-8cbf-3bce6e15b15b` concluiu `committed`, `chunks_written=5`, `rss_peak_mb=128.63`, `resource_isolation_mode=systemd_run`, Qdrant `document_id=5` e `ingestion_id=5`.
- I400-009R: arquivo real `Ettinger's Textbook of Veterinary Internal Medicine, 9th Edition (VetBooks.ir).pdf` (`255251193` bytes) enviado via `/documents/upload`; job `dd52408f-78aa-467c-a713-a6f274b1cf8c` concluiu `committed`, `final_document_id=a7867508-e9bc-4b2b-9045-6a1ec62f4823`, `page_count=2801`, `char_count=15567412`, `chunks_written=17761`, `qdrant_points_written=17761`, Qdrant por `document_id=17761`, Qdrant por `ingestion_id=17761`, `rss_peak_mb=242.71`, `resource_isolation_mode=systemd_run`, backend `healthy`, sem OOM no kernel.
- Hardening operacional aplicado durante I400-009R: endpoint `GET /documents/ingestion-jobs` e painel de jobs na tela `/documents`.
- O backend permaneceu `healthy`; `qdrant.points=2950`, `operational_documents=3`, `operational_chunks=2929`.
- Limitacao registrada: fixtures validam upload/preflight/worker/cgroup, mas nao simulam complexidade textual do livro real.
- I400-010 concluido: arquivo real `0000 - Surgery-2nd - 2ed - Full-Book - N-A - cat - surgery - routine - 26441926.pdf` (`410562000` bytes) enviado pela web; job `5e084499-7c84-435e-9c79-2bcd976bd7af` concluiu `committed`, `final_document_id=cbe57a5e-af6f-4275-8eea-7717c391c394`, `3109` paginas, `18679` chunks/pontos, chunks JSON final `18679`, Qdrant por `document_id=18679`, Qdrant por `ingestion_id=18679`, `rss_peak_mb=418.52`, upload staging removido, `/health=healthy`, busca filtrada retornando `3` resultados e sem OOM no kernel.
- Risco operacional para I400-011: API e `/health` apresentaram lentidao/timeout sob carga do canario final; auditoria confirmou que a indexacao nao falhou, mas a web pode aparentar falha quando o backend nao responde rapido. Tornar health/status leves e baseados no JSON do job, sem varrer inventario/chunks nem executar contagens pesadas durante ingestao.

## Sprint Files

- `docs/03_build/INDEXING_400MB_SPRINTS/SPRINT_7.1_GATE_OPERACIONAL_400MB.md`
- `docs/03_build/INDEXING_400MB_SPRINTS/SPRINT_7.2_WORKER_CGROUP.md`
- `docs/03_build/INDEXING_400MB_SPRINTS/SPRINT_7.3_CANARY_400MB.md`
- `docs/03_build/INDEXING_400MB_SPRINTS/SPRINT_7.4_HARDENING_OPERACIONAL.md`

## Evidencia Sprint 7.4

- I400-011 concluido: job service registra `last_heartbeat_at`, `last_batch_at`, `pages_per_minute`, `chunks_per_minute`, `operational_status`, `operational_alerts` e calcula `seconds_since_last_batch` na leitura leve.
- Processamento PDF controlado atualiza heartbeat/lote a cada batch por `record_ingestion_heartbeat`.
- `/health?light=true` retorna health leve com Qdrant `ok`, sem inventario, telemetria ou contagens Qdrant pesadas.
- Frontend shell passa a consumir health leve e a tela `/documents` preserva o ultimo status valido quando a atualizacao de jobs atrasa, exibindo aviso operacional em vez de aparentar falha definitiva.
- Verificacao: `py_compile` dos modulos alterados passou; `pytest -q src/tests/test_ingestion_jobs.py src/tests/test_sprint5.py::TestHealthEndpoint` -> `13 passed`; `tsc --noEmit`, `npm run lint` e `npm run build` passaram.
- Runtime: backend/frontend reiniciados nos servicos existentes; `GET /health?workspace_id=default&light=true` retornou `mode=light`, `status=healthy`, Qdrant `ok`, `corpus=null`, `telemetry=null`.
- I400-012 concluido: gatilho futuro de shards JSONL formalizado em `docs/02_spec/0122_indexing_400mb_controlled_release_spec.md`, `src/core/config.py` e `src/.env.example` com `CHUNKS_JSONL_SHARD_TRIGGER_CHUNK_COUNT=100000` e `CHUNKS_JSONL_SHARD_TRIGGER_FILE_BYTES=524288000`.
- Regra de escala: release `400MB` permanece em `*_chunks.json` atomico; qualquer aumento futuro de limite deve ser bloqueado ate SPEC/BUILD propria para persistencia em shards JSONL quando `chunk_count > 100000` ou arquivo de chunks previsto > `500MB`.
- Verificacao I400-012: `src/.venv/bin/python -m py_compile src/core/config.py` passou; import direto confirmou os dois thresholds canonicos.

## Decisao Operacional Final

- Status: `APPROVED_FOR_PERMANENT_CONTROLLED_RELEASE`
- Limite liberado: `MAX_UPLOAD_BYTES=524288000`
- Auditoria: `docs/04_audit/INDEXING_400MB_CONTROLLED_RELEASE/0490_audit_report.md`
- Condicoes: manter concorrencia grande `1`, timeout `21600s`, worker isolado, health leve no frontend e gatilhos JSONL para qualquer aumento futuro acima de `500MiB`.
