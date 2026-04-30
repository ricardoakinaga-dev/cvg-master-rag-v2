# 2026-04-30 - GAP-09/GAP-10 Health Router

## Objetivo

Executar `GAP-09/GAP-10`: definir o primeiro corte de extracao de `src/api/main.py` e entregar um router dedicado sem alterar contrato publico.

## Plano Tecnico Do GAP-09

| Criterio | Decisao |
|---|---|
| Dominio escolhido | Health/runtime basico |
| Motivo | Baixa ruptura, um endpoint unico, contrato simples e cobertura existente por unit/direct call, TestClient e Playwright. |
| Arquivo novo | `src/api/health_routes.py` |
| Contrato publico preservado | `GET /health` |
| Testes alvo | `TestHealthEndpoint`, traces via `/health`, backend completo e Playwright smoke |
| Ordem futura | Depois de health, seguir para modularizacao de testes (`GAP-11`) antes de novas extracoes maiores. |

Dominios adiados:

- Auth/session: risco maior por cookies, RBAC e compatibilidade de chamadas diretas em testes.
- Admin/runtime: alta densidade de dependencias e payloads.
- Documents/query/evaluation: contratos mais amplos e acoplados a corpus/Qdrant.

## Execucao Do GAP-10

| Arquivo | Mudanca |
|---|---|
| `src/api/health_routes.py` | Criado router dedicado com `GET /health` e `health_check`. |
| `src/api/main.py` | Passou a incluir `health_router`; bloco do endpoint `/health` foi removido do arquivo principal. |
| `src/tests/test_sprint5.py` | Teste direto de `health_check` passou a importar de `api.health_routes` e monkeypatchar o novo modulo. |

## Resultado Estrutural

| Item | Antes | Depois |
|---|---:|---:|
| `src/api/main.py` | 2231 linhas | 2171 linhas |
| `src/api/health_routes.py` | 0 linhas | 72 linhas |

## Validacoes

```text
pytest -q src/tests/test_sprint5.py::TestHealthEndpoint::test_health_reports_corpus_and_qdrant
1 passed
```

```text
pytest -q src/tests/test_p0_closeout.py::test_observability_traces_returns_recent_spans_and_headers src/tests/test_p0_closeout.py::test_admin_can_read_slo_and_traces_for_foreign_workspace
2 passed
```

```text
python3 -m compileall -q src/api/main.py src/api/health_routes.py
passou
```

```text
pytest -q -rs src/tests
245 passed, 15 skipped
```

Os 15 skips permanecem causados por Qdrant local ausente nesta execucao; `GAP-03` ja validou Qdrant live com `253 passed`.

```text
python3 src/scripts/scan_secrets.py
passou
```

```text
npm run test:smoke
7 passed
```

## Decisao

`GAP-09` e `GAP-10` estao **DONE**.

O primeiro desacoplamento de `src/api/main.py` foi entregue sem regressao observada. O score operacional permanece `98/100` ate iniciar `GAP-11` e executar auditoria final.

Proximo passo oficial: `GAP-11 - Modularizar testes monoliticos gradualmente`.
