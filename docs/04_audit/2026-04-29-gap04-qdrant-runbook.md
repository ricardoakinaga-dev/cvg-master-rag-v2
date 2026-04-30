# 2026-04-29 - GAP-04 Runbook Qdrant Local

## Objetivo

Executar `GAP-04 - Documentar comando padrao de Qdrant local`, tornando a validacao live do GAP-03 reproduzivel por qualquer operador.

## Artefatos Atualizados

| Arquivo | Atualizacao |
|---|---|
| `README.md` | Comando padrao curto para subir Qdrant local, healthcheck, reindex, suite backend e parada do container. |
| `src/README.md` | Runbook operacional detalhado para Qdrant local, reindex e validacao live. |
| `docs/03_build/0310_MIGRATIONS.md` | Runbook canonico de corpus/Qdrant com imagem, portas, healthcheck, reindex, teste e observacoes operacionais. |
| `docs/BACKLOG_EXECUTIVO_2026-04-28_GAPS_98_100.md` | `GAP-04` marcado como `DONE`. |
| `docs/30_backlog_master.md` | `GAP-04` marcado como `DONE`. |

## Comando Padrao Registrado

```bash
docker run -d --rm \
  --name cvg-qdrant-local \
  -p 6337:6333 \
  -p 6338:6334 \
  qdrant/qdrant:v1.11.5

curl -fsS http://127.0.0.1:6337/readyz

cd src
QDRANT_HOST=127.0.0.1 QDRANT_PORT=6337 python3 scripts/reindex_corpus.py default
QDRANT_HOST=127.0.0.1 QDRANT_PORT=6337 pytest -q -rs tests

docker stop cvg-qdrant-local
```

## Decisoes Operacionais

- A porta de host padrao para validacao auditavel e `6337`, preservando `6333` para qualquer Qdrant local existente.
- A imagem canonica documentada e `qdrant/qdrant:v1.11.5`, a mesma usada na validacao do GAP-03.
- O reindex completo recria a collection por padrao; `--skip-recreate` fica reservado para cenarios em que outros pontos/workspaces precisem ser preservados.
- Sem `OPENAI_API_KEY`, o pipeline usa embeddings offline deterministicas, permitindo validacao local sem custo/rede externa.

## Evidencia De Origem

O procedimento documentado reflete a validacao executada no GAP-03:

```text
QDRANT_HOST=127.0.0.1 QDRANT_PORT=6337 pytest -q -rs src/tests
253 passed in 205.82s
```

## Decisao

`GAP-04` esta **DONE**.

Score operacional atualizado para `97/100`.

Proximo passo oficial: `GAP-05 - Corrigir variavel EMBEDDING_MODEL`.
