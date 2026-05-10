# 99_runtime_state.md

# RUNTIME STATE — CVG RAG Enterprise Premium

## CONTEXTO
- project: cvg-master-rag
- current_engine: REPO_SYNC
- completion_status: PUSHED_TO_GITHUB_V2

## POSIÇÃO ATUAL
- current_phase: VETERINARY_CLINICAL_CHAT_RAG
- current_task: Publicar estado consolidado do repositorio no GitHub `cvg-master-rag-v2`.

## STATUS
- status: READY_FOR_NEXT_STEP
- maturity: 100%
- score_target: 100/100

## PROGRESSO
- last_completed_action: Remote `origin` atualizado para `https://github.com/ricardoakinaga-dev/cvg-master-rag-v2.git`; commit principal `2ee44ff` criado e enviado para `main` com consolidacao das atualizacoes clinicas/RAG e documentacao operacional.
- next_action: Confirmar no GitHub se o repositorio `cvg-master-rag-v2` esta com branch `main` atualizada e seguir novo ciclo CVG conforme proxima demanda.

## BLOQUEIOS
- blockers: nenhum bloqueio tecnico; push normal aceito sem force.

## DECISÃO HUMANA
- human_decision_required: no
- decision_description: Usuario solicitou git commit e push para o repositorio GitHub v2; executado sem force push e com varredura de segredos antes do commit.

## TIMESTAMP
- last_update: 2026-05-10T19:48:12+00:00

---

## REGRAS DE USO

O agente DEVE:
1. Ler este arquivo antes de qualquer ação
2. Atualizar este arquivo após cada ação executada
3. Nunca encerrar sem atualizar estado

---

## HISTÓRICO DE EXECUÇÃO

| Timestamp | Engine | Phase | Sprint | Action | Status |
|---|---|---|---|---|---|
| 2026-04-19 | SYSTEM | INIT | NONE | Setup inicial | READY_FOR_NEXT_STEP |
| 2026-04-19 | DISCOVERY | COMPLETED | — | Discovery completo | COMPLETED |
| 2026-04-19 | PRD | COMPLETED | — | PRD completo | COMPLETED |
| 2026-04-19 | SPEC | COMPLETED | — | SPEC completa | COMPLETED |
| 2026-04-19 | BUILD | COMPLETED | PHASE 0-4 | Build consolidado | COMPLETED |
| 2026-04-19 | AUDIT | COMPLETED | — | Auditoria formal com fonte normativa 00/01/02 | COMPLETED |
| 2026-04-22 | AUDIT | COMPLETED | P4_FINAL_REAUDIT | Rodada final com gates verdes e score 95/100 | READY_FOR_NEXT_STEP |
| 2026-04-22 | BUILD_FIX | COMPLETED | AUTH_RUNTIME | Correção do login do dashboard com sessão por cookie e limpeza dos conflitos de merge do runtime | COMPLETED |
| 2026-04-22 | AUDIT | COMPLETED | LOCAL_RUNTIME | Runtime local revalidado com backend em 8000 e frontend reciclado na mesma 3010 sem reinstalação | READY_FOR_NEXT_STEP |
| 2026-04-22 | AUDIT | COMPLETED | AUTH_DEBUG | Login local revalidado após restauração da credencial demo do admin e correção do endpoint base do frontend | READY_FOR_NEXT_STEP |
| 2026-04-22 | AUDIT | COMPLETED | AUTH_UI_DEBUG | Login via UI validado em localhost e IP após ajuste de CORS e cookie HTTP do backend local | READY_FOR_NEXT_STEP |
| 2026-04-22 | AUDIT | COMPLETED | QUERY_GUARDRAILS | Query/chat endurecidos contra falso positivo do Qdrant com overlap numérico incidental e abstenção fora de escopo | READY_FOR_NEXT_STEP |
| 2026-04-22 | AUDIT | COMPLETED | ANSWER_QUALITY | Parse/chunking Markdown corrigidos e corpus canônico principal reindexado para melhorar especificidade das respostas | READY_FOR_NEXT_STEP |
| 2026-04-22 | AUDIT | COMPLETED | RETRIEVAL_RUNTIME_DEBUG | Filtro implícito de `catalog_scope` removido, backend local reiniciado com `.env` e sinalização de abstenção alinhada ao payload do chat | READY_FOR_NEXT_STEP |
| 2026-04-22 | AUDIT | COMPLETED | RANKING_SCORE_NORMALIZATION | Normalização do score híbrido eliminou empates artificiais em `1.0` e devolveu gradação útil aos resultados do retrieval | READY_FOR_NEXT_STEP |
| 2026-04-22 | AUDIT | COMPLETED | CLINICAL_ACRONYM_RETRIEVAL | Expansão de siglas clínicas e bloqueio do retry neural removeram chunks de bibliografia/fora de escopo em queries veterinárias abreviadas | READY_FOR_NEXT_STEP |
| 2026-04-27 | AUDIT | COMPLETED | P0_EXECUTION | FECHAMENTO P0 (BE-01 a BE-10): correção de autorização/session/CORS, observability e atualização documental | COMPLETED |
| 2026-04-27 | AUDIT | COMPLETED | SECOND_DEEP_AUDIT | Segunda auditoria profunda com backend 238 passed, frontend lint/build verdes, Playwright 7 passed e CORS Playwright coberto por teste | COMPLETED |
| 2026-04-27 | AUDIT | COMPLETED | DEBT_CLOSEOUT | Débitos finais resolvidos: TestClient warning, secret scan CI, Qdrant live CI, migrations policy e README raiz | COMPLETED |
| 2026-04-28 | AUDIT | COMPLETED | REAL_STATE_RECONCILIATION | Auditoria do estado real com backend 238 passed/15 skipped, secret scan, TypeScript, lint, build e Playwright 7 passed; score auditado 95/100 | COMPLETED |
| 2026-04-28 | BUILD | COMPLETED | GAP_CLOSEOUT_PLANNING | Plano executivo, roadmap e backlog criados para fechamento 98-100 dos gaps residuais | READY_FOR_NEXT_STEP |
| 2026-04-28 | BUILD | COMPLETED | GAP-01_SCORE_RECONCILIATION | Score canonico reconciliado: 95/100 atual, 98-100 meta; build gate 100% classificado como historico | READY_FOR_NEXT_STEP |
| 2026-04-28 | BUILD | COMPLETED | GAP-02_RESIDUAL_CLOSEOUT_REPORT | Relatorio canonico de fechamento residual criado, consolidando gaps e gates para 98-100 | READY_FOR_NEXT_STEP |
| 2026-04-29 | BUILD | COMPLETED | GAP-03_QDRANT_LIVE | Qdrant live local validado em porta isolada 6337; backend `253 passed` sem skips | READY_FOR_NEXT_STEP |
| 2026-04-29 | BUILD | COMPLETED | GAP-04_QDRANT_RUNBOOK | Comando padrao de Qdrant local documentado em README, src/README e runbook de migrations | READY_FOR_NEXT_STEP |
| 2026-04-29 | BUILD | COMPLETED | GAP-05_EMBEDDING_MODEL | `EMBEDDING_MODEL` corrigida como variavel primaria com fallback legado e teste automatizado | READY_FOR_NEXT_STEP |
| 2026-04-29 | BUILD | COMPLETED | GAP-06_GAP-07_CORS_COOKIES | CORS e cookies endurecidos com testes de origem permitida/negada e atributos de sessao por ambiente | READY_FOR_NEXT_STEP |
| 2026-04-29 | BUILD | COMPLETED | GAP-08_GITLEAKS | Gitleaks integrado como scanner complementar ao scanner interno de secrets no CI | READY_FOR_NEXT_STEP |
| 2026-04-30 | AUDIT | COMPLETED | ROADMAP_GAPS_98_100_VERIFICATION | Verificacao do roadmap 98-100 encontrou backend/security/build verdes, mas Playwright smoke `6 passed, 1 failed` | BLOCKED |
| 2026-04-30 | AUDIT | COMPLETED | E2E_SMOKE_STABILIZATION | Playwright smoke estabilizado com build/start em producao; `npm run test:smoke` fechou `7 passed` | READY_FOR_NEXT_STEP |
| 2026-04-30 | BUILD | COMPLETED | GAP-09_GAP-10_HEALTH_ROUTER | Primeiro corte de `src/api/main.py` entregue com `src/api/health_routes.py`; backend `245 passed, 15 skipped` e Playwright `7 passed` | READY_FOR_NEXT_STEP |
| 2026-04-30 | BUILD | COMPLETED | GAP-11_ADMIN_RUNTIME_MODULARIZATION | Runtime admin extraido para router dedicado e testes movidos para `src/tests/test_admin_runtime_routes.py`; backend `245 passed, 15 skipped` e Playwright `7 passed` | READY_FOR_NEXT_STEP |
| 2026-04-30 | AUDIT | COMPLETED | GAP-12_FINAL_98_100 | Auditoria final aprovada com Qdrant live `260 passed`, Playwright `7 passed`, scanners verdes e score `100/100` | COMPLETED |
| 2026-04-30 | REPO_SYNC | REMOTE_UPDATE | GITHUB_PULL | Melhorias remotas baixadas de `origin/main` e aplicadas por fast-forward ate `14bc739`; trabalho local anterior preservado em `stash@{0}` | READY_FOR_NEXT_STEP |
| 2026-04-30 | RUNTIME_DEPLOY | LOCALHOST_EXISTING_PORTS | SERVICE_RECYCLE | Melhorias subidas com rebuild frontend, restart systemd nas portas `8000/3004`, Qdrant existente `6333` reindexado e health backend `healthy` | READY_FOR_NEXT_STEP |
| 2026-04-30 | RUNTIME_DEPLOY | AUTH_UPLOAD_DEBUG | SESSION_TRANSPORT | Erro de autorizacao no upload diagnosticado como sessao nao reenviada pelo navegador; fallback Bearer aplicado no frontend e validado | READY_FOR_NEXT_STEP |
| 2026-04-30 | RUNTIME_DEPLOY | UPLOAD_OOM_DEBUG | STREAM_AND_BATCH | Nova falha de upload diagnosticada como `oom-kill`; upload streaming e indexacao em lotes aplicados e validados com upload `201` | READY_FOR_NEXT_STEP |
| 2026-04-30 | RUNTIME_DEPLOY | CONTROLLED_PDF_INDEXING | PAGE_BATCH_PIPELINE | PDFs operacionais passaram a ser parseados, chunkados e indexados por lotes de paginas sem persistir raw text completo | READY_FOR_NEXT_STEP |
| 2026-04-30 | AUDIT | INDEXING_MEMORY_AUDIT | OBSERVATION_ONLY | Auditoria sem codigo confirmou novo `oom-kill` no upload de livro grande, arquivo de chunks corrompido e pontos orfaos no Qdrant | BLOCKED |
| 2026-04-30 | SPEC | INDEXING_MEMORY_RESILIENCE_PLANNING | PLAN_SPEC_ROADMAP_BACKLOG | Plano, SPEC, roadmap, backlog e sprints IMR criados para remediacao controlada de OOM/travamento PDF | WAITING_HUMAN_APPROVAL |
| 2026-04-30 | BUILD | INDEXING_MEMORY_RESILIENCE | SPRINT_0.1_CONTENCAO_RECONCILIACAO | IMR-001 a IMR-003 concluidas: upload grande bloqueado, artefatos parciais em quarentena, pontos orfaos removidos e limites conservadores aplicados | READY_FOR_NEXT_STEP |
| 2026-04-30 | BUILD | INDEXING_MEMORY_RESILIENCE | SPRINT_1.1_PDF_MEMORY_SAFE | IMR-004 e IMR-005 concluidas: extracao PDF por lote com limpeza de cache e medicao RSS em PDF real | READY_FOR_NEXT_STEP |
| 2026-04-30 | BUILD | INDEXING_MEMORY_RESILIENCE | SPRINT_2.1_WORKER_ISOLADO | IMR-006 e IMR-007 concluidas: upload pesado vira job e worker isolado processa fora do Uvicorn com limite de memoria | READY_FOR_NEXT_STEP |
| 2026-04-30 | BUILD | INDEXING_MEMORY_RESILIENCE | SPRINT_3.1_UNIFICACAO_PDF | IMR-008 e IMR-009 concluidas: parser legado bloqueia PDF e PDF canonico/operacional/reindex usa politica memory-safe | READY_FOR_NEXT_STEP |
| 2026-04-30 | BUILD | INDEXING_MEMORY_RESILIENCE | SPRINT_4.1_REINDEX_BATCH_SAFE | IMR-010 e IMR-011 concluidas: reindex amplo e individual processam chunks/textos/embeddings em batches | READY_FOR_NEXT_STEP |
| 2026-04-30 | BUILD | INDEXING_MEMORY_RESILIENCE | SPRINT_5.1_TRANSACAO_CLEANUP | IMR-012 e IMR-013 concluidas: commit atomico de arquivos e cleanup por ingestion_id em falha de job | READY_FOR_NEXT_STEP |
| 2026-05-01 | BUILD | INDEXING_MEMORY_RESILIENCE | SPRINT_6.1_OBSERVABILIDADE_VALIDACAO | IMR-014 e IMR-015 concluidas: metricas por lote expostas, livro real validado sem OOM e falha simulada limpou Qdrant/temporarios | READY_FOR_NEXT_STEP |
| 2026-05-01 | AUDIT | INDEXING_MEMORY_RESILIENCE_AUDIT | OPERATIONAL_RELEASE_DECISION | Auditoria IMR concluiu `READY_FOR_CONTROLLED_RELEASE`; upload grande segue bloqueado ate aprovacao de canario | WAITING_HUMAN_APPROVAL |
| 2026-05-01 | AUDIT | INDEXING_MEMORY_RESILIENCE_AUDIT | LARGE_UPLOAD_CANARY | Canario via endpoint real concluiu `committed` com 842 paginas, 2919 chunks, RSS pico 159.71 MB e backend healthy; limite restaurado | WAITING_HUMAN_APPROVAL |
| 2026-05-01 | DISCOVERY | LARGE_DOCUMENT_CONTROLLED_INGESTION_DISCOVERY | 400GB_ANALYSIS | Analise concluiu que 400GB exige control plane separado com storage dedicado, cgroups, shards, checkpoints e backpressure | READY_FOR_NEXT_STEP |
| 2026-05-01 | DISCOVERY | INDEXING_400MB_CONTROLLED_RELEASE_DISCOVERY | 400MB_ANALYSIS | Retificacao: alvo real e 400MB; analise recomenda evoluir pipeline atual com cgroup, preflight, timeout, concorrencia 1 e canarios | READY_FOR_NEXT_STEP |
| 2026-05-01 | SPEC/BUILD_PLANNING | INDEXING_400MB_CONTROLLED_RELEASE | PROJECT_DOCS | SPEC 0122, roadmap 0305, backlog 0306 e sprints 7.1-7.4 criados para margem segura 500MiB | READY_FOR_NEXT_STEP |
| 2026-05-01 | BUILD | INDEXING_400MB_CONTROLLED_RELEASE | SPRINT_7.1_GATE_OPERACIONAL_400MB | I400-001 a I400-004 concluidas: upload `500MiB`, preflight de disco/Qdrant, concorrencia grande `1`, timeout `21600s` e backend healthy apos restart | READY_FOR_NEXT_STEP |
| 2026-05-01 | BUILD | INDEXING_400MB_CONTROLLED_RELEASE | SPRINT_7.2_WORKER_CGROUP | I400-005 a I400-007 concluidas: worker grande com `systemd-run`, limites cgroup do perfil `normal`, fallback `rlimit_only`, abort por memoria e backend healthy | READY_FOR_NEXT_STEP |
| 2026-05-01 | BUILD | INDEXING_400MB_CONTROLLED_RELEASE | SPRINT_7.3_CANARY_400MB_PARTIAL | I400-008 e I400-009 concluidas com canarios `100MiB` e `250MiB`; I400-010 bloqueada por ausencia do arquivo real `410562000` bytes | BLOCKED |
| 2026-05-01 | RUNTIME_DEPLOY | PUBLIC_DNS_SSL | MASTER_RAG_CADDY_ROUTE | DNS `www.master.rag.centroveterinarioguarapiranga.com` roteado no Caddy existente para frontend `3004` e API `8000`, certificado Let's Encrypt emitido, login/cookie seguro validados | READY_FOR_NEXT_STEP |
| 2026-05-01 | RUNTIME_DEPLOY | PUBLIC_DNS_SSL | DOCUMENTS_ROUTE_FIX | Corrigida colisao `/documents` API/frontend usando prefixo publico `/api/*`; frontend rebuildado; `/documents` responde HTML 200 e `/api/health` responde healthy | READY_FOR_NEXT_STEP |
| 2026-05-01 | BUILD/RUNTIME_DEPLOY | INDEXING_400MB_CONTROLLED_RELEASE | REAL_250MB_MONITORING_AND_JOB_UI | Canario real `255251193` bytes concluiu `committed`: `2801` paginas, `17761` chunks/pontos, RSS pico `242.71MB`, Qdrant consistente, upload removido e busca filtrada funcionando | READY_FOR_NEXT_STEP |
| 2026-05-01 | BUILD/RUNTIME_VALIDATION | INDEXING_400MB_CONTROLLED_RELEASE | SPRINT_7.3_CANARY_391MIB_STATUS | Job final `410562000` bytes verificado em processamento: `573/3109` paginas, `3683` chunks/pontos, RSS pico `418.52MB`, worker cgroup ativo e sem OOM; API responsiva apos recycle do backend | IN_PROGRESS |
| 2026-05-01 | BUILD/RUNTIME_DIAGNOSIS | INDEXING_400MB_CONTROLLED_RELEASE | SPRINT_7.3_CANARY_391MIB_FAILURE_CHECK | Suposta falha investigada: job nao esta failed, segue `processing` com `2573/3109` paginas e `15578` chunks/pontos; falha percebida causada por timeout/lentidao da API/health sob carga | IN_PROGRESS |
| 2026-05-01 | BUILD/RUNTIME_VALIDATION | INDEXING_400MB_CONTROLLED_RELEASE | SPRINT_7.3_CANARY_391MIB_FINAL | Canario final `410562000` bytes concluiu `committed`: `3109` paginas, `18679` chunks/pontos, RSS pico `418.52MB`, Qdrant consistente, upload removido, `/health=healthy` e busca filtrada funcionando | READY_FOR_NEXT_STEP |
| 2026-05-01 | BUILD/RUNTIME_DEPLOY | INDEXING_400MB_CONTROLLED_RELEASE | SPRINT_7.4_I400_011_HEARTBEAT_STATUS_LEVE | I400-011 concluiu heartbeat/status leve, alertas de job parado/RSS alto, health leve e frontend resiliente a atraso de polling; testes backend/frontend e build passaram | READY_FOR_NEXT_STEP |
| 2026-05-01 | BUILD | INDEXING_400MB_CONTROLLED_RELEASE | SPRINT_7.4_I400_012_JSONL_SHARD_TRIGGER | I400-012 concluiu gatilhos futuros de shards JSONL: `100000` chunks ou arquivo de chunks previsto > `524288000` bytes; ciclo 400MB pronto para decisao operacional | WAITING_HUMAN_APPROVAL |
| 2026-05-01 | AUDIT | INDEXING_400MB_CONTROLLED_RELEASE | FINAL_RELEASE_DECISION | Auditoria final aprovou liberacao permanente controlada de `MAX_UPLOAD_BYTES=524288000`, sem gaps criticos/importantes e com evidencias runtime/Qdrant/canario/testes verdes | COMPLETED |
| 2026-05-01 | BUILD/RUNTIME_FIX | RETRIEVAL_CHAT_QUALITY | RQ-001_RQ-009 | Busca/chat ajustados e validados para corpus veterinario bilingue: threshold `0.25`, BM25F default, ponte portugues-ingles, frontend versionado e health publico verde | READY_FOR_NEXT_STEP |
| 2026-05-01 | BUILD/RUNTIME_FIX | RETRIEVAL_CHAT_QUALITY | RQ-010_HEPATOPATIA_RUNTIME | Query real de hepatopatia em cao corrigida com aliases hepaticos, rejeicao de resposta generica curta, `/api/search` com 8 resultados e `/api/query` grounded/high no DNS publico | READY_FOR_NEXT_STEP |
| 2026-05-02 | SPEC | VETERINARY_CLINICAL_CHAT_RAG | VCHAT_FLOW_SPEC | SPEC 0123 criada para chat clinico v2 com planejador LLM multilíngue, fan-out PT/EN, evidence pack e resposta professoral estruturada | WAITING_HUMAN_APPROVAL |
| 2026-05-02 | SPEC | VETERINARY_CLINICAL_CHAT_RAG | VCHAT_GUARDRAILS_SPEC | SPEC 0123 atualizada com guardrails determinísticos, tradução contextual pre-retrieval e resposta pós-retrieval restrita a referencias bibliograficas recuperadas | WAITING_HUMAN_APPROVAL |
| 2026-05-02 | BUILD_PLANNING | VETERINARY_CLINICAL_CHAT_RAG | VCHAT_ROADMAP_BACKLOG | Roadmap 0307 e backlog 0308 criados com 6 phases, 14 sprints, 42 tasks e rodape bibliografico obrigatorio | READY_FOR_NEXT_STEP |
| 2026-05-02 | BUILD | VETERINARY_CLINICAL_CHAT_RAG | SPRINT_0.1_VCHAT_001 | Contrato `QueryResponse` expandido com campos clinicos v2 opcionais, mantendo `answer` retrocompativel; testes focados passaram | READY_FOR_NEXT_STEP |
| 2026-05-02 | BUILD | VETERINARY_CLINICAL_CHAT_RAG | SPRINT_0.1_VCHAT_002 | Contrato do rodape `Referencias bibliograficas` implementado com referencia estruturada, deduplicacao e formatador markdown; testes focados passaram | READY_FOR_NEXT_STEP |
| 2026-05-02 | BUILD | VETERINARY_CLINICAL_CHAT_RAG | SPRINT_0.1_VCHAT_003 | Testes de contrato sem LLM real adicionados; Sprint 0.1 concluida com `6 passed, 240 deselected` | READY_FOR_NEXT_STEP |
| 2026-05-02 | BUILD | VETERINARY_CLINICAL_CHAT_RAG | SPRINT_0.2_VCHAT_004 | Eval set clinico inicial criado com 7 casos reais e validacao offline `2 passed, 246 deselected` | READY_FOR_NEXT_STEP |
| 2026-05-02 | BUILD | VETERINARY_CLINICAL_CHAT_RAG | SPRINT_0.2_VCHAT_005 | Fixtures esperadas de secoes/referencias/guardrails criadas para 7 casos clinicos; validacao offline `4 passed, 246 deselected` | READY_FOR_NEXT_STEP |
| 2026-05-02 | BUILD | VETERINARY_CLINICAL_CHAT_RAG | SPRINT_0.2_VCHAT_006 | Baseline atual executado contra 7 casos clinicos: `0/7` passou, lacunas de secoes/referencias/guardrails documentadas | READY_FOR_NEXT_STEP |
| 2026-05-02 | BUILD | VETERINARY_CLINICAL_CHAT_RAG | SPRINT_1.1_VCHAT_007 | Planner pre-retrieval JSON deterministico criado sem responder ao usuario, com fallback local, preservacao da query original e variantes PT/EN | READY_FOR_NEXT_STEP |
| 2026-05-02 | BUILD | VETERINARY_CLINICAL_CHAT_RAG | SPRINT_1.1_VCHAT_008 | Validacao forte do plano criada para rejeitar payload LLM incompleto e plano inseguro antes do retrieval | READY_FOR_NEXT_STEP |
| 2026-05-02 | BUILD | VETERINARY_CLINICAL_CHAT_RAG | SPRINT_1.1_VCHAT_009 | Logs seguros/auditaveis do planner criados sem query bruta, com hashes de variantes, request_id, trace_id e warnings | READY_FOR_NEXT_STEP |
| 2026-05-02 | BUILD | VETERINARY_CLINICAL_CHAT_RAG | SPRINT_1.2_VCHAT_010 | Fan-out estruturado original/PT/EN/sinonimos criado com origem, finalidade, deduplicacao e preservacao da pergunta original | READY_FOR_NEXT_STEP |
| 2026-05-02 | BUILD | VETERINARY_CLINICAL_CHAT_RAG | SPRINT_1.2_VCHAT_011 | Guardrail de traducao preserva especie, problema, intencao e contexto temporal/gravidade, bloqueando variante alterada | READY_FOR_NEXT_STEP |
| 2026-05-02 | BUILD | VETERINARY_CLINICAL_CHAT_RAG | SPRINT_1.2_VCHAT_012 | Gate de escopo rejeita fan-out que troca especie/problema ou mantem variante traduzida bloqueada antes do retrieval | READY_FOR_NEXT_STEP |
| 2026-05-02 | BUILD | VETERINARY_CLINICAL_CHAT_RAG | SPRINT_2.1_VCHAT_013 | Retrieval fan-out executa variantes original/PT/EN/sinonimos e anexa `query_variant` aos candidatos sem texto bruto | READY_FOR_NEXT_STEP |
| 2026-05-02 | BUILD | VETERINARY_CLINICAL_CHAT_RAG | SPRINT_2.1_VCHAT_014 | Merge deterministico deduplica candidatos por `chunk_id`, preserva melhor score e acumula origens das variantes | READY_FOR_NEXT_STEP |
| 2026-05-02 | BUILD | VETERINARY_CLINICAL_CHAT_RAG | SPRINT_2.1_VCHAT_015 | Debug administrativo seguro expõe variantes e chunks do fan-out sem query textual ou dados sensiveis | READY_FOR_NEXT_STEP |
| 2026-05-02 | BUILD | VETERINARY_CLINICAL_CHAT_RAG | SPRINT_2.2_VCHAT_016 | Candidatos do fan-out classificados por categoria clinica deterministica antes do reranking/evidence pack | READY_FOR_NEXT_STEP |
| 2026-05-02 | BUILD | VETERINARY_CLINICAL_CHAT_RAG | SPRINT_2.2_VCHAT_017 | Reranking clinico prioriza diversidade de categorias antes de repetir chunks da mesma secao por score | READY_FOR_NEXT_STEP |
| 2026-05-02 | BUILD | VETERINARY_CLINICAL_CHAT_RAG | SPRINT_2.2_VCHAT_018 | Filtro de escopo remove indice, bibliografia isolada e assunto clinico divergente antes do evidence pack | READY_FOR_NEXT_STEP |
| 2026-05-02 | BUILD | VETERINARY_CLINICAL_CHAT_RAG | SPRINT_2.3_VCHAT_019 | Evidence pack categoriza chunks por secao obrigatoria, preserva origem de retrieval e marca secoes sem evidencia | READY_FOR_NEXT_STEP |
| 2026-05-02 | BUILD | VETERINARY_CLINICAL_CHAT_RAG | SPRINT_2.3_VCHAT_020 | Evidence pack normaliza referencias bibliograficas por item/secao/pack e deduplica secoes sustentadas | READY_FOR_NEXT_STEP |
| 2026-05-02 | BUILD | VETERINARY_CLINICAL_CHAT_RAG | SPRINT_2.3_VCHAT_021 | Evidence pack expoe `missing_sections` deterministico antes do gerador de resposta v2 | READY_FOR_NEXT_STEP |
| 2026-05-02 | BUILD | VETERINARY_CLINICAL_CHAT_RAG | SPRINT_3.1_VCHAT_022 | Gerador professoral inicial renderiza todas as secoes obrigatorias usando somente evidence pack | READY_FOR_NEXT_STEP |
| 2026-05-02 | BUILD | VETERINARY_CLINICAL_CHAT_RAG | SPRINT_3.1_VCHAT_023 | Guardrail detecta unsupported claims e reduz resposta ao conteudo sustentado pelo evidence pack | READY_FOR_NEXT_STEP |
| 2026-05-02 | BUILD | VETERINARY_CLINICAL_CHAT_RAG | SPRINT_3.1_VCHAT_024 | Regra de completude marca orientacao parcial quando secoes criticas faltam e evita protocolo completo sem suporte | READY_FOR_NEXT_STEP |
| 2026-05-02 | BUILD | VETERINARY_CLINICAL_CHAT_RAG | SPRINT_3.2_VCHAT_025 | Gerador cria `bibliography_footer` e faz `answer_markdown` terminar com referencias bibliograficas | READY_FOR_NEXT_STEP |
| 2026-05-02 | BUILD | VETERINARY_CLINICAL_CHAT_RAG | SPRINT_3.2_VCHAT_026 | Formatter deduplica referencias e ordena footer pela primeira aparicao dos chunks na resposta | READY_FOR_NEXT_STEP |
| 2026-05-03 | BUILD | VETERINARY_CLINICAL_CHAT_RAG | VCHAT_027_042_RELEASE | Chat clinico v2 concluido com API/contrato/frontend/guardrails/telemetria/eval; `clinical_v2_eval_latest` passou 7/7 | COMPLETED |
| 2026-05-03 | RUNTIME_DEPLOY | VETERINARY_CLINICAL_CHAT_RAG | EXISTING_SERVICES_RECYCLE | Serviços existentes backend/frontend reiniciados sem novas portas; DNS publico `/api/health?light=true` healthy e `/chat` HTTP 200 | COMPLETED |
| 2026-05-03 | BUILD/RUNTIME_FIX | VETERINARY_CLINICAL_CHAT_RAG | HCM_SCOPE_GUARDRAIL_HOTFIX | Cardiomiopatia hipertrofica/HCM reconhecida; chunks genericos/tabelas/especie conflitante bloqueados; no-evidence retorna low/ungrounded | COMPLETED |
| 2026-05-03 | BUILD/RUNTIME_FIX | VETERINARY_CLINICAL_CHAT_RAG | TCE_SCOPE_RESPONSE_HOTFIX | Trauma cranioencefalico/TCE reconhecido; luxacao/atlas/semiologia bloqueados; plano desconhecido abstém; resposta fallback virou sintese extrativa citada | COMPLETED |
| 2026-05-03 | BUILD/RUNTIME_FIX | VETERINARY_CLINICAL_CHAT_RAG | TCE_OPENAI_PRESERVE_HOTFIX | Backend confirmado com OPENAI_API_KEY via systemd; reducao de seguranca preserva resposta LLM citada; endpoint real retornou resposta LLM sem fallback | COMPLETED |
| 2026-05-03 | BUILD/RUNTIME_FIX | VETERINARY_CLINICAL_CHAT_RAG | GASTRO_RESPONSE_QUALITY_HOTFIX | Evidence pack rejeita termos soltos por secao; fallback deterministico renderiza sintese extrativa sem OCR bruto; secoes planejadas evitam cirurgico quando nao aplicavel | COMPLETED |
| 2026-05-03 | BUILD/RUNTIME_DIAGNOSIS | VETERINARY_CLINICAL_CHAT_RAG | CHAT_QUALITY_LOG_ANALYSIS | Diagnostico concluiu que o caso real de corpo estranho linear em gatos falha por lacuna no planner/fan-out e filtro de escopo, nao por ausencia de corpus | READY_FOR_NEXT_STEP |
| 2026-05-03 | BUILD/RUNTIME_FIX | VETERINARY_CLINICAL_CHAT_RAG | LINEAR_FOREIGN_BODY_HOTFIX | Corpo estranho linear em gatos reconhecido no planner; fan-out PT/EN inclui linear/gastrointestinal foreign body, obstruction, enterotomy/gastrotomy/peritonitis; testes focados passaram | READY_FOR_NEXT_STEP |
| 2026-05-03 | BUILD/DOCUMENTATION | VETERINARY_CLINICAL_CHAT_RAG | TRANSLATION_ROUTE_DOC_UPDATE | SPEC/backlog atualizados: portugues deve ser traduzido para ingles antes do retrieval; resposta final deve ser pt-BR; aliases viram legado/fallback, nao rota principal | READY_FOR_NEXT_STEP |
| 2026-05-03 | BUILD | VETERINARY_CLINICAL_CHAT_RAG | VCHAT_TRANSLATION_001 | Rota principal clinical_v2 agora traduz PT->EN antes do retrieval, faz passthrough EN, bloqueia falha de traducao sem busca e mantem resposta final pt-BR | READY_FOR_NEXT_STEP |
| 2026-05-03 | BUILD | VETERINARY_CLINICAL_CHAT_RAG | VCHAT_CORR_001_006 | Correcoes pos-relatorio implementadas: gate PT->EN, clinical_problem obrigatorio, evidence pack ampliado, telemetria segura, Retrieval sanitizado e SPEC limpa | READY_FOR_NEXT_STEP |
| 2026-05-03 | BUILD/RUNTIME_VALIDATION | VETERINARY_CLINICAL_CHAT_RAG | VCHAT_RUNTIME_001_007 | Runtime real validado com OpenAI/Qdrant/API autenticada, telemetria segura e UI Retrieval admin/viewer; ajustes focados aplicados | READY_FOR_NEXT_STEP |
| 2026-05-03 | BUILD | FRONTEND_CONFIG | TSCONFIG_PLAYWRIGHT_TYPES | `frontend/tsconfig.json` corrigido para remover include redundante de tipos gerados `.next-playwright`; TypeScript e build frontend validados | READY_FOR_NEXT_STEP |
| 2026-05-03 | BUILD/RUNTIME_VALIDATION | CHAT_VALIDATION | TEST_AND_CHAT_RERUN | Testes clinicos/frontend e runtime do chat reexecutados; `/query` clinical_v2 PT/EN autenticado e smoke UI focado do chat passaram | READY_FOR_NEXT_STEP |
| 2026-05-04 | RUNTIME_VALIDATION | INDEXING_BOOK_UPLOAD | FOSSUM_WORKER_STATUS_CHECK | Indexacao do livro Fossum confirmada em andamento: job `c1842e86-c5ca-48a7-b541-ab3a25520313` ativo no systemd, `3898/5008` paginas, `7220` chunks/pontos, heartbeat recente, backend `/health?light=true` healthy e frontend `/chat` 200 | IN_PROGRESS |
| 2026-05-04 | RUNTIME_QUERY | RAG_DATABASE | LINEAR_FOREIGN_BODY_CATS_TEST | Consulta RAG sobre corpo estranho linear em gatos executada; `/query clinical_v2` foi conservador sem citacoes, retrieval direto recuperou evidencias do Fossum e Surgery-2nd sobre fisiopatologia, sinais, diagnostico, tratamento e prognostico | READY_FOR_NEXT_STEP |
| 2026-05-04 | RUNTIME_QUERY | RAG_DATABASE | KAREN_TOBIAS_LINEAR_FOREIGN_BODY_CATS | Consulta dirigida no documento Surgery-2nd/Karen Tobias recuperou evidencias sobre frequencia em gatos, ancoragem sublingual/pilorica, plicatura intestinal, diagnostico por imagem, tratamento cirurgico e prognostico | READY_FOR_NEXT_STEP |
| 2026-05-04 | RUNTIME_DIAGNOSIS | RAG_DATABASE | SURGERY_2ND_CHUNK_QUALITY | Diagnostico apontou chunks degradados por extracao PDF multicoluna/tabela/legenda misturada, chunking recursivo sem estrutura semantica e raw text nao persistido | BLOCKED |
| 2026-05-04 | RUNTIME_VALIDATION | INDEXING_BOOK_UPLOAD | FOSSUM_INDEXING_COMPLETION_CHECK | Indexacao Fossum confirmada finalizada: job `committed/completed`, `5008` paginas, `8969` chunks/pontos, arquivos raw/chunks persistidos e unit systemd `inactive` | COMPLETED |
| 2026-05-08 | BUILD/RUNTIME_FIX | VETERINARY_CLINICAL_CHAT_RAG | CHAT_PROFESSOR_OUTPUT_ADJUSTMENT | `rick-professor` inspecionado e seus padroes professorais aplicados ao prompt/gerador clinico e renderizacao markdown do `/chat`; testes gerador, lint e build frontend passaram | READY_FOR_NEXT_STEP |
| 2026-05-08 | BUILD/RUNTIME_FIX | VETERINARY_CLINICAL_CHAT_RAG | CHAT_RICK_PROFESSOR_PIPELINE_ADAPTATION | Fluxo `clinical_v2` adaptado para top-k 12, gate/score por termos obrigatorios, selecao diversificada de chunks e resposta final `direct_answer/therapeutics/exams/monitoring/warnings`; testes clinicos, lint e build passaram | READY_FOR_NEXT_STEP |
| 2026-05-08 | BUILD/RUNTIME_FIX | FRONTEND_RUNTIME | CHAT_PAGE_LOAD_FIX | Frontend recarregado com build atual e login corrigido para redirecionar automaticamente ao `next=/chat`; Playwright headless validou `/chat` autenticado sem erros | READY_FOR_NEXT_STEP |
| 2026-05-08 | BUILD/RUNTIME_FIX | VETERINARY_CLINICAL_CHAT_RAG | RICK_PROFESSOR_LOGIC_PORT_RUNTIME | `PREPROCESSOR`, busca top-k 12, gate, selecao de evidencias e `CLINICAL_AGENT` do `rick-professor` portados; runtime real autenticado confirmou resposta `llm_evidence_pack` | READY_FOR_NEXT_STEP |
| 2026-05-08 | BUILD/RUNTIME_FIX | VETERINARY_CLINICAL_CHAT_RAG | PTBR_TO_ENGLISH_RAG_FLOW | Fluxo obrigatorio pt-BR -> ingles -> RAG -> chunks ingles -> resposta pt-BR reforcado e validado com testes clinicos e runtime real autenticado | READY_FOR_NEXT_STEP |
| 2026-05-08 | BUILD/RUNTIME_FIX | VETERINARY_CLINICAL_CHAT_RAG | RICK_PROFESSOR_PASSTHROUGH_RAG | Filtros locais pos-Qdrant removidos da rota LLM, hits sem classificacao mantidos como evidencias e runtime real retornou high/grounded com 4 citacoes | READY_FOR_NEXT_STEP |
| 2026-05-08 | BUILD/RUNTIME_FIX | EXTERNAL_INTEGRATION | EXTERNAL_CHAT_ENDPOINT | Endpoint `/external/chat` com `X-API-Key` criado, documentado, testado e validado em runtime publico retornando resposta do chat clinico | READY_FOR_NEXT_STEP |
| 2026-05-10 | RUNTIME_QUERY | RAG_DATABASE | MOTHERS_DAY_CANINE_REPRODUCTION | Consulta RAG para material educativo sobre cio e gestacao em cadelas; evidencias recuperadas de Semiologia Veterinaria, Ettinger, Blackwell Five-Minute Consult e Surgery-2nd | READY_FOR_NEXT_STEP |
| 2026-05-10 | REPO_SYNC | GITHUB_PUSH | CVG_MASTER_RAG_V2 | Commit principal `2ee44ff` enviado para `https://github.com/ricardoakinaga-dev/cvg-master-rag-v2.git` na branch `main`; `.runtime/` e logs operacionais ficaram ignorados | READY_FOR_NEXT_STEP |

---

## GATES

| Gate | Arquivo | Status |
|---|---|---|
| DISCOVERY | 0090_discovery_validation.md | APROVADO |
| PRD | 0090_prd_validation.md | APROVADO |
| SPEC | 0190_spec_validation.md | APROVADO |
| BUILD | 0390_build_gate.md | APROVADO |
| AUDIT | docs/04_audit/0490_audit_report.md | 100/100 |

---

## SCORE GERAL

### Score Atual
- current_score: 100/100
- target_score: 100/100
- assessed_score: 100/100

### Gaps Críticos Abertos
- Nenhum gap critico ou importante aberto no ciclo 98-100.

### Próximas Ações
1. Decidir destino de `stash@{0}` (`pre-pull-local-work-2026-04-30`).
2. Operar limite `500MiB` com monitoramento de health leve e heartbeat de jobs.
3. Para qualquer limite acima de `500MiB`, iniciar novo ciclo CVG com shards JSONL.
4. Usar rotas publicas de API sempre sob `https://www.master.rag.centroveterinarioguarapiranga.com/api/*` para evitar colisao com paginas do frontend.
5. Testar consultas reais no chat/busca e registrar exemplos ruins restantes para ajuste fino de ranking/evaluation.
