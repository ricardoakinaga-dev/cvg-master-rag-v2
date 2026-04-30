# 2026-04-29 - GAP-05 EMBEDDING_MODEL

## Objetivo

Executar `GAP-05 - Corrigir variavel EMBEDDING_MODEL`, alinhando a configuracao real com `src/.env.example` e preservando compatibilidade com o nome legado `EMBEDDING_EMBEDDING_MODEL`.

## Falha Reproduzida

Antes da correcao, o teste novo mostrou o comportamento incorreto:

```text
pytest -q src/tests/test_config_embedding_model.py
2 failed, 1 passed
```

Falhas reproduzidas:

- `EMBEDDING_MODEL` era ignorada quando `EMBEDDING_EMBEDDING_MODEL` existia.
- `services.embedding_service.get_embedding()` continuava usando `text-embedding-3-small` como default efetivo mesmo com `EMBEDDING_MODEL` configurada.

## Correcao Aplicada

| Arquivo | Mudanca |
|---|---|
| `src/core/config.py` | `EMBEDDING_MODEL` passou a ser lida como variavel primaria. |
| `src/core/config.py` | `EMBEDDING_EMBEDDING_MODEL` foi mantida como fallback legado. |
| `src/tests/test_config_embedding_model.py` | Adicionados testes para prioridade da variavel primaria, fallback legado e uso efetivo pelo embedding service. |

Regra final:

```python
EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL",
    os.getenv("EMBEDDING_EMBEDDING_MODEL", "text-embedding-3-small"),
)
```

## Validacoes

```text
pytest -q src/tests/test_config_embedding_model.py
3 passed
```

```text
pytest -q src/tests/test_config_embedding_model.py src/tests/test_sprint5.py::TestEmbeddingBatching
8 passed
```

```text
python3 src/scripts/scan_secrets.py
Secret scan passed: no high-signal secrets found.
```

```text
pytest -q -rs src/tests
241 passed, 15 skipped in 100.19s
```

Os 15 skips da suite local sao os mesmos testes live que dependem de Qdrant ativo no ambiente. A validacao live com Qdrant ja foi executada no GAP-03 com `253 passed`.

## Decisao

`GAP-05` esta **DONE**.

Score operacional permanece `97/100`, porque o criterio de `98/100` depende do fechamento conjunto de `GAP-05`, `GAP-06`, `GAP-07` e `GAP-08`.

Proximo passo oficial: `GAP-06/GAP-07 - Hardening de CORS e cookies`.
