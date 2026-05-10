# BACKLOG MASTER — CVG RAG Enterprise Premium

---

## CICLO ATUAL - RETRIEVAL CHAT QUALITY (2026-05-01)

Status atual: **READY_FOR_NEXT_STEP** — codigo, configuracao, restart e validacao publica final concluidos.

Fonte executiva:
- `docs/03_build/0310_RETRIEVAL_CHAT_QUALITY_FIX.md`

Objetivo: melhorar a qualidade de busca e chat para corpus veterinario bilingue, evitando abstencao indevida em consultas portuguesas sobre conteudo indexado em ingles.

Regra de execucao: cada task deve marcar `Executado: [x]`, registrar evidencia e atualizar `docs/99_runtime_state.md` e `docs/20_master_execution_log.md` antes da proxima task.

Itens ativos:

| ID | Prioridade | Titulo | Status |
|---|---|---|---|
| RQ-001 | P0 | Reproduzir falha com consultas reais em portugues | DONE |
| RQ-002 | P0 | Confirmar corpus e collection Qdrant efetiva | DONE |
| RQ-003 | P0 | Ampliar ponte terminologica portugues-ingles | DONE |
| RQ-004 | P0 | Aplicar ponte no caminho comum de busca | DONE |
| RQ-005 | P0 | Ajustar threshold operacional para score normalizado | DONE |
| RQ-006 | P0 | Ativar reranking BM25F por padrao | DONE |
| RQ-007 | P1 | Versionar defaults persistidos do frontend | DONE |
| RQ-008 | P1 | Atualizar documentacao e registrar evidencias | DONE |
| RQ-009 | P0 | Reiniciar servicos e validar DNS publico | DONE |

---

## CICLO PROPOSTO - INDEXING 400MB CONTROLLED RELEASE (2026-05-01)

Status atual: **COMPLETED** — ciclo 400MB aprovado para liberacao permanente controlada: canarios `100MiB`, `250MiB`, arquivo real de aproximadamente `250MB`, canario final `391,5MiB` (`410.562.000 bytes`), heartbeat/status leve, gatilhos futuros de shards JSONL e auditoria final sem gaps criticos/importantes.

Fonte executiva:
- `docs/INDEXING_400MB_CONTROLLED_INGESTION_ANALYSIS.md`
- `docs/02_spec/0122_indexing_400mb_controlled_release_spec.md`
- `docs/03_build/0305_ROADMAP_INDEXING_400MB_CONTROLLED_RELEASE.md`
- `docs/03_build/0306_BACKLOG_INDEXING_400MB_CONTROLLED_RELEASE.md`
- `docs/03_build/INDEXING_400MB_SPRINTS/`

Objetivo: liberar indexacao sob demanda do arquivo alvo de `410.562.000 bytes` (`391,54 MiB`) usando limite seguro `MAX_UPLOAD_BYTES=524288000` (`500 MiB`), com preflight, concorrencia controlada, timeout, cgroup e canarios progressivos.

Regra de execucao: cada task do ciclo I400 deve marcar `Executado: [x]`, registrar evidencia e atualizar `docs/99_runtime_state.md` e `docs/20_master_execution_log.md` antes da proxima task.

Itens ativos:

| ID | Prioridade | Titulo | Status |
|---|---|---|---|
| I400-001 | P0 | Definir limite seguro de upload 500MiB | DONE |
| I400-002 | P0 | Implementar preflight de disco/capacidade | DONE |
| I400-003 | P0 | Limitar concorrencia de jobs grandes a 1 | DONE |
| I400-004 | P0 | Configurar timeout finito para job grande | DONE |
| I400-005 | P0 | Executar worker com systemd/cgroup | DONE |
| I400-006 | P1 | Registrar perfil e modo de isolamento no job | DONE |
| I400-007 | P1 | Testar fallback/abort por limite de memoria | DONE |
| I400-008 | P0 | Canary 100MB | DONE |
| I400-009 | P0 | Canary 250MB | DONE |
| I400-009R | P0 | Canary real aproximadamente 250MB | DONE |
| I400-010 | P0 | Canary arquivo real 391,5MiB | DONE |
| I400-011 | P1 | Adicionar heartbeat e alertas operacionais | DONE |
| I400-012 | P2 | Definir gatilho de shards JSONL futuro | DONE |

---

## CICLO PROPOSTO - INDEXING MEMORY RESILIENCE (2026-04-30)

Status atual: **WAITING_HUMAN_APPROVAL** — canario de upload grande passou via endpoint real; limite foi restaurado para `MAX_UPLOAD_BYTES=26214400` e aguarda decisao sobre promocao permanente para `52428800`.

Fonte executiva:
- `docs/INDEXING_MEMORY_REMEDIATION_PLAN.md`
- `docs/02_spec/0121_indexing_memory_resilience_spec.md`
- `docs/03_build/0303_ROADMAP_INDEXING_MEMORY_RESILIENCE.md`
- `docs/03_build/0304_BACKLOG_INDEXING_MEMORY_RESILIENCE.md`
- `docs/03_build/INDEXING_MEMORY_SPRINTS/`

Objetivo: remediar travamentos/OOM na indexacao de livros PDF grandes, reconciliar estado parcial em disco/Qdrant e tornar upload/reindexacao seguros por lotes, worker isolado, commit atomico e cleanup.

Regra de execucao: cada task do ciclo IMR deve marcar `Executado: [x]` no sprint correspondente, registrar evidencia e atualizar `docs/99_runtime_state.md` e `docs/20_master_execution_log.md` antes da proxima task.

Itens ativos:

| ID | Prioridade | Titulo | Status |
|---|---|---|---|
| IMR-001 | P0 | Bloquear nova indexacao grande ate reconciliacao | DONE |
| IMR-002 | P0 | Limpar artefatos parciais e pontos orfaos | DONE |
| IMR-003 | P0 | Definir limites temporarios conservadores | DONE |
| IMR-004 | P0 | Criar extracao PDF por pagina/lote com liberacao de cache | DONE |
| IMR-005 | P0 | Medir memoria por pagina/lote | DONE |
| IMR-006 | P0 | Transformar upload pesado em job | DONE |
| IMR-007 | P0 | Criar worker isolado com limite de memoria | DONE |
| IMR-008 | P1 | Remover caminho PDF inseguro do parser antigo | DONE |
| IMR-009 | P1 | Unificar PDF operacional, canonico e reindex | DONE |
| IMR-010 | P1 | Tornar reindex_corpus batch-safe | DONE |
| IMR-011 | P1 | Tornar reindex_document batch-safe | DONE |
| IMR-012 | P0 | Implementar arquivos temporarios e commit atomico | DONE |
| IMR-013 | P0 | Implementar cleanup por ingestion_id | DONE |
| IMR-014 | P1 | Expor logs/metricas por lote | DONE |
| IMR-015 | P0 | Validar com livro real e falha simulada | DONE |

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

## BACKLOG PRIORITARIO - VETERINARY CLINICAL CHAT RAG v2

| Prioridade | ID | Titulo | Fonte | Status |
|---|---|---|---|---|
| P0 | VCHAT-001..003 | Contrato clinico estruturado e rodape bibliografico | `docs/03_build/0308_BACKLOG_VETERINARY_CLINICAL_CHAT_RAG.md` | PENDING |
| P0 | VCHAT-004..006 | Eval set clinico inicial e baseline | `docs/03_build/0308_BACKLOG_VETERINARY_CLINICAL_CHAT_RAG.md` | PENDING |
| P0 | VCHAT-007..012 | Planner clinico multilíngue, traducao contextual e preservacao de escopo | `docs/03_build/0308_BACKLOG_VETERINARY_CLINICAL_CHAT_RAG.md` | PENDING |
| P0 | VCHAT-013..021 | Fan-out PT/EN, reranking clinico e evidence pack por secao | `docs/03_build/0308_BACKLOG_VETERINARY_CLINICAL_CHAT_RAG.md` | PENDING |
| P0 | VCHAT-022..027 | Resposta professoral e rodape `Referencias bibliograficas` | `docs/03_build/0308_BACKLOG_VETERINARY_CLINICAL_CHAT_RAG.md` | PENDING |
| P0 | VCHAT-028..033 | Grounding por secao, guardrails de escopo e reducao segura | `docs/03_build/0308_BACKLOG_VETERINARY_CLINICAL_CHAT_RAG.md` | PENDING |
| P1 | VCHAT-034..042 | API retrocompativel, frontend clinico, observabilidade e release gate | `docs/03_build/0308_BACKLOG_VETERINARY_CLINICAL_CHAT_RAG.md` | PENDING |
| P0 | VCHAT-HF-003 | Hotfix qualidade resposta gastroenterite: evidencia fraca/OCR cru/secoes planejadas | `docs/03_build/0308_BACKLOG_VETERINARY_CLINICAL_CHAT_RAG.md` | COMPLETED |

Regra especifica: nenhuma task VCHAT pode ser considerada pronta sem atualizar documentacao e log antes da proxima task.

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
