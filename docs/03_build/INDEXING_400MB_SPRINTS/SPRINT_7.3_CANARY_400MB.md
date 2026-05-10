# Sprint 7.3 - Canary 400MB

## Objetivo

Validar progressivamente o limite seguro de `500MiB` ate o arquivo real de `391,5MiB`.

## Tasks

### I400-008 - Canary 100MB

- Executado: [x]
- O QUE: testar primeiro degrau acima do canario de 37MB.
- ONDE: runtime local/staging, endpoint `/documents/upload`.
- COMO: executar PDF ou fixture realista de aproximadamente `100MB`, monitorando health, job, logs e Qdrant.
- DEPENDENCIA: Sprint 7.2.
- CRITERIO DE PRONTO: `committed`, health saudavel, JSON/Qdrant consistentes.
- EVIDENCIA: fixture PDF valida `canary_100MiB.pdf` com `104857600` bytes enviada via `/documents/upload`; upload `201 queued`, `ingestion_id=501e5ec9-d923-4833-9451-f2f0df3db27c`, `final_document_id=458607c6-3291-4b16-a15a-7a0c209c9267`, status `committed`, `page_count=5`, `chunks_written=5`, `qdrant_points_written=5`, `rss_peak_mb=128.24`, `resource_isolation_mode=systemd_run`, backend `/health=healthy`.
- OBSERVACAO: fixture usa stream PDF grande nao referenciado para validar upload/preflight/worker/cgroup sem simular complexidade textual de livro real.
- REGRA POS-TASK: marcar `Executado: [x]`, registrar evidencia e atualizar runtime/log/backlog antes da proxima task.

### I400-009 - Canary 250MB

- Executado: [x]
- O QUE: testar degrau intermediario.
- ONDE: runtime local/staging, endpoint `/documents/upload`.
- COMO: executar PDF ou fixture realista de aproximadamente `250MB`, monitorando CPU/RAM/IO.
- DEPENDENCIA: I400-008.
- CRITERIO DE PRONTO: `committed`, health saudavel, sem violar limites do perfil.
- EVIDENCIA: fixture PDF valida `canary_250MiB.pdf` com `262144000` bytes enviada via `/documents/upload`; upload `201 queued`, `ingestion_id=f8edb9a1-a26b-4969-8cbf-3bce6e15b15b`, `final_document_id=660f6eb2-3b08-420c-96cd-4ac0a8f0e030`, status `committed`, `page_count=5`, `chunks_written=5`, `qdrant_points_written=5`, `rss_peak_mb=128.63`, `resource_isolation_mode=systemd_run`, backend `/health=healthy`.
- OBSERVACAO: durante o upload de `250MiB`, o backend permaneceu saudavel, mas o stack multipart manteve CPU do Uvicorn em torno de `30%` antes da criacao do job; isso deve entrar no hardening operacional.
- REGRA POS-TASK: marcar `Executado: [x]`, registrar evidencia e atualizar runtime/log/backlog antes da proxima task.

### I400-010 - Canary arquivo real 391,5MiB

- Executado: [x]
- O QUE: validar o arquivo alvo real.
- ONDE: runtime local/staging, endpoint `/documents/upload`.
- COMO: executar arquivo de `410562000` bytes com `MAX_UPLOAD_BYTES=524288000`, monitorando do inicio ao commit.
- DEPENDENCIA: I400-009.
- CRITERIO DE PRONTO: `committed`, `rss_peak_mb` aceitavel, health saudavel, JSON valido, Qdrant consistente, docs atualizadas.
- STATUS FINAL: concluido `committed`.
- EVIDENCIA FINAL: job `5e084499-7c84-435e-9c79-2bcd976bd7af`; `final_document_id=cbe57a5e-af6f-4275-8eea-7717c391c394`; arquivo `0000 - Surgery-2nd - 2ed - Full-Book - N-A - cat - surgery - routine - 26441926.pdf`; `file_size_bytes=410562000`; `status=committed`; `page_count=3109`; `pages_processed=3109`; `chunks_written=18679`; `qdrant_points_written=18679`; chunks JSON final `18679`; Qdrant por `document_id=18679`; Qdrant por `ingestion_id=18679`; `rss_peak_mb=418.52`; `started_at=2026-05-01T16:27:15.548149Z`; `finished_at=2026-05-01T21:59:12.575339Z`; upload staging removido; `/health=healthy`; busca filtrada por `document_id` retornou `3` resultados; sem OOM no kernel desde o inicio do upload.
- RISCO OBSERVADO: API e `/health` apresentaram lentidao/timeout sob carga do canario final. Auditoria posterior confirmou que a indexacao nao falhou; a falha percebida vem da camada de observabilidade/API, que pode varrer inventario/chunks e fazer chamadas pesadas durante ingestao. Tratar em I400-011 antes da liberacao permanente.
- REGRA POS-TASK: marcar `Executado: [x]`, registrar evidencia e atualizar runtime/log/backlog antes de liberar permanente.

### I400-009R - Canary real aproximadamente 250MB

- Executado: [x]
- O QUE: validar arquivo real enviado pelo usuario antes do alvo final de `391,5MiB`.
- ONDE: runtime publico existente, endpoint `/documents/upload`, worker `systemd_run`.
- COMO: monitorar job ate `committed`, sem criar portas/dependencias e preservando backend/frontend existentes.
- DEPENDENCIA: I400-009.
- CRITERIO DE PRONTO: `committed`, health saudavel, `chunks_written == qdrant_points_written`, RSS abaixo do limite cgroup, JSON/Qdrant consistentes.
- EVIDENCIA: arquivo `Ettinger's Textbook of Veterinary Internal Medicine, 9th Edition (VetBooks.ir).pdf` recebido com `255251193` bytes; `ingestion_id=dd52408f-78aa-467c-a713-a6f274b1cf8c`; `final_document_id=a7867508-e9bc-4b2b-9045-6a1ec62f4823`; status `committed`; `page_count=2801`; `char_count=15567412`; `chunks_written=17761`; `qdrant_points_written=17761`; Qdrant por `document_id=17761`; Qdrant por `ingestion_id=17761`; `rss_peak_mb=242.71`; backend `healthy`; erros de lote `0`; upload staging removido; busca filtrada por documento retornou resultados com `page_hint`.
- MELHORIA APLICADA: backend passou a expor `GET /documents/ingestion-jobs`; frontend `/documents` passou a mostrar jobs recentes com status, paginas, chunks, pontos, RSS, tamanho e modo de isolamento.
- REGRA POS-TASK: ao concluir, marcar `Executado: [x]`, registrar evidencia final e atualizar runtime/log/backlog antes da proxima validacao.

## Gate Do Sprint

- [x] canarios progressivos concluidos
- [x] canario real aproximadamente 250MB concluido
- [x] arquivo real validado (`410562000` bytes)
- [ ] decisao de liberar permanente registrada

## Verificacao

- `canary_100MiB.pdf`: JSON final valido, chunks JSON valido, Qdrant `document_id=5` e `ingestion_id=5`.
- `canary_250MiB.pdf`: JSON final valido, chunks JSON valido, Qdrant `document_id=5` e `ingestion_id=5`.
- `Ettinger's Textbook...pdf`: `committed`, `255251193` bytes, `2801` paginas, `17761` chunks/pontos, `rss_peak_mb=242.71`, sem erro.
- arquivo final `410562000` bytes: job `5e084499-7c84-435e-9c79-2bcd976bd7af` concluiu `committed`, `3109/3109` paginas, `18679` chunks/pontos, `rss_peak_mb=418.52`, Qdrant consistente, upload removido e busca filtrada funcionando.
- `/health`/API: apos fim da carga, `/health=healthy` e API de jobs voltou a responder; rotas de observabilidade deram timeout em `20s` durante carga, com hardening obrigatorio em I400-011.

## Resultado

Sprint 7.3 concluida. Os degraus `100MiB` e `250MiB` de fixture passaram pelo endpoint real e pelo worker com `systemd_run`; o arquivo real de aproximadamente `250MB` concluiu `committed` com Qdrant consistente; o canario final de `391,5MiB` concluiu `committed` sem OOM e com Qdrant/arquivos/busca consistentes. A liberacao permanente ainda depende da Sprint 7.4 por causa da degradacao temporaria de observabilidade/API durante a carga.
