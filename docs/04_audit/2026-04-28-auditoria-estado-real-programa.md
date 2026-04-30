# 2026-04-28 — Auditoria do Estado Real do Programa

## Escopo

Auditoria solicitada sobre:

- `docs/BACKLOG_EXECUTIVO_2026-04-27.md`
- `docs/ROADMAP_2026-04-27.md`
- estado real do backend, frontend, CI, segurança, documentação e runtime local

Objetivo: reconciliar backlog/roadmap com evidência executável atual e atribuir nota de 0 a 100 para cada item analisado.

## Evidência Executada

| Evidência | Resultado |
|---|---:|
| `pytest -q -rs src/tests` | `238 passed, 15 skipped` |
| `python3 src/scripts/scan_secrets.py` | passou |
| `npm exec -- tsc --noEmit` | passou |
| `npm run lint` | passou |
| `npm run build` | passou |
| `npm run test:smoke` | `7 passed` |

Os 15 skips do backend são todos dependentes de Qdrant local indisponível. O CI contém serviço Qdrant, mas esta auditoria local não executou a trilha live com Qdrant ativo.

## Resultado Consolidado

**Score auditado real:** 95/100

O sistema está funcional e os bloqueadores P0 do backlog executivo foram remediados com evidência de teste. A nota não chega a 98-100 por quatro razões objetivas:

1. Qdrant live não foi validado localmente nesta rodada.
2. Havia divergência documental residual entre auditorias antigas de 79/100, estado que chegou a declarar 98/100 e build gate antigo de 100/100; a nota canônica atual passou a ser `95/100` em `docs/04_audit/2026-04-28-score-canonico.md`.
3. `src/api/main.py` permanece com 2230 linhas, concentrando responsabilidades críticas.
4. `src/core/config.py` lê `EMBEDDING_EMBEDDING_MODEL`, enquanto `src/.env.example` documenta `EMBEDDING_MODEL`.

## Nota por Item do Backlog Executivo

| Item | Nota | Estado real | Justificativa |
|---|---:|---|---|
| BE-01 — Unificar autorização admin/observability | 96 | Resolvido | Rotas sensíveis retornam 403 para permissão insuficiente; há teste de regressão em `src/tests/test_sprint5.py`. |
| BE-02 — Corrigir autorização encapsulada em 500 | 98 | Resolvido | Blocos `except HTTPException: raise` preservam 403 em observability/admin; teste passou. |
| BE-03 — Estabilizar `/queries/logs` | 94 | Resolvido com ressalva | Suíte completa passou sem falha; ressalva fica por dependência local de Qdrant em parte dos testes live. |
| BE-04 — Corrigir upload autenticado no Playwright | 100 | Resolvido | Smoke E2E validou upload autenticado pela UI: `7 passed`, incluindo `documentos executa upload web pela UI`. |
| BE-05 — Remediar divergência de nota documental/evidência | 96 | Resolvido para decisão atual | Nota canônica criada em `docs/04_audit/2026-04-28-score-canonico.md`: score vigente 95/100, meta 98-100, notas antigas preservadas como histórico. |
| BE-06 — Reforçar contratos auth/observability | 94 | Resolvido | Existem contratos para 403, prioridade de cookie e fluxos críticos; cobertura é boa, mas concentrada em arquivo de teste muito grande. |
| BE-07 — Hardening de CORS por ambiente | 84 | Parcial | CORS é configurável e testado para origem Playwright, mas default local contém várias origens e não há teste de política estrita de produção. |
| BE-08 — Reduzir acoplamento `src/api/main.py` | 65 | Aberto | `src/api/main.py` tem 2230 linhas; extração modular ainda não foi feita. |
| BE-09 — Endurecimento de frontend session store | 90 | Majoritariamente resolvido | Frontend usa `credentials: include` e não persiste bearer token; ainda falta verificação automatizada explícita de atributos HttpOnly/SameSite/Secure por ambiente. |
| BE-10 — Higiene de corpus canônico/operacional | 90 | Resolvido com melhoria futura | README e política de migrations existem; inventário operacional ainda pode ser auditado periodicamente para reduzir ruído. |

## Nota por Domínio Auditado

| Domínio | Nota | Leitura objetiva |
|---|---:|---|
| Governança CVG e rastreabilidade | 92 | Pipeline e artefatos existem; divergência histórica de score reduz confiança documental. |
| Aderência ao PRD/SPEC | 96 | PRD/SPEC aprovados e funcionalidades principais têm evidência executável. |
| Backend API e contratos | 97 | `238 passed`; endpoints críticos cobertos. |
| Auth/session | 96 | Login, sessão por cookie, logout, tenant switch e prioridade cookie > bearer estão cobertos. |
| RBAC/admin/observability | 95 | 403 correto em rotas sensíveis; bom controle de acesso. |
| Multi-tenant e não vazamento | 95 | Playwright e testes backend validam troca de tenant e isolamento mínimo. |
| Ingestão, upload e documentos | 97 | Upload autenticado passou no E2E real. |
| Retrieval/RAG/query | 94 | Busca e chat passaram no E2E; live Qdrant local não foi executado. |
| Observabilidade/logs/métricas | 93 | Rotas existem e contratos passam; logs são auditáveis, mas dependem de arquivos locais. |
| Segurança e secrets | 91 | Scanner dedicado passou e CI roda secret scan; scanner é regex-based e exclui `.env` local por desenho. |
| CI/CD e gates | 92 | CI possui secret scan, typecheck, lint, build e Qdrant service; não foi executado remotamente nesta auditoria. |
| Frontend operacional | 96 | Lint/build/smoke passaram; principais telas renderizam. |
| Arquitetura e manutenibilidade | 72 | Acoplamento alto em `main.py` e teste monolítico de 8530 linhas. |
| Configuração e ambientes | 86 | Config é funcional, mas há typo de variável `EMBEDDING_EMBEDDING_MODEL` vs `EMBEDDING_MODEL`. |
| Prontidão enterprise real | 93 | Sistema está operável; faltam hardening final, Qdrant live local e reconciliação documental completa. |

## Achados

### A1 — Bloqueadores P0 do backlog estão fechados

Evidência: backend completo passou; Playwright passou os fluxos de upload, tenant, busca e chat.

Impacto: o rebaixamento anterior de 79/100 não representa mais o estado real atual.

### A2 — Divergência documental residual

Evidência:

- `docs/04_audit/2026-04-27-auditoria-reconsolidada-do-programa.md` declara 79/100.
- `docs/99_runtime_state.md` declara 95/100 como score atual.
- `docs/03_build/0390_build_gate.md` declara 100% apenas como completude histórica do build gate.
- Esta auditoria atribui 95/100 com base na execução de 2026-04-28.
- `docs/04_audit/2026-04-28-score-canonico.md` consolida a regra de interpretação.

Impacto: mitigado para decisões futuras; documentos antigos permanecem históricos e a decisão operacional deve usar a nota canônica.

### A3 — Qdrant live não validado localmente

Evidência: `pytest -q -rs src/tests` teve 15 skips por `Qdrant host port not reachable from sandbox`.

Impacto: não há falha funcional local, mas a trilha live depende de ambiente provisionado.

### A4 — Dívida estrutural em `src/api/main.py`

Evidência: `src/api/main.py` tem 2230 linhas.

Impacto: risco de regressão em auth, admin, observability e query por concentração de responsabilidades.

### A5 — Inconsistência de variável de ambiente de embedding

Evidência: `src/core/config.py` lê `EMBEDDING_EMBEDDING_MODEL`; `src/.env.example` documenta `EMBEDDING_MODEL`.

Impacto: override operacional esperado pode não funcionar, embora o default atual preserve comportamento.

## Plano de Remediação

| Prioridade | Ação | Critério de pronto |
|---|---|---|
| P0 | Reconciliar documentos oficiais de score | `99_runtime_state`, `20_master_execution_log`, build gate e auditorias recentes apontam para o mesmo score atual ou explicam histórico claramente. |
| P1 | Rodar suíte local com Qdrant ativo | `pytest -q -rs src/tests` sem skips live por Qdrant. |
| P1 | Corrigir variável `EMBEDDING_MODEL` | Config aceita `EMBEDDING_MODEL` e mantém compatibilidade com nome legado se necessário. |
| P2 | Extrair rotas de `src/api/main.py` | Admin, auth, documents, query e evaluation separados em routers menores com testes preservados. |
| P2 | Substituir/complementar scanner por Gitleaks | Gate de secrets cobre padrões adicionais sem depender só de regex interna. |
| P2 | Adicionar teste de CORS produção | Teste valida deny/allow por ambiente, não apenas origem local de Playwright. |

## Decisão de Auditoria

**GO condicionado.** O programa está funcional, os fluxos críticos passaram e os itens bloqueadores do backlog executivo estão fechados. A condição é tratar a divergência documental e os hardenings residuais antes de declarar 98-100 como estado real permanente.
