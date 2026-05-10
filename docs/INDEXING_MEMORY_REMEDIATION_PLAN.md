# Plano de Remediacao - Indexacao PDF Sem Travamento

## Contexto

Este plano nasce da auditoria `INDEXING_MEMORY_AUDIT`, que confirmou novo `oom-kill` durante upload/indexacao de livro PDF grande.

Evidencias principais:
- backend morto pelo kernel em `2026-04-30 05:03:41 UTC`
- processo Python com cerca de `4.8GB` de RSS anonimo antes do kill
- arquivo `d057d3c6-13e1-4fd9-bdf9-9b1c26ea7d38_chunks.json` ficou JSON invalido
- documento parcial ficou sem raw JSON correspondente
- Qdrant manteve `2312` pontos orfaos
- `/health` mostrou `workspace_points=2524` contra corpus reconhecido com `chunks=41`

## Objetivo

Impedir que novas indexacoes de livros grandes travem a VPS, garantindo:
- API responsiva durante processamento pesado
- consumo de memoria limitado e observavel
- PDF processado sem acumulacao de cache por pagina
- reindexacao segura para documentos grandes
- rollback/cleanup quando houver falha
- consistencia entre disco, registry e Qdrant

## Principios

1. Nenhuma indexacao pesada deve rodar dentro do request web.
2. Nenhum caminho de PDF deve carregar o livro inteiro em memoria.
3. Nenhum arquivo final deve ser escrito diretamente antes da conclusao.
4. Nenhum ponto Qdrant deve virar ativo antes do commit documental.
5. Toda task deve atualizar documentacao antes da proxima task.
6. Toda task deve marcar sua propria execucao no arquivo de sprint.

## Fases

| Fase | Nome | Resultado esperado |
|---|---|---|
| 0 | Contencao e reconciliacao | Estado parcial limpo e nova tentativa pesada bloqueada ate remediacao |
| 1 | Extracao PDF memory-safe | `pdfplumber` usado com liberacao de cache por pagina/lote |
| 2 | Worker de ingestao isolado | Upload nao bloqueia Uvicorn e processamento tem limite proprio |
| 3 | Unificacao dos caminhos PDF | Upload, corpus canonico e reindex usam pipeline seguro |
| 4 | Reindexacao batch-safe | Scripts/admin nao carregam chunks/texts/embeddings inteiros |
| 5 | Transacao e cleanup | Falha no meio nao deixa JSON corrompido nem pontos orfaos |
| 6 | Observabilidade e validacao | Memoria, progresso e divergencias visiveis por lote |

## Ordem Obrigatoria

1. Executar Fase 0 antes de qualquer nova tentativa com livro grande.
2. Implementar Fase 1 antes de reabilitar PDF grande no fluxo web.
3. Implementar Fase 2 antes de permitir upload de livro grande por usuario.
4. Implementar Fases 3 e 4 antes de executar reindexacao ampla.
5. Implementar Fase 5 antes de considerar o fluxo confiavel.
6. Fechar Fase 6 com teste real e evidencia de memoria.

## Criterio De Pronto Geral

O ciclo so pode ser fechado quando:
- API permanece saudavel durante indexacao de livro grande
- RSS do worker fica abaixo do limite operacional definido
- falha simulada no meio nao deixa `*_chunks.json` invalido
- Qdrant nao mantem pontos orfaos apos falha
- `/health` nao reporta divergencia entre corpus e Qdrant
- documentacao de estado e log estao atualizados

## Referencias De Execucao

- SPEC: `docs/02_spec/0121_indexing_memory_resilience_spec.md`
- Roadmap: `docs/03_build/0303_ROADMAP_INDEXING_MEMORY_RESILIENCE.md`
- Backlog: `docs/03_build/0304_BACKLOG_INDEXING_MEMORY_RESILIENCE.md`
- Sprints: `docs/03_build/INDEXING_MEMORY_SPRINTS/`
