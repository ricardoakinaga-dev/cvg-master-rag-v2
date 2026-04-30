# PLANO EXECUTIVO - FECHAMENTO 98-100

## Status Final

**COMPLETED em 2026-04-30.** O ciclo fechou com score final `100/100`, registrado em `docs/04_audit/0490_audit_report.md`.

## 1. Objetivo

Elevar o sistema de **95/100 auditado** para uma faixa sustentável de **98-100/100**, sem criar novo escopo funcional. O ciclo existe para fechar os gaps residuais identificados na auditoria real de 2026-04-28:

1. Reconciliacao documental de score.
2. Validacao live local com Qdrant ativo.
3. Hardening de configuracao e seguranca residual.
4. Reducao controlada de acoplamento em `src/api/main.py`.

## 2. Estado de Partida

| Area | Estado atual |
|---|---|
| Score auditado real | 95/100 |
| Backend | `238 passed, 15 skipped` |
| Frontend | TypeScript, lint, build e smoke E2E verdes |
| Smoke Playwright | `7 passed` |
| Bloqueadores funcionais P0 | Nenhum aberto |
| Gaps residuais | Documentacao, Qdrant live local, config embedding, CORS/prod hardening, acoplamento |

## 3. Resultado Esperado

O ciclo sera considerado concluido quando:

- `docs/99_runtime_state.md`, `docs/20_master_execution_log.md`, build gate e auditorias recentes tiverem score reconciliado ou historico claramente explicado.
- `pytest -q -rs src/tests` rodar com Qdrant local ativo sem skips de Qdrant.
- `EMBEDDING_MODEL` funcionar como variavel documentada, preservando compatibilidade com `EMBEDDING_EMBEDDING_MODEL` se necessario.
- Politica CORS tiver separacao clara entre dev/smoke/producao e teste de negacao de origem nao permitida.
- `src/api/main.py` tiver um primeiro corte de extracao de routers sem regressao funcional.
- Gates finais passarem: backend, secret scan, TypeScript, lint, build e Playwright.

## 4. Estrategia de Execucao

### Frente A - Governanca e score

Objetivo: remover ambiguidade executiva.

Escopo:

- Atualizar documentos oficiais para explicitar a linha historica `79 -> 95 -> meta 98`.
- Marcar `98/100` como meta ate a conclusao dos hardenings.
- Criar criterio unico de score atual em runtime state e relatorio final.

### Frente B - Runtime live com Qdrant

Objetivo: eliminar skips locais e validar integracao real de vector store.

Escopo:

- Criar procedimento local padrao para subir Qdrant.
- Rodar suite backend com Qdrant ativo.
- Registrar evidencia dos testes live.
- Ajustar scripts/docs se a execucao local exigir passos manuais fragilizados.

### Frente C - Hardening de configuracao e seguranca

Objetivo: fechar riscos pequenos que impedem score 98-100.

Escopo:

- Corrigir compatibilidade de `EMBEDDING_MODEL`.
- Testar CORS por ambiente, incluindo origem permitida e origem negada.
- Avaliar complemento do scanner interno com ferramenta externa como Gitleaks.
- Verificar atributos de cookie por ambiente (`HttpOnly`, `SameSite`, `Secure`).

### Frente D - Manutenibilidade arquitetural

Objetivo: reduzir risco de regressao sem refatoracao ampla.

Escopo:

- Extrair primeiro conjunto de rotas de `src/api/main.py` para routers dedicados.
- Prioridade de extracao: observability/admin wrappers ou auth/session, conforme menor risco de conflito.
- Preservar contratos publicos e testes existentes.
- Manter refatoracao incremental, com gate verde apos cada corte.

## 5. Ordem Executiva

1. Reconciliar documentacao e score publico.
2. Validar Qdrant live local.
3. Corrigir `EMBEDDING_MODEL` e testes de config.
4. Endurecer CORS/cookies/secret scanning.
5. Executar extracao incremental de routers.
6. Rodar auditoria final e atualizar score.

## 6. Criterios de Nota

| Score | Condicao |
|---:|---|
| 95 | Estado atual auditado, funcional, com gaps residuais claros |
| 96 | Documentacao reconciliada e score historico sem ambiguidade |
| 97 | Qdrant live local validado sem skips de vector store |
| 98 | Config/CORS/cookie hardening concluido com testes |
| 99 | Primeiro corte de desacoplamento de `main.py` e primeiro corte de testes monoliticos concluidos sem regressao |
| 100 | Auditoria final sem gaps residuais relevantes e com todos os gates verdes |

## 7. Riscos e Mitigacoes

| Risco | Impacto | Mitigacao |
|---|---|---|
| Refatoracao de router quebrar auth/session | Alto | Extrair em cortes pequenos e rodar testes focados + suite completa |
| Qdrant local divergir do CI | Medio | Documentar versao da imagem e usar mesma imagem do CI |
| Reconciliacao documental apagar historico | Medio | Preservar documentos antigos como historico e criar nota canonica atual |
| Hardening CORS bloquear smoke/dev | Medio | Separar politica por ambiente e cobrir com teste |
| Scanner externo gerar falso positivo | Baixo | Introduzir como etapa complementar inicialmente informativa |

## 8. Decisao Executiva

**GO para ciclo de fechamento 98-100.**

Nao ha bloqueador funcional P0. O trabalho deve ser tratado como ciclo de hardening, governanca e reducao de risco, com entregas curtas e validacao executavel ao fim de cada sprint.
