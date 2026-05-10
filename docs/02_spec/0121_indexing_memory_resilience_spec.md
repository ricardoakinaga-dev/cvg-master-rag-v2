# SPEC - Indexacao PDF Resiliente A Memoria

## Status

- engine: SPEC
- escopo: remediacao tecnica da indexacao/chunking de livros PDF grandes
- base: auditoria `INDEXING_MEMORY_AUDIT`
- decisao: documentacao tecnica para liberar BUILD controlado

## Problema Tecnico

O sistema possui mitigacao parcial por lotes, mas ainda permite travamento da VPS porque:
- `pdfplumber` mantem caches de pagina/layout/textmap durante a extracao
- `pdf.pages` materializa paginas em memoria
- o endpoint web chama ingestao sincrona durante request
- o parser antigo de PDF continua disponivel
- scripts de reindexacao carregam documentos/chunks/textos em memoria
- falhas por OOM deixam disco e Qdrant inconsistentes

## Objetivos De Engenharia

1. Tornar extracao de PDF incremental e liberadora de memoria.
2. Isolar processamento pesado em worker/job fora do request web.
3. Unificar todo caminho de PDF em pipeline memory-safe.
4. Tornar reindexacao batch-safe.
5. Criar semantica transacional para raw/chunks/Qdrant.
6. Expor progresso, memoria e divergencias operacionais.

## Nao Objetivos

- Nao adicionar OCR nesta fase.
- Nao trocar Qdrant por outro banco vetorial.
- Nao alterar regras de negocio de permissao de upload.
- Nao mudar modelo de embedding como objetivo principal.
- Nao otimizar qualidade semantica dos chunks alem do necessario para estabilidade.

## Arquitetura Alvo

| Componente | Responsabilidade |
|---|---|
| Upload API | Receber arquivo, validar permissao, criar job e retornar status |
| Ingestion Job Store | Persistir estado do job, progresso, erro e artefatos temporarios |
| PDF Page Extractor | Extrair texto por pagina/lote e liberar cache explicitamente |
| Chunk Batch Writer | Escrever chunks em arquivo temporario e promover somente no commit |
| Embedding Batch Runner | Gerar embeddings por lote pequeno e controlado |
| Qdrant Staging Indexer | Indexar pontos com `ingestion_id` ate commit |
| Commit/Reconciler | Promover documento ou limpar artefatos em falha |
| Runtime Metrics | Registrar RSS, paginas, chunks, tempo e divergencias |

## Fluxo Alvo

1. API recebe upload e grava arquivo em staging.
2. API cria `ingestion_job` com status `pending`.
3. Worker inicia job e marca `processing`.
4. Worker processa PDF pagina por pagina ou lote pequeno.
5. Cada lote gera chunks, embeddings e pontos Qdrant em staging.
6. Chunks sao escritos em arquivo temporario.
7. Ao final, raw metadata e chunks temporarios sao promovidos.
8. Pontos Qdrant sao considerados ativos por `document_id`.
9. Job muda para `committed`.
10. Em falha, cleanup remove temporarios e pontos por `ingestion_id`.

## Maquina De Estados

| Estado | Significado | Proximo estado valido |
|---|---|---|
| `pending` | Upload salvo, job criado | `processing`, `failed` |
| `processing` | Worker processando lotes | `committing`, `failed`, `aborted` |
| `committing` | Promocao atomica de artefatos | `committed`, `failed` |
| `committed` | Documento ativo e consistente | final |
| `failed` | Falha recuperavel com cleanup | final |
| `aborted` | Abortado por limite operacional | final |

## Contratos Internos

### IngestionJob

Campos minimos:
- `ingestion_id`
- `document_id`
- `workspace_id`
- `filename`
- `source_path`
- `status`
- `page_count`
- `pages_processed`
- `chunks_written`
- `qdrant_points_written`
- `rss_peak_mb`
- `started_at`
- `finished_at`
- `error_code`
- `error_message`

### BatchResult

Campos minimos:
- `batch_index`
- `page_start`
- `page_end`
- `chars_extracted`
- `chunks_created`
- `embeddings_created`
- `points_indexed`
- `rss_mb`
- `duration_ms`

## Regras Tecnicas

1. `pdfplumber` deve liberar cache da pagina processada antes da proxima pagina/lote.
2. O sistema nao deve manter lista completa de textos, chunks ou embeddings para documento grande.
3. O endpoint web nao deve executar indexacao pesada diretamente.
4. Todo arquivo final deve ser escrito via temporario e renome atomico.
5. Todo ponto Qdrant gerado durante processamento deve carregar `ingestion_id`.
6. Cleanup deve conseguir remover pontos por `ingestion_id` ou `document_id`.
7. Reindexacao deve usar o mesmo mecanismo batch-safe.
8. Se memoria ultrapassar limite configurado, worker deve abortar o job com cleanup.
9. Toda task do plano deve atualizar documentacao antes da proxima.

## Configuracoes Esperadas

| Variavel | Proposito | Default sugerido inicial |
|---|---|---|
| `PDF_INGESTION_PAGE_BATCH_SIZE` | paginas por lote | `1` ou `2` |
| `INGESTION_INDEX_BATCH_SIZE` | chunks por lote de embedding | `8` |
| `QDRANT_UPSERT_BATCH_SIZE` | pontos por upsert | `32` |
| `INGESTION_WORKER_MEMORY_LIMIT_MB` | limite operacional do worker | definir por VPS |
| `INGESTION_JOB_TIMEOUT_SECONDS` | timeout por job | definir por tamanho alvo |
| `INGESTION_ABORT_ON_MEMORY_LIMIT` | abortar se passar limite | `true` |

## Integridade E Consistencia

O commit so pode ocorrer se:
- raw metadata valido existe
- chunks temporario e JSON valido
- pontos Qdrant esperados foram indexados
- job possui progresso coerente
- nao ha erro pendente

Em falha:
- remover arquivo temporario de chunks
- remover raw temporario
- remover upload temporario se aplicavel
- remover pontos Qdrant por `ingestion_id`
- registrar job como `failed` ou `aborted`

## Observabilidade

Eventos obrigatorios:
- `ingestion.job.created`
- `ingestion.job.started`
- `ingestion.batch.completed`
- `ingestion.memory.limit_reached`
- `ingestion.job.committed`
- `ingestion.job.failed`
- `ingestion.cleanup.completed`
- `ingestion.reconciliation.completed`

Metricas obrigatorias:
- RSS atual e pico
- paginas processadas
- chunks criados
- pontos Qdrant gravados
- tempo por lote
- divergencia disco/Qdrant

## Criterios De Aceite

1. Livro grande processa sem OOM.
2. API responde `/health` durante indexacao.
3. Worker pode falhar sem matar API.
4. JSON final nunca fica corrompido.
5. Qdrant nao fica com pontos orfaos apos falha.
6. Reindexacao nao carrega corpus inteiro em memoria.
7. Documentacao de runtime/log/backlog e sprint e atualizada a cada task.
