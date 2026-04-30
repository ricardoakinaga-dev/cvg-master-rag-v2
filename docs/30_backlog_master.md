# BACKLOG MASTER — CVG RAG Enterprise Premium

---

## CICLO ATUAL - FECHAMENTO 98-100 (2026-04-28)

Status final: **COMPLETED** em 2026-04-30, score final `100/100`.

Fonte executiva:
- `docs/EXECUTIVE_PLAN_2026-04-28_GAPS_98_100.md`
- `docs/ROADMAP_2026-04-28_GAPS_98_100.md`
- `docs/BACKLOG_EXECUTIVO_2026-04-28_GAPS_98_100.md`

Objetivo: elevar o score auditado real de 95/100 para 98-100/100 por meio de reconciliacao documental, Qdrant live local, hardening de configuracao/seguranca e primeiro desacoplamento de `src/api/main.py`.

Itens ativos:

| ID | Prioridade | Titulo | Status |
|---|---|---|---|
| GAP-01 | P0 | Reconciliar score canonico do programa | DONE |
| GAP-02 | P0 | Criar relatorio canonico de fechamento residual | DONE |
| GAP-03 | P1 | Rodar suite backend com Qdrant local ativo | DONE |
| GAP-04 | P1 | Documentar comando padrao de Qdrant local | DONE |
| GAP-05 | P1 | Corrigir variavel `EMBEDDING_MODEL` | DONE |
| GAP-06 | P1 | Testar CORS permitido e negado por ambiente | DONE |
| GAP-07 | P1 | Verificar atributos de cookie por ambiente | DONE |
| GAP-08 | P1 | Avaliar Gitleaks como scanner complementar | DONE |
| GAP-09 | P2 | Definir plano de extracao de `src/api/main.py` | DONE |
| GAP-10 | P2 | Extrair primeiro router dedicado | DONE |
| GAP-11 | P2 | Modularizar testes monoliticos gradualmente | DONE |
| GAP-12 | P3 | Executar auditoria final 98-100 | DONE |

---

## P0 — CRÍTICO (Foundation — Execução Imediata)

### ITEM 1
- **título:** Executar Sprint 0.1 — Auth Module Básico
- **descrição:** Session storage, login endpoint, logout endpoint, session validation
- **módulo:** Auth
- **dependência:** Nenhuma
- **fase:** Phase 0
- **risco:** Baixo
- **impacto:** Alto

### ITEM 2
- **título:** Executar Sprint 0.2 — Session Persistence
- **descrição:** Session expiry, refresh, configurable timeout
- **módulo:** Auth
- **dependência:** Sprint 0.1
- **fase:** Phase 0
- **risco:** Baixo
- **impacto:** Alto

### ITEM 3
- **título:** Executar Sprint 0.3 — RBAC Middleware
- **descrição:** Role definitions, RBAC decorator, protected endpoints, audit log
- **módulo:** Auth
- **dependência:** Sprint 0.1
- **fase:** Phase 0
- **risco:** Médio
- **impacto:** Alto

### ITEM 4
- **título:** Executar Sprint 0.4 — Telemetry + Health
- **descrição:** Structured logging, request_id middleware, health endpoint
- **módulo:** Telemetry
- **dependência:** Sprint 0.1
- **fase:** Phase 0
- **risco:** Baixo
- **impacto:** Alto

### ITEM 5
- **título:** Executar Sprint 1.1 — Admin CRUD
- **descrição:** Tenant CRUD, User CRUD, persistence
- **módulo:** Admin
- **dependência:** Sprint 0.3
- **fase:** Phase 1
- **risco:** Médio
- **impacto:** Alto

### ITEM 6
- **título:** Executar Sprint 1.2 — Tenant Isolation
- **descrição:** Workspace filter, bootstrap protection
- **módulo:** Admin
- **dependência:** Sprint 1.1
- **fase:** Phase 1
- **risco:** Alto
- **impacto:** Crítico

### ITEM 7
- **título:** Executar Sprint 1.3 — Non-Leakage Suite
- **descrição:** TKT-010 suite, cross-tenant tests
- **módulo:** Admin
- **dependência:** Sprint 1.2
- **fase:** Phase 1
- **risco:** Alto
- **impacto:** Crítico

### ITEM 8
- **título:** Executar Sprint 2.1 — Retrieval Module
- **descrição:** Hybrid search (dense + sparse + RRF)
- **módulo:** Retrieval
- **dependência:** Sprint 0.4
- **fase:** Phase 2
- **risco:** Médio
- **impacto:** Alto

### ITEM 9
- **título:** Executar Sprint 2.2 — Query/RAG Module
- **descrição:** Context assembly, LLM response, citations, groundedness
- **módulo:** Query/RAG
- **dependência:** Sprint 2.1
- **fase:** Phase 2
- **risco:** Médio
- **impacto:** Alto

### ITEM 10
- **título:** Executar Sprint 2.3 — Evaluation Framework
- **descrição:** Dataset, hit rate calculation, evaluation runner
- **módulo:** Evaluation
- **dependência:** Sprint 2.2
- **fase:** Phase 2
- **risco:** Médio
- **impacto:** Alto

---

## P1 — ALTA PRIORIDADE

### ITEM 1
- **título:** Executar Sprint 3.1 — Advanced Tracing
- **descrição:** request_id propagation, spans, cross-module trace
- **módulo:** Telemetry
- **dependência:** Phase 2 completa
- **fase:** Phase 3
- **risco:** Baixo
- **impacto:** Médio

### ITEM 2
- **título:** Executar Sprint 3.2 — SLI/SLO + Alerts
- **descrição:** SLI definitions, SLO targets, alert rules
- **módulo:** Telemetry
- **dependência:** Sprint 3.1
- **fase:** Phase 3
- **risco:** Baixo
- **impacto:** Médio

### ITEM 3
- **título:** Executar Sprint 3.3 — Dashboard
- **descrição:** Dashboard layout, key metrics widgets, trends, tenant filter
- **módulo:** Telemetry
- **dependência:** Sprint 3.2
- **fase:** Phase 3
- **risco:** Baixo
- **impacto:** Médio

### ITEM 4
- **título:** Executar Sprint 4.3 — Final Audit
- **descrição:** Full code audit, gate F3 validation
- **módulo:** All
- **dependência:** Phase 3 completa
- **fase:** Phase 4
- **risco:** Médio
- **impacto:** Alto

---

## P2 — MÉDIA PRIORIDADE

### ITEM 1
- **título:** Executar Sprint 4.1 — TypeScript Checks
- **descrição:** tsc --noEmit, type annotations, CI integration
- **módulo:** Build
- **dependência:** Código completo
- **fase:** Phase 4
- **risco:** Baixo
- **impacto:** Médio

### ITEM 2
- **título:** Executar Sprint 4.2 — Smoke Tests
- **descrição:** Smoke test suite, critical flows, stable execution
- **módulo:** Build
- **dependência:** Sprint 4.1
- **fase:** Phase 4
- **risco:** Baixo
- **impacto:** Médio

---

## P3 — BAIXA PRIORIDADE (Future Scope)

### ITEM 1
- **título:** Cohere Rerank integration
- **descrição:** Reranking premium se hit_rate < 80%
- **módulo:** Retrieval
- **dependência:** RRF working
- **fase:** Future
- **risco:** Baixo
- **impacto:** Baixo

### ITEM 2
- **título:** Supabase Auth SSO
- **descrição:** Enterprise SSO se necessidade real
- **módulo:** Auth
- **dependência:** Current auth working
- **fase:** Future
- **risco:** Baixo
- **impacto:** Baixo

### ITEM 3
- **título:** MinIO/S3 storage
- **descrição:** Object storage para documentos
- **módulo:** Ingestion
- **dependência:** Multi-service need
- **fase:** Future
- **risco:** Baixo
- **impacto:** Baixo

### ITEM 4
- **título:** LangSmith integration
- **descrição:** Evaluation integration
- **módulo:** Evaluation
- **dependência:** Dataset working
- **fase:** Future
- **risco:** Baixo
- **impacto:** Baixo

### ITEM 5
- **título:** MFA para acessos internos sensíveis
- **descrição:** Segundo fator para `super_admin` e operações críticas de governança
- **módulo:** Auth
- **dependência:** Auth access hardening concluído
- **fase:** Future
- **risco:** Médio
- **impacto:** Alto

### ITEM 6
- **título:** SSO corporativo
- **descrição:** Login federado para ambientes enterprise internos
- **módulo:** Auth
- **dependência:** Papéis e sessões estáveis
- **fase:** Future
- **risco:** Médio
- **impacto:** Alto

### ITEM 7
- **título:** Device and session management
- **descrição:** Inventário de dispositivos/sessões, revogação seletiva e visibilidade por usuário
- **módulo:** Auth
- **dependência:** Sessões revogáveis implementadas
- **fase:** Future
- **risco:** Baixo
- **impacto:** Médio

### ITEM 8
- **título:** IP allowlist por perfil
- **descrição:** Restringir `super_admin` e superfícies sensíveis a ranges internos aprovados
- **módulo:** Security
- **dependência:** Telemetria de IP consistente
- **fase:** Future
- **risco:** Médio
- **impacto:** Médio

### ITEM 9
- **título:** Approval workflow para mudanças sensíveis
- **descrição:** Aprovação formal para promoção de privilégio, reset administrativo e config sensível
- **módulo:** Governance
- **dependência:** Trilha de auditoria endurecida
- **fase:** Future
- **risco:** Médio
- **impacto:** Alto

### ITEM 10
- **título:** ABAC incremental
- **descrição:** Evoluir de RBAC puro para políticas por recurso, workspace e origem de dado quando houver necessidade real
- **módulo:** Auth
- **dependência:** RBAC estável e inventário de recursos sensíveis
- **fase:** Future
- **risco:** Médio
- **impacto:** Médio

---

## 📌 REGRAS DE USO

* Backlog deve ser atualizado continuamente
* Novos itens devem ser adicionados imediatamente
* Itens devem ser priorizados corretamente
* Backlog guia execução futura

---

## DÉPITOS TÉCNICOS REGISTRADOS

| ID | Débitos | Severidade | Phase |
|---|---|---|---|
| D1 | Sistema ainda não implementado | 🟠 Alto | ALL |
| D2 | Não há runtime para auditar | 🟠 Alto | AUDIT |
| D3 | Fallback graceful limitado | 🟡 Médio | F2 |
| D4 | Session storage in-memory | 🟡 Médio | F0 |
| D5 | No CI/CD configurado | 🟡 Médio | F4 |
