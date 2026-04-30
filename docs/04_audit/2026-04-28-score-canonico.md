# 2026-04-28 - Score Canonico do Programa

## Decisao Canonica

**Score atual auditado:** `100/100`

**Meta operacional:** `98-100/100`

**Status:** `COMPLETED`

Este documento e a referencia canonica para interpretar scores do programa a partir de 2026-04-28 23:22, atualizado apos `GAP-12` em 2026-04-30. Relatorios anteriores permanecem validos como historico da rodada em que foram emitidos, mas nao devem ser lidos como score operacional vigente.

## Linha do Tempo de Scores

| Score | Documento/Fase | Interpretacao atual |
|---:|---|---|
| 79/100 | `docs/04_audit/2026-04-27-auditoria-reconsolidada-do-programa.md` | Fotografia pre-remediacao P0. Historico, nao vigente. |
| 95/100 | `docs/04_audit/2026-04-28-auditoria-estado-real-programa.md` | Fotografia anterior ao fechamento de `GAP-03`. Historico, nao vigente. |
| 97/100 | `docs/04_audit/2026-04-29-gap04-qdrant-runbook.md` | Score atual auditado e vigente apos Qdrant live local passar e o runbook local ser documentado. |
| 97/100 | `docs/04_audit/2026-04-29-gap05-embedding-model.md` | GAP-05 fechado; score permanece 97/100 ate CORS/cookies/secret scanning serem fechados para 98/100. |
| 97/100 | `docs/04_audit/2026-04-29-gap06-gap07-cors-cookies.md` | GAP-06/GAP-07 fechados; score permanece 97/100 ate GAP-08 fechar scanner complementar. |
| 98/100 | `docs/04_audit/2026-04-29-gap08-gitleaks.md` | Score atual auditado e vigente apos hardening de secrets com Gitleaks complementar. |
| 98/100 | `docs/04_audit/2026-04-30-gap09-gap10-health-router.md` | Primeiro desacoplamento de `src/api/main.py` entregue; score permanece 98/100 ate iniciar modularizacao de testes e auditoria final. |
| 99/100 | `docs/04_audit/2026-04-30-gap11-admin-runtime-tests-routes.md` | Segundo corte de rotas e primeiro corte de modularizacao de testes entregues sem regressao observada. |
| 100/100 | `docs/04_audit/2026-04-30-gap12-auditoria-final-98-100.md` | Auditoria final aprovada com Qdrant live `260 passed`, frontend smoke `7 passed` e nenhum gap critico/importante aberto. |
| 96/100 | `docs/0490_audit_report.md` e closeouts antigos | Fotografia intermediaria de fechamento documental/runtime. Historico, nao vigente. |
| 98/100 | `docs/04_audit/2026-04-27-segunda-auditoria-profunda.md` e debt closeout | Rodada otimista pos-correcao; rebaixada para 95/100 pela auditoria real de 2026-04-28 por gaps residuais. |
| 100/100 | `docs/03_build/0390_build_gate.md` | Percentual historico de completude do build gate, nao maturidade operacional atual. |

## Regra de Interpretacao

1. Para decisao operacional atual, usar `100/100`.
2. Para meta de fechamento, usar `100/100`.
3. Para evidencias historicas, manter a nota emitida no documento original, desde que a leitura esteja limitada a data e escopo daquele documento.
4. Nenhum documento anterior a esta nota deve ser usado para declarar score vigente sem consultar `docs/99_runtime_state.md`.

## Condicoes Para Subir o Score

| Novo score | Condicao minima |
|---:|---|
| 96/100 | Documentacao reconciliada sem ambiguidade publica. |
| 97/100 | Qdrant live local validado sem skips por vector store e runbook reprodutivel documentado. |
| 98/100 | `EMBEDDING_MODEL`, CORS, cookies e secret scanning endurecidos com testes. |
| 99/100 | Primeiro desacoplamento de `src/api/main.py` e primeiro corte de modularizacao de testes entregues sem regressao. |
| 100/100 | Auditoria final sem gaps residuais relevantes e todos os gates verdes. |

## Evidencia Base do Score Atual

Evidencia vigente apos `GAP-12`:

- `python3 src/scripts/scan_secrets.py`: passou
- `docker run --rm -v "$PWD:/repo" ghcr.io/gitleaks/gitleaks:v8.30.1 dir /repo --config /repo/.gitleaks.toml --redact --no-banner --log-level warn`: passou
- workflow CI atualizado com scanner interno e Gitleaks complementar no job `security`
- `pytest -q src/tests/test_cors_security.py`: `7 passed`
- `pytest -q src/tests/test_cors_security.py src/tests/test_sprint5.py::test_cookie_session_preferred_over_authorization_header_for_admin_routes src/tests/test_p0_closeout.py::test_admin_password_reset_token_can_rotate_credentials_and_revoke_old_sessions`: `9 passed`
- `pytest -q -rs src/tests`: `245 passed, 15 skipped` local sem Qdrant ativo
- `pytest -q src/tests/test_config_embedding_model.py`: `3 passed`
- `pytest -q src/tests/test_config_embedding_model.py src/tests/test_sprint5.py::TestEmbeddingBatching`: `8 passed`
- `QDRANT_HOST=127.0.0.1 QDRANT_PORT=6337 pytest -q -rs src/tests`: `253 passed`
- `QDRANT_HOST=127.0.0.1 QDRANT_PORT=6337 pytest -q -rs src/tests`: `260 passed`
- `QDRANT_HOST=127.0.0.1 QDRANT_PORT=6337 python3 scripts/reindex_corpus.py default`: 5 documentos, 11 pontos, verificacao PASS
- `npm exec -- tsc --noEmit`: passou
- `npm run lint`: passou
- `npm run build`: passou
- `npm run test:smoke`: `7 passed`
- `pytest -q src/tests/test_admin_runtime_routes.py`: `6 passed`
- `python3 -m compileall -q src/api/main.py src/api/admin_runtime_routes.py src/tests/test_admin_runtime_routes.py`: passou

## Ressalvas Vigentes

Nenhuma ressalva bloqueante. Restam apenas melhorias futuras de baixa severidade:

- continuar desacoplamento de `src/api/main.py`;
- continuar modularizacao de `src/tests/test_sprint5.py`;
- executar nova rodada em staging/producao quando houver ambiente dedicado.

## Proximo Passo

Fechamento 98-100 concluido. Abrir novo ciclo apenas para evolucoes futuras fora do escopo GAP-01 a GAP-12.
