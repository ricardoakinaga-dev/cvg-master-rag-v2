# 0310_MIGRATIONS.md

# Política de Migrations — CVG RAG Enterprise Premium

## Status Atual

O sistema não usa banco relacional, Alembic, Prisma ou ORM com migration formal.

O estado persistente atual está distribuído em:

- `src/data/documents/{workspace_id}/` para corpus canônico em `*_raw.json` e `*_chunks.json`
- `src/data/enterprise/*.json` para sessões, usuários, tenants e recuperação
- `src/logs/*.jsonl` para telemetria, auditoria e reparos
- Qdrant para índice vetorial e payloads de chunks

Portanto, a estratégia de migration atual é filesystem-first + reindex controlado.

## Quando Uma Migration É Obrigatória

Criar migration/documentação quando houver mudança em:

- formato de `*_raw.json`
- formato de `*_chunks.json`
- schema de `admin_state.json`, `session_state.json` ou `recovery_state.json`
- campos de payload enviados ao Qdrant
- estrutura de logs JSONL usada por métricas ou auditoria
- contrato de API persistido por clientes externos
- introdução futura de banco SQL/NoSQL

## Padrão de Nome

Use:

```text
docs/03_build/MIGRATIONS/YYYYMMDD_<descricao>.md
```

Cada migration deve conter:

- contexto
- arquivos afetados
- versão anterior
- versão nova
- script/comando de aplicação
- comando de rollback ou restauração
- validação pós-migration
- risco operacional

## Runbook Para Corpus/Qdrant

### Subir Qdrant local para validação live

Use a mesma imagem validada no GAP-03 e portas de host isoladas para não interferir em Qdrant local existente na `6333`:

```bash
docker run -d --rm \
  --name cvg-qdrant-local \
  -p 6337:6333 \
  -p 6338:6334 \
  qdrant/qdrant:v1.11.5
```

Healthcheck:

```bash
curl -fsS http://127.0.0.1:6337/readyz
```

Parar a instância temporária:

```bash
docker stop cvg-qdrant-local
```

Se a máquina local for dedicada a este projeto e a porta default estiver livre, é aceitável mapear `-p 6333:6333 -p 6334:6334` e usar `QDRANT_PORT=6333`. Para validação auditável, preferir `6337/6338`.

Recriar chunks locais:

```bash
cd src
python3 scripts/reindex_corpus.py default --local-only
```

Reindexar Qdrant a partir do corpus persistido:

```bash
cd src
QDRANT_HOST=127.0.0.1 QDRANT_PORT=6337 python3 scripts/reindex_corpus.py default
```

Reindexar sem recriar collection:

```bash
cd src
QDRANT_HOST=127.0.0.1 QDRANT_PORT=6337 python3 scripts/reindex_corpus.py default --skip-recreate
```

Rodar a suite backend completa contra Qdrant live:

```bash
cd src
QDRANT_HOST=127.0.0.1 QDRANT_PORT=6337 pytest -q -rs tests
```

Observações operacionais:

- `QDRANT_COLLECTION` usa `rag_phase0` por padrão.
- Sem `OPENAI_API_KEY`, o serviço de embeddings usa fallback offline determinístico; isso é esperado para validação local sem custo/rede externa.
- O reindex completo recria a collection por padrão. Use `--skip-recreate` apenas quando precisar preservar outros workspaces/pontos na mesma collection.
- O resultado auditado em 2026-04-29 foi `253 passed` usando `QDRANT_HOST=127.0.0.1` e `QDRANT_PORT=6337`.

## Gate De Pronto

Uma migration só é considerada pronta quando:

- existe documentação em `docs/03_build/MIGRATIONS/`
- o comando de aplicação foi testado localmente ou em staging
- o rollback está descrito
- `pytest -q src/tests` passa
- se Qdrant for afetado, os testes live com Qdrant passam no CI
- `docs/99_runtime_state.md` e `docs/20_master_execution_log.md` são atualizados

## Decisão Atual

Nenhuma migration pendente foi identificada nesta auditoria. A dívida era documental/processual: não havia política explícita para mudanças futuras de schema filesystem/Qdrant.
