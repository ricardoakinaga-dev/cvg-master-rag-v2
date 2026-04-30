# 0401 - AUDIT PLAN

## Objetivo

Executar auditoria final GAP-12 e decidir se o programa pode sair de 99/100 para 100/100.

## Plano De Execucao

| Fase | Area | Evidencia esperada |
|---|---|---|
| 1 | PRD adherence | Funcionalidades core implementadas e testadas |
| 2 | SPEC adherence | Contratos de API, dados, seguranca e observabilidade preservados |
| 3 | Runtime | Backend e frontend executam em smoke real |
| 4 | Logs | Request ID, traces, auditoria admin e eventos operacionais presentes |
| 5 | Metricas | Health, metrics, SLO, alerts e runtime admin disponiveis |
| 6 | Integracoes | Qdrant live, embeddings offline fallback, frontend/backend |
| 7 | Integridade | Corpus canonico, reindex e isolamento por workspace |
| 8 | Seguranca | RBAC, CORS, cookies, secrets e scanners |
| 9 | Experiencia operacional | Rotas principais e workflows web via Playwright |
| 10 | GAPs | Classificacao residual |
| 11 | Remediacao | Plano para melhorias nao bloqueantes |
| 12 | Relatorio final | Score e decisao |

## Gates Planejados

| Gate | Comando |
|---|---|
| Backend sem Qdrant live | `pytest -q -rs src/tests` |
| Backend com Qdrant live | `QDRANT_HOST=127.0.0.1 QDRANT_PORT=6337 pytest -q -rs src/tests` |
| Qdrant reindex | `QDRANT_HOST=127.0.0.1 QDRANT_PORT=6337 python3 scripts/reindex_corpus.py default` |
| Secret scan interno | `python3 src/scripts/scan_secrets.py` |
| Gitleaks | `docker run --rm -v "$PWD:/repo" ghcr.io/gitleaks/gitleaks:v8.30.1 dir /repo --config /repo/.gitleaks.toml --redact --no-banner --log-level warn` |
| TypeScript | `npm exec -- tsc --noEmit` em `frontend/` |
| Lint | `npm run lint` em `frontend/` |
| Build | `npm run build` em `frontend/` |
| Smoke E2E | `npm run test:smoke` em `frontend/` |

## Criterio De Aprovacao

Auditoria aprovada se todos os gates passarem, Qdrant live eliminar os skips, e nao houver gap critico ou importante aberto.
