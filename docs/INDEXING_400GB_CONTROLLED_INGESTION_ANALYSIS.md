# Analise - Indexacao Controlada Para Livros Ate 400GB

## Status

- data: 2026-05-01
- engine: DISCOVERY/ARCHITECTURE_ANALYSIS
- status: SUPERSEDED_BY_USER_CORRECTION
- decisao: substituida pela analise de `400MB`
- superseded_by: `docs/INDEXING_400MB_CONTROLLED_INGESTION_ANALYSIS.md`

## Retificacao

O usuario corrigiu o alvo de capacidade: o arquivo esperado e de ate `400MB`, nao `400GB`.

Esta analise permanece arquivada apenas como referencia historica. A fonte ativa para proximos passos e:

`docs/INDEXING_400MB_CONTROLLED_INGESTION_ANALYSIS.md`

## Contexto Atual Validado

O ciclo `INDEXING_MEMORY_RESILIENCE` estabilizou o upload grande atual:

- PDF real de aproximadamente `37 MB`
- `842` paginas
- `2919` chunks/pontos Qdrant
- `rss_peak_mb=159.71`
- endpoint real `/documents/upload` concluiu `committed`
- backend permaneceu `healthy`

Configuracao atual:

- `MAX_UPLOAD_BYTES=26214400`
- `PDF_INGESTION_PAGE_BATCH_SIZE=1`
- `INGESTION_INDEX_BATCH_SIZE=8`
- `QDRANT_UPSERT_BATCH_SIZE=32`
- `INGESTION_WORKER_MEMORY_LIMIT_MB=3072`
- `INGESTION_JOB_TIMEOUT_SECONDS=0`

Ambiente atual medido:

- CPU: `2` vCPU
- RAM: `7.8 GiB`
- swap: `4.0 GiB`
- disco raiz: `96 GB`, `76 GB` usado, `20 GB` livre
- systemd: `255`, cgroup v2 ativo

## Conclusao Curta

O sistema atual esta bom para dezenas ou centenas de MB com controle. Ele nao esta pronto para 400GB.

Para 400GB, a solucao correta nao e aumentar `MAX_UPLOAD_BYTES`. E criar uma esteira de ingestao sob demanda, com arquivo externo, preflight, fila, shards, checkpoints, controle por cgroup e commit parcial/retomavel.

## Por Que 400GB E Outra Classe De Problema

Usando o canario como referencia bruta:

- `37 MB` geraram `2919` chunks e levaram cerca de `15 min`.
- `400 GB` e mais de `10.000x` maior que `37 MB`.
- Se a relacao fosse linear, o resultado poderia chegar a dezenas de milhoes de chunks e muitos dias/semanas de processamento em uma VPS de 2 vCPU.

Essa extrapolacao nao deve ser usada como promessa de capacidade, mas mostra a ordem de grandeza do problema.

## Bloqueios Do Desenho Atual

| Area | Estado Atual | Risco Para 400GB |
|---|---|---|
| Upload HTTP multipart | `/documents/upload` recebe arquivo pelo backend | conexoes longas, timeout, proxy/body limit, falha reinicia tudo |
| Disco local | apenas `20 GB` livres | impossivel armazenar arquivo de `400 GB` |
| Worker | subprocesso Python com `RLIMIT_AS` | limita memoria, mas nao controla CPU/IO nem concorrencia global |
| CPU | sem `CPUQuota` por job | um job pode saturar os 2 vCPU |
| IO | sem limite de leitura/escrita | leitura de PDF grande e escrita de chunks pode degradar VPS |
| Chunks | um JSON final por documento | arquivo unico pode ficar enorme e ruim para commit/reindex |
| Job store | JSON por job | suficiente para pequeno/medio, fraco para checkpoints por milhoes de paginas/chunks |
| Qdrant | pontos indexados direto na colecao principal | milhoes de pontos exigem backpressure, compactacao e estrategia de cleanup mais robusta |
| PDF parser | `pdfplumber` reabre por lote/pagina | seguro em memoria, mas pode ser lento demais para PDF gigante |
| Retomada | job falho limpa artefatos | para 400GB deve retomar de checkpoints, nao recomecar do zero |

## Solucao Recomendada

Criar um novo subsistema: `Large Ingestion Control Plane`.

### 1. Entrada Do Arquivo Sem Passar Pelo Backend

Para 400GB, o arquivo nao deve ser enviado como multipart para o Uvicorn.

Opcoes recomendadas:

1. Upload direto para storage externo/local montado:
   - S3/MinIO
   - volume dedicado montado em `/mnt/ingestion`
   - caminho local previamente copiado por `rsync`, `scp`, painel admin ou presigned upload
2. API recebe apenas uma referencia:
   - `source_uri`
   - `sha256`
   - `size_bytes`
   - `workspace_id`
   - `filename`
   - perfil de recurso

Contrato alvo:

```json
{
  "source_uri": "file:///mnt/ingestion/books/livro.pdf",
  "size_bytes": 429496729600,
  "sha256": "...",
  "workspace_id": "default",
  "resource_profile": "low",
  "mode": "on_demand"
}
```

### 2. Preflight Obrigatorio

Antes de indexar:

- validar arquivo existe e tamanho confere
- validar espaco livre em storage e Qdrant
- estimar paginas
- extrair amostra de paginas
- estimar chunks
- estimar custo/tempo de embeddings
- verificar se e PDF textual ou escaneado
- recusar se precisar OCR e OCR nao estiver habilitado
- gerar relatorio de aprovacao humana

Estados:

```text
submitted -> preflight_running -> waiting_approval -> queued -> processing -> committing -> committed
```

### 3. Worker Com Controle Real De CPU/RAM/IO

Trocar o `subprocess.Popen` simples por `systemd-run` ou service template com cgroup v2.

Perfil recomendado para a VPS atual:

| Perfil | CPU | RAM | IO | Uso |
|---|---:|---:|---:|---|
| `low` | `CPUQuota=40%` | `MemoryMax=1536M` | `IOWeight=50` | processamento em horario comercial |
| `normal` | `CPUQuota=70%` | `MemoryMax=2560M` | `IOWeight=100` | janela controlada |
| `aggressive` | `CPUQuota=120%` | `MemoryMax=4096M` | `IOWeight=200` | janela noturna/dedicada |

Exemplo conceitual:

```bash
systemd-run \
  --unit=cvg-ingestion-<job_id> \
  --property=MemoryMax=2560M \
  --property=MemorySwapMax=512M \
  --property=CPUQuota=70% \
  --property=IOWeight=100 \
  --property=Nice=10 \
  --property=TasksMax=128 \
  /root/cvg-master-rag/src/.venv/bin/python -m scripts.large_ingestion_worker --job-id <job_id>
```

Beneficio:

- se o worker exceder memoria, o cgroup mata so o job
- Uvicorn/API continua vivo
- CPU fica limitada
- IO fica menos agressivo
- status pode ser consultado por `systemctl show`

### 4. Pipeline Em Shards, Nao Um JSON Gigante

Trocar arquivo unico `*_chunks.json` por manifesto + shards.

Estrutura alvo:

```text
documents/default/<document_id>/
  manifest.json
  raw.json
  chunks/
    shard_000001.jsonl
    shard_000002.jsonl
  checkpoints/
    page_000001.json
    page_001000.json
  failures/
```

Manifesto:

```json
{
  "document_id": "...",
  "source_uri": "...",
  "status": "processing",
  "page_count": 1000000,
  "pages_processed": 52000,
  "chunks_written": 180000,
  "qdrant_points_written": 180000,
  "current_shard": 18,
  "resource_profile": "normal",
  "rss_peak_mb": 1600
}
```

Beneficio:

- reprocessar apenas shard falho
- validar JSONL por linha
- commit incremental
- evitar abrir/gravar arquivo JSON gigante

### 5. Checkpoint E Retomada

Para 400GB, falha nao pode recomecar do zero.

Checkpoint minimo por lote:

- pagina inicial/final
- offset logico
- chunks criados
- ultimo shard escrito
- pontos Qdrant gravados
- hash do shard
- RSS/CPU/tempo

Retomada:

1. ler manifesto
2. validar ultimo shard completo
3. remover pontos do shard incompleto se necessario
4. continuar da proxima pagina segura

### 6. Backpressure Entre Etapas

O worker deve operar como esteira:

```text
PDF pages -> text -> chunks -> embedding queue -> qdrant queue -> checkpoint
```

Limites obrigatorios:

- max paginas em memoria: `1-4`
- max chunks em memoria: `N`, ex. `100`
- max embeddings em voo: `N`, ex. `8-32`
- max upsert pendente: `N`, ex. `32-128`
- sleep/backoff se Qdrant ou API de embeddings atrasar

### 7. Politica De Qdrant Para Milhoes De Pontos

Para documentos muito grandes:

- usar payload com `ingestion_id`, `document_id`, `shard_id`, `page_start`, `page_end`
- indexar por shard
- permitir cleanup por `ingestion_id` + `shard_id`
- considerar colecao staging ou alias quando o volume for muito alto
- executar compactacao/otimizacao fora do horario de pico
- estimar storage antes de iniciar

Para 400GB, milhoes de pontos podem exigir:

- Qdrant em disco/volume dedicado
- colecao separada por tenant ou por classe de documento
- politicas de quantizacao ou reducao de payload
- top-k e filtros desenhados para nao consultar tudo de forma ampla

### 8. Controle Operacional Sob Demanda

Adicionar comandos/acoes:

- `submit`
- `preflight`
- `approve`
- `pause`
- `resume`
- `cancel`
- `cleanup`
- `status`
- `promote`

Cada job deve poder ser pausado sem perder progresso.

### 9. Guardrails De Capacidade

Preflight deve bloquear se:

- arquivo maior que limite aprovado do perfil
- disco livre insuficiente
- Qdrant sem capacidade estimada
- tipo de PDF exige OCR e OCR esta desabilitado
- custo estimado de embeddings excede limite
- tempo estimado excede janela operacional
- outro job grande ja esta rodando

Regra pratica para storage:

- nao iniciar job de `400 GB` sem pelo menos `1 TB` livre em storage dedicado
- nao usar `/` ou `src/data` como staging de arquivo gigante

## Roadmap Proposto

### Fase 0 - Contencao

Objetivo: manter 400GB bloqueado no endpoint atual.

Entregas:

- `MAX_UPLOAD_BYTES` continua baixo
- documentar que endpoint multipart nao e caminho de 400GB
- criar limite por feature flag `LARGE_INGESTION_ENABLED=false`

### Fase 1 - Control Plane

Objetivo: criar job de ingestao por referencia externa, nao por upload web.

Entregas:

- API `POST /ingestion/large-jobs`
- job store robusto em SQLite/Postgres
- estados `submitted/preflight/waiting_approval/queued/processing/paused/failed/committed`
- endpoint de status

### Fase 2 - Preflight

Objetivo: saber se pode processar antes de gastar recursos.

Entregas:

- medicao de arquivo
- estimativa de paginas/chunks/custo/tempo
- amostragem de paginas
- relatorio de aprovacao

### Fase 3 - Worker Com Cgroup

Objetivo: controlar CPU/RAM/IO de verdade.

Entregas:

- `systemd-run` ou `cvg-ingestion-worker@.service`
- perfis `low/normal/aggressive`
- `MemoryMax`, `MemorySwapMax`, `CPUQuota`, `IOWeight`, `Nice`, `TasksMax`
- heartbeat do worker

### Fase 4 - Shards E Checkpoints

Objetivo: processar documentos enormes sem arquivo unico e com retomada.

Entregas:

- manifesto por documento
- chunks JSONL por shard
- checkpoint por lote
- resume idempotente
- cleanup por shard

### Fase 5 - Backpressure E Rate Limits

Objetivo: nao saturar embeddings, Qdrant, CPU ou IO.

Entregas:

- filas internas limitadas
- sleep/backoff por latencia
- limite de embeddings em voo
- limite de upsert em voo
- pausa/resume/cancel

### Fase 6 - Validacao Progressiva

Objetivo: provar escala em degraus antes de 400GB.

Canarios obrigatorios:

1. `50 MB`
2. `500 MB`
3. `2 GB`
4. `10 GB`
5. `50 GB`
6. `100 GB`
7. `400 GB`

Cada degrau so avanca se:

- API permanece `healthy`
- RSS fica dentro do perfil
- CPU fica dentro do perfil
- Qdrant consistente
- job retomavel
- nenhum arquivo final corrompido

## Recomendacao Para A VPS Atual

Com `2 vCPU`, `8 GB RAM` e `20 GB` livres, a VPS atual nao comporta arquivo de `400 GB` localmente.

Ela pode funcionar como:

- API/control plane
- scheduler
- orquestrador
- monitor

Mas o processamento de 400GB precisa de:

- storage externo ou volume dedicado de no minimo `1 TB`
- Qdrant com storage suficiente
- worker limitado por cgroup
- preferencialmente uma maquina dedicada para ingestao pesada

## Decisao Recomendada

Nao liberar `MAX_UPLOAD_BYTES` para 400GB no endpoint atual.

Criar um novo ciclo CVG:

```text
DISCOVERY -> PRD -> SPEC -> BUILD -> AUDIT
```

Nome sugerido:

`LARGE_DOCUMENT_CONTROLLED_INGESTION`

Objetivo:

Permitir indexacao sob demanda de documentos ate `400GB` com preflight, aprovacao, controle de CPU/RAM/IO, shards, checkpoints e retomada.
