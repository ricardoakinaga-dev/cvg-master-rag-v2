# SPEC - Indexacao 400MB Com Margem Segura

## Status

- engine: SPEC
- ciclo: `INDEXING_400MB_CONTROLLED_RELEASE`
- base: `docs/INDEXING_400MB_CONTROLLED_INGESTION_ANALYSIS.md`
- status: APPROVED_FOR_BUILD_PLANNING
- alvo_real: `410562000 bytes` (`391.54 MiB`)
- limite_seguro: `524288000 bytes` (`500 MiB`)

## Objetivo

Liberar indexacao sob demanda de PDFs de ate `400MB/400MiB`, usando margem operacional segura de `500MiB`, sem voltar a travar a VPS.

O arquivo real informado tem:

- `410.562.000 bytes`
- `391,54 MiB`
- abaixo de `400MiB` (`419.430.400 bytes`)
- abaixo do limite proposto de `500MiB` (`524.288.000 bytes`)
- folga operacional: `113.726.000 bytes`, aproximadamente `108,46 MiB`

## Decisao Tecnica

O pipeline atual sera evoluido, nao substituido.

Manter:

- endpoint `/documents/upload`
- upload streaming em chunks de `1MB`
- job assíncrono para PDFs acima de `5MB`
- worker isolado
- extracao PDF por pagina/lote
- embeddings e Qdrant por batch
- commit atomico e cleanup por `ingestion_id`
- logs/metricas por lote

Adicionar antes da liberacao:

- limite seguro `MAX_UPLOAD_BYTES=524288000`
- preflight de disco/capacidade
- concorrencia maxima de jobs grandes igual a `1`
- timeout finito para job grande
- worker com controle real de CPU/RAM/IO via cgroup/systemd
- canarios progressivos ate o arquivo real

## Configuracao Alvo

```env
MAX_UPLOAD_BYTES=524288000
INGESTION_ASYNC_PDF_ENABLED=true
INGESTION_ASYNC_PDF_MIN_BYTES=5242880
PDF_INGESTION_PAGE_BATCH_SIZE=1
INGESTION_INDEX_BATCH_SIZE=8
QDRANT_UPSERT_BATCH_SIZE=32
INGESTION_WORKER_MEMORY_LIMIT_MB=2560
INGESTION_JOB_TIMEOUT_SECONDS=21600
MAX_CONCURRENT_LARGE_INGESTION_JOBS=1
LARGE_INGESTION_MIN_BYTES=52428800
LARGE_INGESTION_DISK_FREE_MIN_BYTES=5368709120
LARGE_INGESTION_RESOURCE_PROFILE=normal
CHUNKS_JSONL_SHARD_TRIGGER_CHUNK_COUNT=100000
CHUNKS_JSONL_SHARD_TRIGGER_FILE_BYTES=524288000
```

## Resource Profiles

| Perfil | CPU | RAM | IO | Uso |
|---|---:|---:|---:|---|
| `low` | `CPUQuota=40%` | `MemoryMax=1536M` | `IOWeight=50` | horario comercial |
| `normal` | `CPUQuota=70%` | `MemoryMax=2560M` | `IOWeight=100` | padrao 400MB |
| `night` | `CPUQuota=120%` | `MemoryMax=4096M` | `IOWeight=200` | janela dedicada |

Perfil inicial obrigatorio: `normal`.

## Preflight Obrigatorio

Antes de criar/iniciar job grande:

1. validar extensao PDF
2. validar tamanho <= `MAX_UPLOAD_BYTES`
3. validar espaco livre minimo em disco
4. validar Qdrant acessivel
5. validar nenhum job grande em `processing`
6. registrar `file_size_bytes`, `large_job=true`, `resource_profile`
7. retornar erro explicito se capacidade insuficiente

Regra de disco:

```text
free_disk_bytes >= max(5368709120, file_size_bytes * 3)
```

Para o arquivo de `410.562.000 bytes`, o piso de `5GiB` e o limite efetivo.

## Concorrencia

Na VPS atual:

- apenas `1` job grande por vez
- job grande = arquivo >= `52428800` (`50MiB`)
- se ja houver job grande em `processing`, novo job deve ficar bloqueado ou pendente, conforme implementacao da Sprint 7.1

## Worker Controlado

O worker deve rodar com controle de recursos via systemd/cgroup quando disponivel.

Exemplo de execucao alvo:

```bash
systemd-run \
  --unit=cvg-ingestion-<job_id> \
  --property=MemoryMax=2560M \
  --property=MemorySwapMax=512M \
  --property=CPUQuota=70% \
  --property=IOWeight=100 \
  --property=Nice=10 \
  --property=TasksMax=128 \
  /root/cvg-master-rag/src/.venv/bin/python -m scripts.ingestion_worker --job-id <job_id>
```

Fallback permitido:

- se `systemd-run` nao estiver disponivel, usar worker atual com `RLIMIT_AS`
- fallback deve ser registrado no job/log como `resource_isolation_mode=rlimit_only`

## Estado Do Job

Campos adicionais recomendados:

- `file_size_bytes`
- `large_job`
- `resource_profile`
- `resource_isolation_mode`
- `disk_free_bytes_at_start`
- `last_heartbeat_at`
- `last_batch_at`
- `pages_per_minute`
- `chunks_per_minute`
- `resource_limits`

## Observabilidade

Manter batch logs existentes e adicionar:

- evento de preflight
- modo de isolamento do worker
- limite de CPU/RAM aplicado
- concorrencia bloqueada
- timeout aplicado
- heartbeat por job

Alertas operacionais:

- RSS pico > `2048MB`
- job sem novo lote por `10min`
- `ingestion_batches.errors > 0`
- health degraded
- Qdrant indisponivel

## Persistencia

Para o primeiro release de `400MB`, manter arquivo unico `*_chunks.json` e commit atomico, porque a estimativa fica em dezenas de milhares de chunks.

Adicionar gatilhos para hardening futuro:

- se `chunk_count > 100000`, migrar para shards JSONL
- se arquivo de chunks previsto > `500MB`, migrar para shards JSONL

Constantes canonicas:

- `CHUNKS_JSONL_SHARD_TRIGGER_CHUNK_COUNT=100000`
- `CHUNKS_JSONL_SHARD_TRIGGER_FILE_BYTES=524288000`

Regra operacional: esses gatilhos nao mudam o release `400MB`; eles bloqueiam qualquer aumento futuro de limite antes de uma SPEC/BUILD propria para persistencia shardada.

## Criterios De Aceite

1. Arquivo de `410.562.000 bytes` passa pelo limite seguro de `500MiB`.
2. Upload retorna `queued`, nao processa no request.
3. Backend permanece `healthy` durante indexacao.
4. CPU/RAM/IO do worker ficam limitados pelo perfil `normal`.
5. Apenas um job grande roda por vez.
6. Job possui timeout finito.
7. Raw/chunks finais sao JSON validos.
8. Qdrant possui contagem coerente por `document_id` e `ingestion_id`.
9. Falha limpa temporarios e pontos por `ingestion_id`.
10. Canarios `100MB`, `250MB` e `391,5MiB` sao documentados antes de liberar permanentemente.

## Nao Objetivos

- Nao construir control plane de `400GB`.
- Nao trocar Qdrant.
- Nao adicionar OCR.
- Nao mudar qualidade semantica dos chunks.
- Nao liberar uploads ilimitados.
