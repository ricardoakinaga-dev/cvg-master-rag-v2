# BACKLOG EXECUTIVO - FECHAMENTO 98-100

## P0 - Governanca e confiabilidade da nota

### GAP-01 - Reconciliar score canonico do programa

- **Status:** DONE.
- **Descricao:** eliminar divergencia entre documentos que declaram 79/100, 95/100, 98/100 e 100/100.
- **Onde:** `docs/99_runtime_state.md`, `docs/20_master_execution_log.md`, `docs/03_build/0390_build_gate.md`, `docs/04_audit/`.
- **Como:** preservar historico, mas explicitar qual e o score atual auditado e qual e a meta.
- **Dependencia:** auditoria de 2026-04-28.
- **Criterio de pronto:** leitor externo consegue identificar sem ambiguidade: score atual 95/100, meta 98-100, condicoes para subir.
- **Evidencia:** `docs/04_audit/2026-04-28-score-canonico.md`, `docs/03_build/0390_build_gate.md`, `docs/99_runtime_state.md`.
- **Risco:** Alto.
- **Impacto:** Alto.
- **Prioridade:** P0.

### GAP-02 - Criar relatorio canonico de fechamento residual

- **Status:** DONE.
- **Descricao:** consolidar os gaps residuais e criterios de aceite em um unico artefato de transicao.
- **Onde:** `docs/04_audit/`.
- **Como:** criar relatorio curto referenciando auditoria real, plano, roadmap e backlog.
- **Dependencia:** GAP-01.
- **Criterio de pronto:** relatorio cita evidencias executadas e backlog residual.
- **Evidencia:** `docs/04_audit/2026-04-28-fechamento-residual-98-100.md`.
- **Risco:** Medio.
- **Impacto:** Alto.
- **Prioridade:** P0.

## P1 - Runtime live e configuracao

### GAP-03 - Rodar suite backend com Qdrant local ativo

- **Status:** DONE.
- **Descricao:** eliminar os 15 skips por Qdrant ausente.
- **Onde:** ambiente local, `src/tests/test_sprint5.py`, docs de operacao.
- **Como:** subir Qdrant na versao do CI, rodar `pytest -q -rs src/tests`, registrar resultado.
- **Dependencia:** Docker ou Qdrant local disponivel.
- **Criterio de pronto:** suite backend sem skips por `Qdrant host port not reachable`.
- **Evidencia:** `docs/04_audit/2026-04-29-gap03-qdrant-live.md`; `QDRANT_HOST=127.0.0.1 QDRANT_PORT=6337 pytest -q -rs src/tests` -> `253 passed`.
- **Risco:** Medio.
- **Impacto:** Alto.
- **Prioridade:** P1.

### GAP-04 - Documentar comando padrao de Qdrant local

- **Status:** DONE.
- **Descricao:** tornar a validacao live reproduzivel por qualquer operador.
- **Onde:** `README.md`, `src/README.md` ou `docs/03_build/0310_MIGRATIONS.md`.
- **Como:** documentar imagem, portas, healthcheck e comando de teste.
- **Dependencia:** GAP-03.
- **Criterio de pronto:** operador consegue subir Qdrant e rodar suite com os comandos documentados.
- **Evidencia:** `README.md`, `src/README.md`, `docs/03_build/0310_MIGRATIONS.md`, `docs/04_audit/2026-04-29-gap04-qdrant-runbook.md`.
- **Risco:** Baixo.
- **Impacto:** Medio.
- **Prioridade:** P1.

### GAP-05 - Corrigir variavel `EMBEDDING_MODEL`

- **Status:** DONE.
- **Descricao:** alinhar config real com `.env.example`, hoje divergente por `EMBEDDING_EMBEDDING_MODEL`.
- **Onde:** `src/core/config.py`, `src/.env.example`, testes.
- **Como:** ler `EMBEDDING_MODEL` como fonte primaria e manter fallback legado se necessario.
- **Dependencia:** nenhuma.
- **Criterio de pronto:** teste prova que `EMBEDDING_MODEL` altera o modelo efetivo.
- **Evidencia:** `docs/04_audit/2026-04-29-gap05-embedding-model.md`; `pytest -q src/tests/test_config_embedding_model.py` -> `3 passed`; `pytest -q -rs src/tests` -> `241 passed, 15 skipped`.
- **Risco:** Medio.
- **Impacto:** Medio.
- **Prioridade:** P1.

## P1 - Hardening de seguranca operacional

### GAP-06 - Testar CORS permitido e negado por ambiente

- **Status:** DONE.
- **Descricao:** sair de teste apenas para origem Playwright e validar politica negativa.
- **Onde:** `src/tests/test_cors_security.py`, `src/core/config.py`, docs.
- **Como:** adicionar teste para origem permitida e origem nao permitida.
- **Dependencia:** politica de ambiente definida.
- **Criterio de pronto:** preflight de origem nao permitida nao retorna permissao CORS.
- **Evidencia:** `docs/04_audit/2026-04-29-gap06-gap07-cors-cookies.md`; `pytest -q src/tests/test_cors_security.py` -> `7 passed`.
- **Risco:** Medio.
- **Impacto:** Alto.
- **Prioridade:** P1.

### GAP-07 - Verificar atributos de cookie por ambiente

- **Status:** DONE.
- **Descricao:** garantir politica consistente para sessao em dev/smoke/producao.
- **Onde:** `src/services/enterprise_service.py`, testes auth/session.
- **Como:** testar `HttpOnly`, `SameSite` e `Secure` conforme ambiente.
- **Dependencia:** entendimento da politica atual de `SESSION_COOKIE_SECURE`.
- **Criterio de pronto:** testes automatizados cobrem cookie local e cookie seguro.
- **Evidencia:** `docs/04_audit/2026-04-29-gap06-gap07-cors-cookies.md`; `pytest -q src/tests/test_cors_security.py` -> `7 passed`; `pytest -q -rs src/tests` -> `245 passed, 15 skipped`.
- **Risco:** Medio.
- **Impacto:** Alto.
- **Prioridade:** P1.

### GAP-08 - Avaliar Gitleaks como scanner complementar

- **Status:** DONE.
- **Descricao:** reduzir dependencia exclusiva do scanner regex interno.
- **Onde:** `.github/workflows/ci.yaml`, docs de seguranca.
- **Como:** adicionar etapa informativa ou gate dedicado, conforme ruido inicial.
- **Dependencia:** aceitacao de ferramenta externa no CI.
- **Criterio de pronto:** decisao documentada e, se aprovado, CI executando scanner complementar.
- **Evidencia:** `docs/04_audit/2026-04-29-gap08-gitleaks.md`; `docker run --rm -v "$PWD:/repo" ghcr.io/gitleaks/gitleaks:v8.30.1 dir /repo --config /repo/.gitleaks.toml --redact --no-banner --log-level warn` -> passou.
- **Risco:** Baixo.
- **Impacto:** Medio.
- **Prioridade:** P1.

## P2 - Manutenibilidade e arquitetura

### GAP-09 - Definir plano de extracao de `src/api/main.py`

- **Status:** DONE.
- **Descricao:** quebrar o arquivo de 2230 linhas em routers menores sem mudar contrato publico.
- **Onde:** `src/api/main.py`, `src/api/`.
- **Como:** mapear dominios de rota e escolher primeiro corte de menor risco.
- **Dependencia:** gates verdes antes da refatoracao.
- **Criterio de pronto:** plano tecnico indica ordem, arquivos alvo e testes por corte.
- **Evidencia:** `docs/04_audit/2026-04-30-gap09-gap10-health-router.md`.
- **Risco:** Medio.
- **Impacto:** Alto.
- **Prioridade:** P2.

### GAP-10 - Extrair primeiro router dedicado

- **Status:** DONE.
- **Descricao:** executar primeiro corte de desacoplamento.
- **Onde:** preferencialmente `src/api/observability_routes.py`, `src/api/auth_routes.py` ou router admin wrapper, conforme analise.
- **Como:** mover endpoints mantendo schemas, dependencias e contratos.
- **Dependencia:** GAP-09.
- **Criterio de pronto:** suite backend e Playwright passam sem regressao; `main.py` reduz responsabilidade.
- **Evidencia:** `src/api/health_routes.py`; `pytest -q -rs src/tests` -> `245 passed, 15 skipped`; `npm run test:smoke` -> `7 passed`.
- **Risco:** Alto.
- **Impacto:** Alto.
- **Prioridade:** P2.

### GAP-11 - Modularizar testes monoliticos gradualmente

- **Status:** DONE.
- **Descricao:** reduzir risco do arquivo `src/tests/test_sprint5.py` com 8530 linhas.
- **Onde:** `src/tests/`.
- **Como:** mover testes por dominio sem alterar cobertura.
- **Dependencia:** estabilidade da suite apos GAP-10.
- **Criterio de pronto:** primeiro grupo extraido roda isolado e na suite completa.
- **Evidencia:** `src/tests/test_admin_runtime_routes.py`; `src/api/admin_runtime_routes.py`; `pytest -q src/tests/test_admin_runtime_routes.py` -> `6 passed`; `pytest -q -rs src/tests` -> `245 passed, 15 skipped`; `npm run test:smoke` em `frontend/` -> `7 passed`.
- **Risco:** Medio.
- **Impacto:** Medio.
- **Prioridade:** P2.

## P3 - Auditoria final e fechamento

### GAP-12 - Executar auditoria final 98-100

- **Status:** DONE.
- **Descricao:** validar todos os gaps fechados e recalcular score.
- **Onde:** `docs/04_audit/`, runtime local, CI se disponivel.
- **Como:** rodar gates completos e gerar relatorio final.
- **Dependencia:** GAP-01 a GAP-11.
- **Criterio de pronto:** relatorio final declara score >= 98/100 com evidencias.
- **Evidencia:** `docs/04_audit/0490_audit_report.md`; `docs/04_audit/2026-04-30-gap12-auditoria-final-98-100.md`; backend Qdrant live `260 passed`; Playwright smoke `7 passed`; score final `100/100`.
- **Risco:** Baixo.
- **Impacto:** Alto.
- **Prioridade:** P3.

## Matriz de Aceite Final

| Gate | Comando/evidencia | Esperado |
|---|---|---|
| Backend completo | `pytest -q -rs src/tests` | sem falhas e sem skips de Qdrant |
| Secret scan | `python3 src/scripts/scan_secrets.py` | passou |
| TypeScript | `npm exec -- tsc --noEmit` | passou |
| Lint | `npm run lint` | passou |
| Build | `npm run build` | passou |
| Smoke E2E | `npm run test:smoke` | `7 passed` ou superior |
| Documentacao | runtime/log/audit/build gate | score reconciliado |
| Arquitetura | diff de `src/api/main.py` | primeiro desacoplamento entregue |
