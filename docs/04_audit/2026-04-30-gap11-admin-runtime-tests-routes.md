# 2026-04-30 - GAP-11 Admin Runtime Routes E Testes

## Objetivo

Executar `GAP-11`: modularizar gradualmente a suite monolitica e avançar o desacoplamento de `src/api/main.py` sem alterar contrato publico.

## Corte Escolhido

| Criterio | Decisao |
|---|---|
| Dominio | Runtime administrativo |
| Rotas | `GET /admin/runtime`, `POST /admin/runtime/prune-index`, `POST /admin/runtime/cleanup-operational` |
| Motivo | Bloco grande, coeso, com testes dedicados e impacto direto em operacao/admin |
| Risco controlado | Contratos HTTP preservados, schemas existentes mantidos e permissao `runtime.manage` mantida |

## Execucao

| Arquivo | Mudanca |
|---|---|
| `src/api/admin_runtime_routes.py` | Novo router dedicado para runtime administrativo. |
| `src/api/main.py` | Passou a incluir `admin_runtime_router`; bloco de runtime admin foi removido do arquivo principal. |
| `src/tests/test_admin_runtime_routes.py` | Novo arquivo dedicado para os testes de runtime admin. |
| `src/tests/test_sprint5.py` | Grupo de testes de runtime admin removido do monolito. |

## Reducao De Acoplamento

| Artefato | Depois do GAP-10 | Depois do GAP-11 |
|---|---:|---:|
| `src/api/main.py` | 2171 linhas | 1912 linhas |
| `src/tests/test_sprint5.py` | suite monolitica principal | 8246 linhas |
| `src/api/admin_runtime_routes.py` | inexistente | 275 linhas |
| `src/tests/test_admin_runtime_routes.py` | inexistente | 317 linhas |

## Validacao Executada

```bash
pytest -q src/tests/test_admin_runtime_routes.py
```

Resultado: `6 passed`.

```bash
python3 -m compileall -q src/api/main.py src/api/admin_runtime_routes.py src/tests/test_admin_runtime_routes.py
```

Resultado: passou.

```bash
pytest -q -rs src/tests
```

Resultado: `245 passed, 15 skipped`.

Observacao: os `15 skipped` continuam restritos a Qdrant live inacessivel no sandbox; esse caminho ja possui validacao live registrada no GAP-03.

Gates executados antes da extracao final do arquivo de testes, sem mudanca posterior em runtime:

```bash
python3 src/scripts/scan_secrets.py
```

Resultado: passou.

```bash
npm exec -- tsc --noEmit
npm run lint
```

Resultado: passaram em `frontend/`.

```bash
npm run test:smoke
```

Resultado: `7 passed`.

## Status

`GAP-11` esta **DONE**.

O primeiro corte de modularizacao de testes e o segundo corte de rotas foram entregues sem regressao observada. A condicao canonica para `99/100` foi atendida: primeiro desacoplamento de `src/api/main.py` + primeiro corte de modularizacao de testes.

Proximo passo oficial: `GAP-12 - Auditoria final 98-100`.
