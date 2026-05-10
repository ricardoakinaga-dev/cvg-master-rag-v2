# Analise - Indexacao Controlada Para Livros Ate 400MB

## Status

- data: 2026-05-01
- engine: DISCOVERY/ARCHITECTURE_ANALYSIS
- status: ANALYSIS_COMPLETED
- correcao: alvo real e `400MB`, nao `400GB`
- decisao: pipeline atual pode ser evoluido; nao precisa novo control plane completo de 400GB

## Contexto Atual Validado

O canario real via endpoint `/documents/upload` passou com:

- PDF de aproximadamente `37MB`
- `842` paginas
- `2919` chunks/pontos Qdrant
- `rss_peak_mb=159.71`
- status final `committed`
- backend permaneceu `healthy`
- raw/chunks JSON validos
- Qdrant consistente

Ambiente atual:

- CPU: `2` vCPU
- RAM: `7.8 GiB`
- disco livre: aproximadamente `20GB`
- cgroup v2/systemd disponivel

Configuracao atual:

- `MAX_UPLOAD_BYTES=26214400`
- `INGESTION_ASYNC_PDF_ENABLED=true`
- `INGESTION_ASYNC_PDF_MIN_BYTES=5242880`
- `PDF_INGESTION_PAGE_BATCH_SIZE=1`
- `INGESTION_INDEX_BATCH_SIZE=8`
- `QDRANT_UPSERT_BATCH_SIZE=32`
- `INGESTION_WORKER_MEMORY_LIMIT_MB=3072`
- `INGESTION_JOB_TIMEOUT_SECONDS=0`

## Conclusao Curta

Para `400MB`, nao e necessario construir uma arquitetura de 400GB com storage externo, shards obrigatorios e novo control plane completo.

O caminho atual pode suportar `400MB` sob demanda, desde que seja promovido com controles adicionais:

1. limite de upload configurado para `400MB` ou pouco acima;
2. fila/worker isolado obrigatorio;
3. controle real de CPU/RAM por systemd/cgroup;
4. preflight simples antes de aceitar o job;
5. concorrencia de jobs grandes limitada a `1`;
6. monitoramento e rollback documentados;
7. canarios progressivos ate `400MB`.

## Estimativa A Partir Do Canario

Canario observado:

- `37MB`
- `842` paginas
- `2919` chunks
- cerca de `15min`
- `rss_peak_mb=159.71`

Extrapolacao aproximada para `400MB`:

- tamanho: cerca de `10.8x` maior
- chunks estimados: cerca de `31k`
- tempo estimado: algumas horas na VPS atual, dependendo de paginas, densidade de texto, latencia de embeddings e Qdrant
- RSS esperado: nao deve crescer linearmente se o batch por pagina continuar funcionando, mas deve ser monitorado

Esta estimativa e operacional, nao garantia. PDFs variam muito por layout, densidade de texto, tabelas e qualidade de extracao.

## O Que Ja Esta Adequado

| Area | Estado | Avaliacao Para 400MB |
|---|---|---|
| Upload streaming | backend grava em chunks de `1MB` | adequado |
| Worker isolado | PDFs acima de `5MB` viram job | adequado |
| API responsiva | canario manteve `/health` healthy | adequado |
| PDF memory-safe | pagina por pagina, cache limpo | adequado |
| Embeddings/indexacao | batches pequenos | adequado |
| Qdrant | `2919` pontos no canario sem erro | provavelmente adequado para `~31k` pontos |
| Cleanup | por `ingestion_id` | adequado |
| Observabilidade | batch logs, metrics, health | adequado |

## Gaps Antes De Liberar 400MB

| Gap | Severidade | Motivo |
|---|---|---|
| `MAX_UPLOAD_BYTES` ainda em `25MB` | bloqueante operacional | precisa subir para permitir `400MB` |
| worker controla RAM por `RLIMIT_AS`, mas nao CPU | importante | 400MB pode consumir CPU por horas |
| sem `CPUQuota`/`IOWeight` por job | importante | job pode degradar a VPS |
| sem preflight de disco | importante | disco livre atual e `20GB`, suficiente para 400MB, mas precisa guardrail |
| sem limite explicito de concorrencia de jobs grandes | importante | dois uploads simultaneos podem saturar CPU/RAM/Qdrant |
| `INGESTION_JOB_TIMEOUT_SECONDS=0` | medio | job pode rodar indefinidamente se travar |
| arquivo de chunks unico ainda e aceitavel para 400MB, mas no limite | medio | `~31k` chunks deve ser ok; acima disso considerar JSONL/shards |

## Solucao Recomendada Para 400MB

### 1. Manter Endpoint Atual, Mas Com Perfil Controlado

O endpoint `/documents/upload` pode continuar sendo usado para `400MB`, desde que:

- `MAX_UPLOAD_BYTES` seja promovido para `524288000` (`500MB`) ou `419430400` (`400MB`);
- PDFs acima de `5MB` continuem sempre indo para worker;
- a API nunca execute parse/index pesado no request;
- o upload retorne `queued`.

Recomendacao inicial:

- usar `MAX_UPLOAD_BYTES=524288000` para aceitar arquivo de `400MB` com margem;
- manter `INGESTION_ASYNC_PDF_MIN_BYTES=5242880`.

### 2. Adicionar Controle De CPU/RAM/IO No Worker

Substituir ou complementar `subprocess.Popen` com `systemd-run`/cgroup.

Perfis recomendados para a VPS atual:

| Perfil | CPU | RAM | IO | Quando usar |
|---|---:|---:|---:|---|
| `low` | `CPUQuota=40%` | `MemoryMax=1536M` | `IOWeight=50` | horario comercial |
| `normal` | `CPUQuota=70%` | `MemoryMax=2560M` | `IOWeight=100` | uso padrao sob demanda |
| `night` | `CPUQuota=120%` | `MemoryMax=4096M` | `IOWeight=200` | janela noturna |

Para o primeiro release de 400MB:

- perfil padrao: `normal`
- `MemoryMax=2560M`
- `CPUQuota=70%`
- `MemorySwapMax=512M`
- `Nice=10`
- `TasksMax=128`

### 3. Preflight Simples Antes Do Job

Antes de criar o job ou antes de iniciar o worker:

- validar extensao PDF;
- validar `received_bytes <= MAX_UPLOAD_BYTES`;
- validar disco livre minimo;
- validar Qdrant acessivel;
- validar nenhum job grande em `processing`;
- opcionalmente contar paginas antes de processar;
- registrar estimativa inicial no job.

Guardrail de disco recomendado:

- bloquear se disco livre < `max(5GB, 3x tamanho_do_arquivo)`.

Para `400MB`, 3x = `1.2GB`; o piso de `5GB` e mais seguro.

### 4. Concorrencia

Para a VPS atual:

- `MAX_CONCURRENT_LARGE_INGESTION_JOBS=1`
- jobs pequenos podem continuar, mas qualquer PDF acima de `50MB` deve respeitar fila exclusiva

Estados recomendados:

```text
pending -> processing -> committed
pending -> blocked_capacity
processing -> failed/aborted
```

### 5. Timeouts E Heartbeat

Definir timeout alto, mas finito:

- `INGESTION_JOB_TIMEOUT_SECONDS=21600` (`6h`) para 400MB

Adicionar heartbeat:

- `last_heartbeat_at`
- `last_batch_at`
- `pages_per_minute`
- `chunks_per_minute`

Se `last_batch_at` ficar muito antigo, marcar como suspeito.

### 6. Observabilidade

Manter logs por lote e acrescentar alertas operacionais:

- RSS pico > `2GB`
- job sem lote novo por `10min`
- health degraded
- erros em `ingestion_batches`
- Qdrant latency alta

### 7. Persistencia De Chunks

Para `400MB`, o arquivo unico `*_chunks.json` ainda pode ser aceitavel se ficar na casa de dezenas de milhares de chunks.

Mas vale preparar um limite:

- se `chunk_count > 100000`, usar `JSONL shard`;
- se arquivo de chunks previsto > `500MB`, usar shards.

Nao e obrigatorio para o primeiro suporte a `400MB`, mas e o proximo degrau natural.

## Roadmap Proposto

### Sprint 7.1 - Gate Operacional 400MB

Entregas:

- variaveis `MAX_UPLOAD_BYTES_400MB_PROFILE` ou promocao controlada de `MAX_UPLOAD_BYTES`;
- preflight de disco/capacidade;
- bloqueio de concorrencia para jobs grandes;
- timeout finito;
- docs/runbook.

### Sprint 7.2 - Worker Com Cgroup

Entregas:

- `systemd-run` ou service template para ingestion worker;
- perfis `low`, `normal`, `night`;
- captura de status do cgroup;
- testes de falha por memoria.

### Sprint 7.3 - Canary 400MB

Entregas:

- canario `100MB`;
- canario `250MB`;
- canario `400MB`;
- comparativo RSS/CPU/tempo;
- decisao de liberar limite permanente.

### Sprint 7.4 - Hardening Opcional

Entregas:

- chunks JSONL/shards quando passar limite;
- pause/resume simples;
- heartbeat e alertas;
- dashboard operacional de job.

## Configuracao Recomendada Para Primeiro Teste 400MB

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
LARGE_INGESTION_DISK_FREE_MIN_BYTES=5368709120
```

## Decisao Recomendada

Nao criar agora o control plane de 400GB.

Criar um ciclo menor:

`INDEXING_400MB_CONTROLLED_RELEASE`

Objetivo:

Liberar indexacao sob demanda de PDFs ate `400MB` usando o pipeline atual, com cgroup CPU/RAM, preflight de capacidade, concorrencia `1`, timeout finito e canarios progressivos.

## Proximo Passo

Transformar esta analise em SPEC/roadmap/backlog do ciclo `INDEXING_400MB_CONTROLLED_RELEASE` antes de implementar.
