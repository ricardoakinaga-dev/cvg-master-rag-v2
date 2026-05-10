# 0308 - Backlog Veterinary Clinical Chat RAG v2

## Controle Operacional
- Fonte da verdade: `docs/02_spec/0123_VETERINARY_CLINICAL_CHAT_RAG_FLOW.md`
- Roadmap: `docs/03_build/0307_ROADMAP_VETERINARY_CLINICAL_CHAT_RAG.md`
- Status inicial: `PENDING`

## Regra Obrigatoria para Agente Executor
Ao concluir qualquer task:
1. marcar a task como `[x] Executado`;
2. registrar entregas reais;
3. atualizar este backlog se houver mudanca de escopo;
4. atualizar `docs/99_runtime_state.md`;
5. adicionar entrada em `docs/20_master_execution_log.md`;
6. somente depois iniciar a proxima task.

## Hotfixes Runtime Pos-Release

## Plano de Validacao Runtime Pos-Correcoes - OpenAI/API/UI

### Objetivo Executivo
Validar fora de mocks que a rota `clinical_v2` corrigida se comporta corretamente com LLM/OpenAI real, endpoint autenticado `/api/query`, telemetria persistida e frontend com restricao/sanitizacao da aba Retrieval.

### Riscos Residuais Enderecados
- comportamento real do LLM/OpenAI ainda nao validado apos os gates PT->EN;
- endpoint autenticado `/api/query` ainda nao reproduzido nesta rodada;
- `_looks_portuguese()` continua heuristico e precisa ser testado com variacoes reais de frase;
- docstring de `search_and_answer_clinical_v2()` ainda menciona fan-out retrieval, apesar da rota principal ser traducao validada;
- UI precisa confirmar diferenca admin/non-admin na aba Retrieval.

### Ordem de Execucao Recomendada
1. **P0 - Validacao runtime autenticada da API**
   - Confirmar backend/frontend ativos e autenticar com usuario disponivel.
   - Executar `/api/query` com `retrieval_profile=clinical_v2` para `me de um protocolo de corpo estranho linear em gatos`.
   - Executar equivalente EN `linear foreign body in cats clinical protocol`.
   - Registrar confidence, grounded, low_confidence, chunks usados, idioma detectado, traducao aplicada e hash EN.
2. **P1 - Variacoes de idioma e caso negativo**
   - Testar pelo menos tres frases PT que exercitem `_looks_portuguese()`: `fale sobre pancreatite felina`, `explique obstrucao intestinal em gatos`, `qual conduta para corpo estranho linear felino`.
   - Simular ou forcar, da forma menos invasiva possivel, uma traducao ruim/incompleta e confirmar que retrieval nao executa.
   - Se simulacao runtime real nao for viavel sem alterar codigo, documentar limite e cobrir com teste automatizado focado.
3. **P2 - Telemetria segura**
   - Inspecionar `src/logs/queries.jsonl` apos as chamadas.
   - Confirmar presenca de `detected_language`, `translation_applied`, `translation_blocked`, `translation_blocked_reason`, `translated_query_hash`.
   - Confirmar ausencia de texto bruto da query traduzida em campos novos.
4. **P3 - Frontend admin/non-admin**
   - Validar no navegador que perfil admin ve payload sanitizado na aba Retrieval.
   - Validar que perfil nao-admin recebe estado restrito e nao ve `clinical_evidence_pack` completo ou textos de chunks.
5. **P4 - Polish documental minimo**
   - Corrigir docstring de `search_and_answer_clinical_v2()` para nao mencionar fan-out como fluxo principal.
   - Atualizar runtime state/log com evidencia real ou, em caso de falha, abrir task corretiva especifica.

### Tasks Executivas Propostas

#### [x] VCHAT-RUNTIME-001 - Validar `/api/query` PT autenticado com OpenAI real
- Status: COMPLETED
- O QUE: executar query real `me de um protocolo de corpo estranho linear em gatos` via endpoint autenticado com `retrieval_profile=clinical_v2`.
- ONDE: runtime backend publico/local, endpoint `/api/query`, logs `src/logs/queries.jsonl`.
- COMO: autenticar, chamar API, capturar payload sanitizado e verificar que entrada PT gerou traducao aplicada, resposta pt-BR e referencias reais.
- DEPENDENCIA: servicos runtime ativos, usuario/sessao valida e `OPENAI_API_KEY` carregada no backend.
- CRITERIO DE PRONTO: resposta nao e low-confidence indevida, tem grounding/referencias quando corpus sustentar e registra telemetria segura.
- EXECUTADO EM: 2026-05-03 15:20 UTC.
- ENTREGAS REAIS: backend reiniciado para carregar codigo atual; query PT autenticada retornou `confidence=medium`, `grounded=true`, `low_confidence=false`, `translation_applied=true`, `translation_blocked=false`, `generated_by=llm_translation`, `chunks_used=1`, `bibliography=1`.
- AJUSTE NECESSARIO: primeiro runtime revelou falso bloqueio `translation_clinical_problem_conflict`; corrigido normalizando rotulo generico do LLM quando a query EN preserva termos do problema original.

#### [x] VCHAT-RUNTIME-002 - Validar `/api/query` EN passthrough autenticado
- Status: COMPLETED
- O QUE: executar `linear foreign body in cats clinical protocol` com `clinical_v2`.
- ONDE: mesmo runtime autenticado de VCHAT-RUNTIME-001.
- COMO: confirmar que entrada EN nao aplica traducao, usa passthrough e ainda responde em pt-BR.
- DEPENDENCIA: VCHAT-RUNTIME-001.
- CRITERIO DE PRONTO: `detected_language=en`, `translation_applied=false`, resposta final pt-BR e retrieval com evidencias coerentes.
- EXECUTADO EM: 2026-05-03 15:20 UTC.
- ENTREGAS REAIS: query EN autenticada retornou `confidence=medium`, `grounded=true`, `low_confidence=false`, `detected_language=en`, `translation_applied=false`, `generated_by=passthrough`, `chunks_used=1`, `bibliography=1`.

#### [x] VCHAT-RUNTIME-003 - Validar variacoes PT da heuristica de idioma
- Status: COMPLETED
- O QUE: testar frases PT menos obvias para reduzir risco de `_looks_portuguese()` falhar em runtime.
- ONDE: `/api/query`, `src/services/clinical_query_planner_service.py`, logs de query.
- COMO: executar `fale sobre pancreatite felina`, `explique obstrucao intestinal em gatos` e `qual conduta para corpo estranho linear felino`; registrar idioma detectado e comportamento.
- DEPENDENCIA: VCHAT-RUNTIME-001.
- CRITERIO DE PRONTO: todas as frases clinicas PT seguem rota de traducao ou, se alguma escapar, cria-se teste regressivo e fix minimo.
- EXECUTADO EM: 2026-05-03 15:20 UTC.
- ENTREGAS REAIS: `fale sobre pancreatite felina` e `explique obstrucao intestinal em gatos` retornaram `medium/grounded`; `qual conduta para corpo estranho linear felino` seguiu rota PT->EN com `translation_applied=true` e sem bloqueio, mas ficou `low_confidence` por ausencia de resultados no corpus/ranking atual.
- AJUSTE NECESSARIO: runtime expos falso bloqueio por rotulo de intencao; gate passou a nao bloquear apenas por `intent` quando problema/especie e termos originais estao preservados na query EN.

#### [x] VCHAT-RUNTIME-004 - Confirmar bloqueio de traducao ruim antes do retrieval
- Status: COMPLETED
- O QUE: validar que traducao alterada/incompleta nao chama retrieval.
- ONDE: teste automatizado focado ou harness runtime controlado.
- COMO: preferir simulacao controlada do LLM/translation payload; confirmar `translation_blocked=true`, motivo preenchido e nenhuma chamada a `search_hybrid`.
- DEPENDENCIA: VCHAT-CORR-001 e VCHAT-CORR-002.
- CRITERIO DE PRONTO: evidencia objetiva de bloqueio antes do retrieval; se runtime real nao permitir simular LLM ruim, registrar limitacao e manter teste automatizado como gate.
- EXECUTADO EM: 2026-05-03 15:20 UTC.
- ENTREGAS REAIS: caso negativo controlado validado por testes automatizados porque nao ha mecanismo seguro para forcar payload ruim do provedor real sem alterar runtime.
- VERIFICACAO: `pytest -k "species_problem_or_intent_drift or missing_clinical_problem_for_portuguese or retrieval_blocks_portuguese_when_translation_missing_problem"` -> `3 passed`.

#### [x] VCHAT-RUNTIME-005 - Auditar telemetria segura em `queries.jsonl`
- Status: COMPLETED
- O QUE: confirmar persistencia dos campos de traducao sem vazamento de query EN bruta.
- ONDE: `src/logs/queries.jsonl`.
- COMO: inspecionar ultimas entradas das queries PT/EN/blocked e verificar campos esperados.
- DEPENDENCIA: VCHAT-RUNTIME-001 a VCHAT-RUNTIME-004.
- CRITERIO DE PRONTO: campos existem, hash existe quando aplicavel, motivo de bloqueio existe quando aplicavel e nao ha campo novo com texto traduzido bruto.
- EXECUTADO EM: 2026-05-03 15:20 UTC.
- ENTREGAS REAIS: `queries.jsonl` passou a persistir `detected_language`, `translation_applied`, `translation_blocked`, `translation_blocked_reason`, `translated_query_hash`; auditoria confirmou ausencia de campos `translated_query` e `retrieval_query`.
- AJUSTE NECESSARIO: runtime mostrou que os campos existiam no payload, mas nao eram repassados por `TelemetryService.log_query()`; assinatura/evento corrigidos e backend reiniciado.

#### [x] VCHAT-RUNTIME-006 - Validar aba Retrieval admin/non-admin
- Status: COMPLETED
- O QUE: confirmar comportamento visual/autorizacao da aba Retrieval.
- ONDE: frontend `/chat`.
- COMO: usar browser/Playwright com sessao admin e nao-admin; admin deve ver payload sanitizado, nao-admin deve ver `Debug restrito`.
- DEPENDENCIA: frontend ativo e usuarios/perfis disponiveis.
- CRITERIO DE PRONTO: nenhum texto integral de chunk/evidence pack aparece para nao-admin; admin ve apenas resumo sanitizado.
- EXECUTADO EM: 2026-05-03 15:20 UTC.
- ENTREGAS REAIS: frontend rebuildado/reiniciado; Playwright confirmou admin sem `Debug restrito`, com contagens sanitizadas e sem texto integral; viewer com `Debug restrito` e sem evidence pack/chunk bruto.

#### [x] VCHAT-RUNTIME-007 - Polish docstring e fechamento documental
- Status: COMPLETED
- O QUE: corrigir docstring residual de `search_and_answer_clinical_v2()` e atualizar estado/log.
- ONDE: `src/services/search_service.py`, `docs/99_runtime_state.md`, `docs/20_master_execution_log.md`.
- COMO: trocar mencao a fan-out por `translation-gated retrieval`; registrar evidencias de validacao ou abrir task corretiva se falhar.
- DEPENDENCIA: VCHAT-RUNTIME-001 a VCHAT-RUNTIME-006.
- CRITERIO DE PRONTO: documentacao/codigo nao induz entendimento errado e runtime state aponta proximo passo real.
- EXECUTADO EM: 2026-05-03 15:20 UTC.
- ENTREGAS REAIS: docstring de `search_and_answer_clinical_v2()` corrigida para `translation-gated retrieval`; backlog, runtime state e log atualizados.
- VERIFICACAO FINAL: `pytest -k "clinical"` -> `74 passed`; `py_compile` dos modulos alterados passou; `npm run lint` passou.

## Plano Corretivo Pos-Relatorio - Translation Scope Gate

### Objetivo Executivo
Fechar os riscos reabertos pela rota unica `PT -> EN -> retrieval -> pt-BR`, priorizando o gate de preservacao de escopo antes do retrieval. O criterio executivo e impedir que uma traducao incorreta consulte a base errada com aparencia de resposta correta.

### Ordem de Execucao Recomendada
1. **P0 - Gate de traducao e escopo antes do retrieval**
   - Bloquear traducao que altere especie, problema clinico ou intencao.
   - Tornar `clinical_problem` obrigatorio para pergunta clinica em portugues.
   - Adicionar testes negativos para especie/problema/intencao alterados.
2. **P1 - Evidence pack e fallback preparados para a nova rota**
   - Ampliar classificadores por secao para termos de obstrucao, corpo estranho linear, enterotomy, gastrotomy, peritonitis e cirurgia abdominal.
   - Garantir resposta parcial boa quando o corpus recupera evidencias certas, mas nem todas as secoes estao completas.
3. **P2 - Observabilidade e superficie segura**
   - Persistir telemetria segura de traducao: idioma, aplicacao/bloqueio, motivo e hash da query EN.
   - Restringir a aba Retrieval a debug/admin ou payload sanitizado.
4. **P3 - Alinhamento documental**
   - Remover contradicoes da SPEC sobre fan-out/aliases como fluxo principal.
   - Registrar aliases/fan-out apenas como legado/fallback, nao como arquitetura alvo.

### Tasks Executivas Propostas

#### [x] VCHAT-CORR-001 - Gate forte de preservacao PT->EN antes do retrieval
- Status: COMPLETED
- Severidade enderecada: Alto.
- O QUE: validar que a traducao preserva especie, problema clinico, intencao e contexto clinico minimo antes de chamar retrieval.
- ONDE: `src/services/clinical_query_planner_service.py`, testes em `src/tests/test_sprint5.py`.
- COMO: comparar sinais extraidos da pergunta original com payload LLM e query EN; bloquear conflitos de especie, troca de problema ou mudanca de intencao; exigir termos clinicos minimos quando `clinical_problem` existir.
- DEPENDENCIA: `VCHAT-TRANSLATION-001`.
- CRITERIO DE PRONTO: testes negativos bloqueiam traducao que converte gato em dog, altera corpo estranho para outro problema ou muda pedido de conduta/prognostico; retrieval nao executa quando o gate falha.
- EXECUTADO EM: 2026-05-03 05:18 UTC.
- ENTREGAS REAIS: `prepare_clinical_retrieval_query()` passou a bloquear conflito de especie, problema clinico, intencao e traducao sem termos minimos do problema antes de expor `retrieval_query`.
- VERIFICACAO: teste regressivo `test_clinical_retrieval_query_preparation_blocks_species_problem_or_intent_drift` passou.

#### [x] VCHAT-CORR-002 - `clinical_problem` obrigatorio em pergunta clinica PT
- Status: COMPLETED
- Severidade enderecada: Alto.
- O QUE: impedir que pergunta clinica em portugues siga para filtro frouxo quando o LLM nao retorna problema clinico.
- ONDE: `src/services/search_service.py`, `src/services/clinical_query_planner_service.py`, testes em `src/tests/test_sprint5.py`.
- COMO: retornar `low_confidence` com motivo `translation_missing_clinical_problem` para pergunta clinica PT sem `clinical_problem`; ajustar `_missing_expected_clinical_problem_signal()` para nao aceitar candidatos genericos nessa rota.
- DEPENDENCIA: VCHAT-CORR-001.
- CRITERIO DE PRONTO: pergunta clinica PT sem problema identificado nao gera retrieval clinico generico nem resposta sustentada por chunks de outro assunto.
- EXECUTADO EM: 2026-05-03 05:18 UTC.
- ENTREGAS REAIS: pergunta em portugues sem `clinical_problem` retorna bloqueio `translation_missing_clinical_problem`; rota clinical_v2 nao chama `search_hybrid` nesse caso.
- VERIFICACAO: testes `test_clinical_retrieval_query_preparation_blocks_missing_clinical_problem_for_portuguese` e `test_clinical_v2_retrieval_blocks_portuguese_when_translation_missing_problem` passaram.

#### [x] VCHAT-CORR-003 - Classificadores clinicos compatíveis com obstrucao/corpo estranho/cirurgia abdominal
- Status: COMPLETED
- Severidade enderecada: Alto.
- O QUE: ampliar classificacao de secoes e fallback para problemas recuperados pela nova rota em ingles.
- ONDE: `src/services/clinical_evidence_pack_service.py`, `src/services/clinical_response_generator_service.py`, testes/evals clinicos.
- COMO: adicionar termos de `linear foreign body`, `intestinal obstruction`, `enterotomy`, `gastrotomy`, `peritonitis`, sinais, exames e tratamento cirurgico; preferir categorias genericas reutilizaveis em vez de listas por doenca.
- DEPENDENCIA: VCHAT-CORR-001.
- CRITERIO DE PRONTO: caso de corpo estranho linear em gatos gera evidence pack com secoes úteis e fallback extrativo estruturado quando LLM nao estiver disponivel.
- EXECUTADO EM: 2026-05-03 05:18 UTC.
- ENTREGAS REAIS: classificadores de candidate/evidence pack e fallback extrativo ampliados para `linear foreign body`, `gastrointestinal foreign body`, `intestinal obstruction`, `enterotomy`, `gastrotomy`, `peritonitis`, estabilizacao e cirurgia abdominal.
- VERIFICACAO: teste `test_clinical_evidence_pack_classifies_linear_foreign_body_sections` passou; fatia clinica completa `70 passed`.

#### [x] VCHAT-CORR-004 - Telemetria segura persistida da traducao
- Status: COMPLETED
- Severidade enderecada: Medio.
- O QUE: tornar auditavel se a falha ocorreu na deteccao de idioma, traducao, bloqueio, retrieval ou geracao.
- ONDE: `src/services/search_service.py`, telemetria/log JSONL existente.
- COMO: registrar `detected_language`, `translation_applied`, `translation_blocked`, `translation_blocked_reason` e hash da query EN, sem texto bruto.
- DEPENDENCIA: VCHAT-CORR-001.
- CRITERIO DE PRONTO: cada request `clinical_v2` com traducao possui evento auditavel sem expor query completa ou dados sensiveis.
- EXECUTADO EM: 2026-05-03 05:18 UTC.
- ENTREGAS REAIS: `clinical_fanout` e `_log_query()` passam a registrar `detected_language`, `translation_applied`, `translation_blocked`, `translation_blocked_reason` e `translated_query_hash`, sem persistir texto traduzido.
- VERIFICACAO: teste `test_search_and_answer_clinical_v2_logs_safe_translation_telemetry` passou.

#### [x] VCHAT-CORR-005 - Retrieval debug seguro no frontend
- Status: COMPLETED
- Severidade enderecada: Medio.
- O QUE: reduzir exposicao de chunks, evidence pack e debug interno na aba Retrieval.
- ONDE: `frontend/app/chat/page.tsx`.
- COMO: esconder aba por padrao em ambiente nao-admin ou renderizar payload sanitizado com contagens, scores e flags, sem textos integrais dos chunks.
- DEPENDENCIA: definicao de perfil admin/debug no runtime atual.
- CRITERIO DE PRONTO: usuario final nao ve textos integrais de chunks nem campos internos sensiveis; operador/admin ainda consegue diagnostico suficiente.
- EXECUTADO EM: 2026-05-03 05:18 UTC.
- ENTREGAS REAIS: aba Retrieval do chat agora exige perfil `super_admin`, `admin_rag` ou `admin`; mesmo para admin renderiza payload sanitizado com contagens, flags, hashes e resumos, sem textos integrais de chunks/evidence pack.
- VERIFICACAO: `npm run lint` no frontend passou.

#### [x] VCHAT-CORR-006 - Limpeza da SPEC 0123 apos rota unica PT->EN
- Status: COMPLETED
- Severidade enderecada: Medio.
- O QUE: remover contradicoes entre rota unica de traducao e trechos antigos de fan-out/aliases.
- ONDE: `docs/02_spec/0123_VETERINARY_CLINICAL_CHAT_RAG_FLOW.md`.
- COMO: consolidar fluxo principal como `entrada PT -> query EN validada -> retrieval -> resposta pt-BR`; mover fan-out/aliases para secao de legado/fallback, se ainda existir.
- DEPENDENCIA: decisao executiva de manter rota unica.
- CRITERIO DE PRONTO: proximo agente nao encontra instrucao conflitante que incentive reimplementar fan-out/aliases como caminho principal.
- EXECUTADO EM: 2026-05-03 05:18 UTC.
- ENTREGAS REAIS: SPEC 0123 consolidada com rota principal `PT -> EN validado -> retrieval -> pt-BR`; fan-out/aliases documentados como legado/fallback.
- VERIFICACAO: revisao textual por `rg` confirmou remocao dos trechos conflitantes principais.

#### [x] VCHAT-TRANSLATION-001 - Simplificar rota clinica para traducao EN antes do retrieval
- Status: COMPLETED
- O QUE: ajustar o `clinical_v2` para traduzir a pergunta para ingles quando a entrada estiver em portugues, usar essa query no retrieval e gerar a resposta final em portugues brasileiro.
- ONDE: `src/services/clinical_query_planner_service.py`, `src/services/search_service.py`, `src/services/clinical_response_generator_service.py`, `src/tests/test_sprint5.py`.
- COMO: criar etapa explicita de preparacao da query de retrieval; se idioma for portugues, usar LLM com temperatura 0 para traducao clinica fiel para ingles; se ja for ingles, usar a query original; tratar aliases determinísticos por problema clinico como legado/fallback transitorio, nao como rota principal.
- DEPENDENCIA: `clinical_v2` funcional e SPEC 0123 atualizada com a correcao de direcao 2026-05-03.
- CRITERIO DE PRONTO: query em portugues consulta o vector DB com texto em ingles; query em ingles nao chama traducao; resposta final sempre sai em portugues brasileiro; falha de traducao retorna baixa confianca/erro controlado sem inventar aliases; testes regressivos passam.
- AGENTE EXECUTOR: implementar com TDD, validar, atualizar runtime state/log/backlog antes de encerrar.
- EXECUTADO EM: 2026-05-03 05:02 UTC.
- ENTREGAS REAIS: criado `prepare_clinical_retrieval_query()` com traducao LLM PT->EN e passthrough EN; `execute_clinical_fanout_search()` usa a rota de traducao quando `use_llm=True`; falha de traducao bloqueia retrieval com `low_confidence`; caminho deterministico antigo permanece apenas para `use_llm=False`; prompt final exige portugues brasileiro.
- VERIFICACAO: testes TDD da rota de traducao `5 passed`; fatia ampla `clinical_query_planner/clinical_fanout/clinical_scope_filter/search_and_answer_clinical_v2` `25 passed`; fatia clinica completa `65 passed`; `py_compile` dos arquivos alterados passou.

#### [x] VCHAT-DOC-TRANSLATION-000 - Registrar correcao de direcao PT->EN->pt-BR
- Status: COMPLETED
- O QUE: documentar que o fluxo principal nao deve crescer por aliases manuais; portugues deve ser traduzido para ingles antes do retrieval e a resposta final deve ser pt-BR.
- ONDE: `docs/02_spec/0123_VETERINARY_CLINICAL_CHAT_RAG_FLOW.md`, `docs/03_build/0308_BACKLOG_VETERINARY_CLINICAL_CHAT_RAG.md`, `docs/99_runtime_state.md`, `docs/20_master_execution_log.md`.
- COMO: atualizar SPEC, backlog, runtime state e log mestre antes de continuar implementacao.
- DEPENDENCIA: decisao humana registrada em conversa.
- CRITERIO DE PRONTO: documentacao explicita a nova regra de idioma e cria task de implementacao sem iniciar codigo.
- EXECUTADO EM: 2026-05-03 04:57 UTC.
- ENTREGAS REAIS: SPEC 0123 corrigida para rota `entrada PT -> query EN -> retrieval -> resposta pt-BR`; backlog recebeu task `VCHAT-TRANSLATION-001` como proximo item elegivel.

#### [x] VCHAT-HOTFIX-TCE-001 - Bloquear falso positivo em trauma cranioencefalico
- Status: COMPLETED
- O QUE: corrigir resposta real que usava luxacao de quadril, atlas/axis e semiologia generica como evidencia de protocolo para TCE.
- ONDE: `src/services/clinical_query_planner_service.py`, `src/services/search_service.py`, `src/services/clinical_response_generator_service.py`, `src/tests/test_sprint5.py`.
- COMO: adicionar regra deterministica TCE, conflitos de escopo, abstencao para plano sem problema clinico, rota LLM citada com fallback e sintese extrativa do evidence pack.
- DEPENDENCIA: release `clinical_v2`.
- CRITERIO DE PRONTO: consulta TCE nao retorna chunks antigos fora de escopo; testes clinicos passam; backend existente reiniciado e health publico healthy.
- AGENTE EXECUTOR: corrigir bug, testar, atualizar runtime state/log/backlog antes de encerrar.
- EXECUTADO EM: 2026-05-03 01:41 UTC.
- ENTREGAS REAIS: planner reconhece `trauma cranioencefalico`; filtro bloqueia luxacao/atlas/semiologia; plano clinico desconhecido retorna low-confidence sem resposta generica; gerador usa LLM com citacao obrigatoria quando disponivel e fallback extrativo sem OCR bruto.
- VERIFICACAO: `54 passed, 242 deselected` na fatia clinica; py_compile e diff check passaram; backend/frontend/Caddy ativos; `/api/health?light=true` publico healthy.

#### [x] VCHAT-HOTFIX-TCE-002 - Preservar resposta LLM citada
- Status: COMPLETED
- O QUE: corrigir reducao indevida da resposta LLM para fallback extrativo apesar de `OPENAI_API_KEY` estar carregada no backend.
- ONDE: `src/services/clinical_response_generator_service.py`, `src/tests/test_sprint5.py`.
- COMO: quando `generated_by == llm_evidence_pack`, validar por citacoes `chunk_id` com `verify_clinical_answer_citations()` em vez de exigir correspondencia literal do texto sintetizado.
- DEPENDENCIA: VCHAT-HOTFIX-TCE-001.
- CRITERIO DE PRONTO: endpoint real `/query` retorna resposta sintetizada por LLM quando citacoes sao validas.
- AGENTE EXECUTOR: corrigir bug, testar, reiniciar backend existente e atualizar documentacao antes de encerrar.
- EXECUTADO EM: 2026-05-03 01:53 UTC.
- ENTREGAS REAIS: backend confirmado com `OPENAI_API_KEY` via `EnvironmentFile`; resposta LLM citada preservada; fallback fica reservado para saida sem citacao valida ou falha real de LLM.
- VERIFICACAO: `55 passed, 242 deselected` na fatia clinica; endpoint real autenticado `/query` retornou resposta LLM para TCE com `fallback_marker=False`.

## Phase 0 - Contratos, Guardrails e Baseline

### Sprint 0.1 - Contrato Clinico e Rodape Bibliografico

#### [x] VCHAT-001 - Definir contrato de resposta clinica estruturada
- Status: COMPLETED
- O QUE: criar/ajustar modelos de dados para resposta clinica com `sections`, `missing_sections`, `guardrails`, `citations` e `bibliography_footer`.
- ONDE: camada de schemas/API e documentacao de contrato.
- COMO: preservar `answer` para compatibilidade e adicionar campos v2 de forma incremental.
- DEPENDENCIA: SPEC 0123 aprovada.
- CRITERIO DE PRONTO: contrato permite resposta estruturada sem quebrar consumidores atuais.
- ENTREGA: schema documentado e testavel.
- AGENTE EXECUTOR: implementar contrato, adicionar testes unitarios e atualizar documentacao antes da proxima task.
- EXECUTADO EM: 2026-05-02 00:53 UTC.
- ENTREGAS REAIS: `QueryResponse` agora aceita `sections`, `bibliography_footer`, `missing_sections` e `guardrails` como campos opcionais v2; payload legado com `answer` continua valido.
- VERIFICACAO: `py_compile` passou; testes focados `2 passed, 240 deselected`; backend reiniciado no servico existente e `/api/health?light=true` publico retornou `healthy`.

#### [x] VCHAT-002 - Definir contrato do rodape `Referencias bibliograficas`
- Status: COMPLETED
- O QUE: especificar formato do rodape bibliografico no markdown final.
- ONDE: gerador de resposta, schemas e frontend.
- COMO: deduplicar por `document_filename`, `page`, `chunk_id` e listar secoes sustentadas.
- DEPENDENCIA: VCHAT-001.
- CRITERIO DE PRONTO: toda resposta clinica v2 tem rodape com referencias reais recuperadas.
- ENTREGA: contrato `bibliography_footer`.
- AGENTE EXECUTOR: implementar regra de formato e atualizar documentacao antes da proxima task.
- EXECUTADO EM: 2026-05-02 01:33 UTC.
- ENTREGAS REAIS: adicionado contrato estruturado `ClinicalBibliographyReference`, campo `bibliography` em `QueryResponse` e servico `clinical_bibliography_service` para deduplicar referencias e renderizar rodape markdown `## Referencias bibliograficas`.
- VERIFICACAO: `py_compile` passou; testes focados `3 passed, 240 deselected`; backend reiniciado no servico existente e `/api/health?light=true` publico retornou `healthy`.

#### [x] VCHAT-003 - Criar testes de contrato sem LLM real
- Status: COMPLETED
- O QUE: garantir que payload v2 serializa, valida e preserva compatibilidade.
- ONDE: suite de testes backend.
- COMO: usar fixtures estaticas sem chamada externa.
- DEPENDENCIA: VCHAT-001 e VCHAT-002.
- CRITERIO DE PRONTO: testes passam localmente sem API externa.
- ENTREGA: testes automatizados de contrato.
- AGENTE EXECUTOR: adicionar testes e registrar resultado no log antes da proxima task.
- EXECUTADO EM: 2026-05-02 11:20 UTC.
- ENTREGAS REAIS: adicionados testes offline para schema JSON do `QueryResponse`, payload legado, payload clinico v2, rodape vazio, deduplicacao de referencias e pipeline `search_and_answer` com `generate_answer` mockado.
- VERIFICACAO: `py_compile` passou; testes focados da Sprint 0.1 `6 passed, 240 deselected`.

### Sprint 0.1 - Fechamento
- Status: COMPLETED
- Tasks concluidas: VCHAT-001, VCHAT-002, VCHAT-003.
- Entrega consolidada: contrato clinico v2 criado de forma retrocompativel, com campos estruturados para secoes, guardrails, referencias bibliograficas deduplicadas e rodape markdown.
- Proxima sprint: Sprint 0.2 - Eval Set Clinico Inicial, iniciando por VCHAT-004.

### Sprint 0.2 - Eval Set Clinico Inicial

#### [x] VCHAT-004 - Criar evals de perguntas clinicas reais
- Status: COMPLETED
- O QUE: criar perguntas de regressao para gastroenterite, hepatopatia, convulsao, DRC, pancreatite, piometra e obstrucao uretral.
- ONDE: suite de evaluacao/testes.
- COMO: cada pergunta deve declarar secoes esperadas e tipo de evidencia requerida.
- DEPENDENCIA: VCHAT-003.
- CRITERIO DE PRONTO: evals rodam e falham/registram baseline do comportamento atual.
- ENTREGA: dataset de evals clinicos.
- AGENTE EXECUTOR: criar evals e atualizar documentacao antes da proxima task.
- EXECUTADO EM: 2026-05-02 11:32 UTC.
- ENTREGAS REAIS: criado `docs/03_build/VCHAT_EVALS/clinical_eval_v1.json` com 7 casos clinicos: gastroenterite em cao, hepatopatia em cao, convulsao em cao, DRC em gato, pancreatite em cao, piometra em cadela e obstrucao uretral em gato.
- CONTRATO: cada caso declara especie, problema clinico, sistema organico, intencao, secoes esperadas, evidencias requeridas, termos PT, termos EN e secoes que podem ficar ausentes.
- VERIFICACAO: `py_compile` passou; testes focados `2 passed, 246 deselected`.

#### [x] VCHAT-005 - Criar fixtures esperadas de secoes e referencias
- Status: COMPLETED
- O QUE: definir fixtures para secoes obrigatorias e rodape bibliografico.
- ONDE: testes/evals.
- COMO: validar presenca de secoes, referencias e ausencia de unsupported claims.
- DEPENDENCIA: VCHAT-004.
- CRITERIO DE PRONTO: fixtures cobrem resposta completa e resposta parcial.
- ENTREGA: fixtures de validacao.
- AGENTE EXECUTOR: criar fixtures e registrar gaps antes da proxima task.
- EXECUTADO EM: 2026-05-02 11:37 UTC.
- ENTREGAS REAIS: criado `docs/03_build/VCHAT_EVALS/clinical_eval_expected_v1.json` com fixtures esperadas para os 7 casos clinicos, incluindo secoes obrigatorias, secoes ausentes permitidas, campos obrigatorios de referencia, heading do rodape e guardrails obrigatorios.
- VERIFICACAO: `py_compile` passou; testes focados `4 passed, 246 deselected`.

#### [x] VCHAT-006 - Registrar baseline atual
- Status: COMPLETED
- O QUE: executar evals contra chat atual e registrar falhas.
- ONDE: docs e logs de avaliacao.
- COMO: medir secoes ausentes, referencias ausentes, respostas fora de escopo e low confidence.
- DEPENDENCIA: VCHAT-004 e VCHAT-005.
- CRITERIO DE PRONTO: baseline documentado.
- ENTREGA: relatorio de baseline.
- AGENTE EXECUTOR: executar evals, salvar resultado e atualizar runtime state.
- EXECUTADO EM: 2026-05-02 11:54 UTC.
- ENTREGAS REAIS: criado runner `src/scripts/clinical_eval_baseline.py`; baseline real salvo em `docs/03_build/VCHAT_EVALS/clinical_baseline_current_chat_latest.md` e `.json`.
- RESULTADO BASELINE: `0/7` passaram; `7/7` falharam; `51` secoes ausentes; `14` falhas de bibliografia; `28` falhas de guardrails; `5` respostas low-confidence.
- VERIFICACAO: `py_compile` passou; testes offline do runner `5 passed, 246 deselected`; baseline real executado contra o chat atual em `443.29s`.

### Sprint 0.2 - Fechamento
- Status: COMPLETED
- Tasks concluidas: VCHAT-004, VCHAT-005, VCHAT-006.
- Entrega consolidada: eval set clinico v1, fixtures esperadas e baseline atual documentado.
- Decisao tecnica: seguir para Sprint 1.1, pois o chat atual falha no contrato clinico v2 por ausencia de secoes estruturadas, rodape bibliografico e guardrails.
- Proxima sprint: Sprint 1.1 - Planner JSON Deterministico, iniciando por VCHAT-007.

## Phase 1 - Planejador Clinico Multilíngue

### Sprint 1.1 - Planner JSON Deterministico

#### [x] VCHAT-007 - Implementar planner pre-retrieval
- Status: COMPLETED
- O QUE: criar no LLM que transforma pergunta em plano clinico de busca.
- ONDE: novo servico de planejamento ou modulo de search service.
- COMO: temperatura baixa/zero, prompt restrito, saida JSON.
- DEPENDENCIA: VCHAT-006.
- CRITERIO DE PRONTO: planner nao responde ao usuario e nao recomenda conduta.
- ENTREGA: planner funcional com testes.
- AGENTE EXECUTOR: implementar planner, testes e documentar antes da proxima task.
- EXECUTADO EM: 2026-05-02 11:59 UTC.
- ENTREGAS REAIS: adicionados schemas `ClinicalQueryPlan` e `ClinicalQueryVariant`; criado `src/services/clinical_query_planner_service.py` com prompt LLM JSON, temperatura `0`, preservacao da query original, `answers_user=false` e fallback deterministico para os 7 casos clinicos.
- VERIFICACAO: `py_compile` passou; testes focados `7 passed, 246 deselected`; reproducao direta mostrou planos para os 7 casos sem responder ao usuario.

#### [x] VCHAT-008 - Validar schema e rejeitar plano invalido
- Status: COMPLETED
- O QUE: validar JSON do planner contra schema forte.
- ONDE: models/schemas e servico de planejamento.
- COMO: rejeitar campos ausentes, escopo alterado ou plano ambíguo sem warning.
- DEPENDENCIA: VCHAT-007.
- CRITERIO DE PRONTO: plano invalido nao segue para retrieval.
- ENTREGA: validador de plano.
- AGENTE EXECUTOR: implementar validacao e registrar comportamento de erro.
- EXECUTADO EM: 2026-05-02 12:07 UTC.
- ENTREGAS REAIS: criado `ClinicalQueryPlanValidationError`; adicionada validacao de payload LLM com campos obrigatorios; adicionado `validate_clinical_query_plan()` para bloquear plano que responde ao usuario, altera query original, nao tem variante original, nao tem secoes, nao tem sinal clinico ou esta ambiguo sem `scope_warning`.
- VERIFICACAO: `py_compile` passou; testes focados `9 passed, 246 deselected`; teste red/green confirmou fallback quando LLM retorna payload incompleto.

#### [x] VCHAT-009 - Registrar logs seguros do plano
- Status: COMPLETED
- O QUE: logar plano, idioma, variantes e warnings sem expor segredo.
- ONDE: telemetry/logs.
- COMO: mascarar dados sensiveis e manter request_id/trace_id.
- DEPENDENCIA: VCHAT-008.
- CRITERIO DE PRONTO: plano auditavel por request.
- ENTREGA: telemetria de planner.
- AGENTE EXECUTOR: adicionar logs e atualizar documentacao.
- EXECUTADO EM: 2026-05-02 12:13 UTC.
- ENTREGAS REAIS: criado log JSONL `clinical_planner.jsonl` no `TelemetryService`; evento `clinical_query_plan` registra `request_id`, `trace_id`, idioma, especie, problema clinico, sistema, intencao, termos canonicos, secoes desejadas, warnings, status de validacao e variantes com hash/tamanho/tipo, sem persistir query ou variante em texto bruto.
- VERIFICACAO: teste red/green confirmou que nome de tutor e query bruta nao aparecem no evento; `py_compile` passou; testes ampliados `44 passed, 212 deselected`.

### Sprint 1.2 - Traducao Contextual e Preservacao de Escopo

#### [x] VCHAT-010 - Gerar variantes original/PT/EN/sinonimos
- Status: COMPLETED
- O QUE: criar fan-out planejado mantendo pergunta original.
- ONDE: search service/retrieval orchestration.
- COMO: usar plano clinico para gerar variantes sem substituir query original.
- DEPENDENCIA: VCHAT-009.
- CRITERIO DE PRONTO: variantes possuem origem e finalidade registradas.
- ENTREGA: lista de queries estruturadas.
- AGENTE EXECUTOR: implementar fan-out inicial e testes.
- EXECUTADO EM: 2026-05-02 12:20 UTC.
- ENTREGAS REAIS: `ClinicalQueryVariant` passou a registrar `origin`; criado fan-out estruturado `original`, `technical_pt`, `technical_en` e `synonyms` a partir do plano clinico; variantes sao deduplicadas, preservam a query original e carregam origem/finalidade; telemetria segura registra origem sem texto bruto.
- VERIFICACAO: teste red/green cobriu fallback deterministico e payload LLM parcial; `py_compile` passou; testes ampliados `46 passed, 212 deselected`.

#### [x] VCHAT-011 - Validar preservacao de contexto da traducao
- Status: COMPLETED
- O QUE: garantir que traducao nao altere especie, doenca, intencao, gravidade ou tempo.
- ONDE: guardrails pre-retrieval.
- COMO: comparar plano original e variantes traduzidas.
- DEPENDENCIA: VCHAT-010.
- CRITERIO DE PRONTO: variante com contexto alterado e bloqueada.
- ENTREGA: guardrail `translation_context_preserved`.
- AGENTE EXECUTOR: implementar validador e registrar motivo de bloqueio.
- EXECUTADO EM: 2026-05-02 12:25 UTC.
- ENTREGAS REAIS: `ClinicalQueryVariant` passou a registrar `context_preserved`, `blocked` e `blocked_reason`; criado `validate_translation_context_preserved()` para validar especie, problema clinico, intencao e marcadores de tempo/gravidade; variante EN agora usa especie/intencao/contexto em ingles; telemetria segura registra bloqueio sem texto bruto.
- VERIFICACAO: teste red/green confirmou traducao preservada para pancreatite aguda grave em cao e bloqueio de variante alterada para gato/renal; `py_compile` passou; testes ampliados `48 passed, 212 deselected`.

#### [x] VCHAT-012 - Rejeitar fan-out que altere escopo clinico
- Status: COMPLETED
- O QUE: impedir que o retrieval pesquise problema diferente do perguntado.
- ONDE: guardrails pre-retrieval.
- COMO: validar `scope_preserved` antes de consultar Qdrant.
- DEPENDENCIA: VCHAT-011.
- CRITERIO DE PRONTO: fan-out invalido aborta com erro controlado/abstencao.
- ENTREGA: guardrail de escopo.
- AGENTE EXECUTOR: implementar bloqueio e atualizar docs.
- EXECUTADO EM: 2026-05-02 12:30 UTC.
- ENTREGAS REAIS: criado `validate_fanout_scope_preserved()` para rejeitar plano/fan-out antes do retrieval quando especie ou problema clinico divergem da pergunta original, ou quando variante bloqueada pelo guardrail de traducao segue ativa; fluxo LLM invalido cai para fallback deterministico.
- VERIFICACAO: teste red/green confirmou rejeicao de variante bloqueada e fallback quando LLM troca pancreatite/cao por DRC/gato; `py_compile` passou; testes ampliados `50 passed, 212 deselected`.

## Phase 2 - Retrieval Clinico e Evidence Pack

### Sprint 2.1 - Fan-out de Retrieval PT/EN

#### [x] VCHAT-013 - Executar fan-out original/PT/EN/sinonimos
- Status: COMPLETED
- O QUE: consultar Qdrant por multiplas variantes.
- ONDE: execute_search/search orchestration.
- COMO: rodar variantes com limites de candidato e rastrear origem.
- DEPENDENCIA: VCHAT-012.
- CRITERIO DE PRONTO: candidatos retornam com `query_variant`.
- ENTREGA: retrieval fan-out funcional.
- AGENTE EXECUTOR: implementar e testar com corpus real.
- EXECUTADO EM: 2026-05-02 12:37 UTC.
- ENTREGAS REAIS: adicionado `query_variant` opcional em `SearchResultItem`; criado `execute_clinical_fanout_search()` em `search_service` para planejar a query, executar `search_hybrid` por variante segura e anexar metadados de variante sem texto bruto; variantes bloqueadas nao sao consultadas.
- VERIFICACAO: testes red/green cobriram execucao de 4 variantes e skip de variante bloqueada; `py_compile` passou; testes ampliados `52 passed, 212 deselected`; smoke real com corpus retornou `method=clinical_fanout`, `8` resultados, `77` candidatos e variantes `original`, `technical_pt`, `technical_en`, `synonyms`.

#### [x] VCHAT-014 - Combinar candidatos sem duplicar chunks
- Status: COMPLETED
- O QUE: mergear resultados preservando melhor score e origens.
- ONDE: camada de retrieval.
- COMO: deduplicar por `chunk_id`.
- DEPENDENCIA: VCHAT-013.
- CRITERIO DE PRONTO: pool final nao duplica chunks.
- ENTREGA: merge deterministico.
- AGENTE EXECUTOR: implementar merge e testes.
- EXECUTADO EM: 2026-05-02 21:01 UTC.
- ENTREGAS REAIS: adicionado `query_variants` em `SearchResultItem`; criado merge deterministico `_merge_clinical_fanout_candidates()` por `chunk_id`, mantendo o item de maior score, ordenacao final por score e lista deduplicada de origens das variantes.
- VERIFICACAO: teste red/green confirmou chunk duplicado retornando uma vez, com melhor score e origens `original`, `technical_pt`, `technical_en`; `py_compile` passou; testes ampliados `53 passed, 212 deselected`; smoke real com corpus retornou `8` resultados, `8` chunk_ids unicos, `raw_result_count=8`, `deduped_result_count=8`, `duplicate_chunk_count=0`.

#### [x] VCHAT-015 - Expor debug administrativo de variantes
- Status: COMPLETED
- O QUE: permitir auditoria de qual variante encontrou cada chunk.
- ONDE: response debug/telemetry.
- COMO: expor apenas para contexto administrativo ou log interno.
- DEPENDENCIA: VCHAT-014.
- CRITERIO DE PRONTO: diagnostico de retrieval fica auditavel.
- ENTREGA: debug de retrieval.
- AGENTE EXECUTOR: adicionar debug e atualizar docs.
- EXECUTADO EM: 2026-05-02 21:14 UTC.
- ENTREGAS REAIS: criado bloco `scores_breakdown.clinical_fanout_debug` com resumo, variantes executadas/bloqueadas e chunks finais; cada chunk registra `best_variant` e `matched_variants` sem texto bruto da query; debug marcado como `safe_for_admin_response=true`.
- VERIFICACAO: teste red/green confirmou debug sem chave `query` e sem nome de tutor; `py_compile` passou; testes ampliados `54 passed, 212 deselected`; smoke real confirmou debug com `4` variantes, `8` chunks, sem `query` nas variantes e sem `Ricardo` no payload.

### Sprint 2.2 - Reranking Clinico

#### [x] VCHAT-016 - Classificar candidatos por categoria clinica
- Status: COMPLETED
- O QUE: rotular chunks por sintomas, exames, tratamento, cirurgia, referencias etc.
- ONDE: reranker/evidence service.
- COMO: heuristicas deterministicas primeiro; LLM apenas se necessario e validado.
- DEPENDENCIA: VCHAT-015.
- CRITERIO DE PRONTO: cada chunk relevante recebe categoria.
- ENTREGA: classificador clinico.
- AGENTE EXECUTOR: implementar classificacao e testes.
- EXECUTADO EM: 2026-05-02 21:19 UTC.
- ENTREGAS REAIS: adicionados `clinical_categories`, `primary_clinical_category` e `clinical_category_matches` em `SearchResultItem`; criado `classify_clinical_candidate()` com heuristicas deterministicas para resumo, historico/resenha, sinais/sintomas, exames complementares, tratamento clinico, tratamento cirurgico, proximos passos e referencias; fan-out passa a classificar candidatos antes do merge/debug.
- VERIFICACAO: testes red/green cobriram as categorias principais e propagacao para debug; `py_compile` passou; testes ampliados `56 passed, 212 deselected`; smoke real retornou `7` resultados categorizados com categorias `referencias`, `tratamento_clinico` e `exames_complementares`.

#### [x] VCHAT-017 - Reranquear com diversidade de secoes
- Status: COMPLETED
- O QUE: escolher chunks que cubram secoes clinicas, nao apenas maior score lexical.
- ONDE: reranker.
- COMO: combinar score, categoria, especie, problema e diversidade.
- DEPENDENCIA: VCHAT-016.
- CRITERIO DE PRONTO: top-k final melhora cobertura por secao.
- ENTREGA: reranking clinico.
- AGENTE EXECUTOR: implementar reranker e comparar evals.
- EXECUTADO EM: 2026-05-02 21:27 UTC.
- ENTREGAS REAIS: criado reranker deterministico `_rerank_clinical_candidates_for_diversity()` apos merge do fan-out; candidatos sao selecionados primeiro por diversidade de categorias clinicas desejadas e depois completados por score; `scores_breakdown.clinical_reranking` registra categorias selecionadas, quantidade de diversidade e remanescentes.
- VERIFICACAO: teste red/green confirmou que chunks de `sinais_sintomas` e `exames_complementares` sobem acima do segundo chunk repetido de `tratamento_clinico`; `py_compile` passou; testes ampliados `57 passed, 212 deselected`; smoke real retornou `8` resultados, `selected_diversity_count=6` e categorias de diversidade `resumo`, `sinais_sintomas`, `exames_complementares`, `tratamento_clinico`, `referencias`, `tratamento_cirurgico`.

#### [x] VCHAT-018 - Bloquear chunks fora do escopo clinico
- Status: COMPLETED
- O QUE: remover chunks de indice, bibliografia isolada ou assunto diferente.
- ONDE: reranker/guardrails retrieval.
- COMO: aplicar filtros de escopo e sinais de baixa aderencia.
- DEPENDENCIA: VCHAT-017.
- CRITERIO DE PRONTO: chunks fora de escopo nao alimentam resposta clinica.
- ENTREGA: filtro de escopo.
- AGENTE EXECUTOR: implementar filtro e documentar excecoes.
- EXECUTADO EM: 2026-05-02 21:35 UTC.
- ENTREGAS REAIS: criado filtro deterministico `_filter_clinical_scope_candidates()` antes do merge/reranking; remove chunks de indice/sumario, bibliografia isolada sem conteudo clinico e assunto clinico divergente de especie/problema; `scores_breakdown.clinical_scope_filter` registra mantidos/removidos e motivos sem texto bruto.
- VERIFICACAO: teste red/green confirmou remocao de indice, bibliografia isolada e DRC/gato em pergunta de pancreatite/cao; `py_compile` passou; testes ampliados `58 passed, 212 deselected`; smoke real removeu `1` chunk por `clinical_scope_mismatch` e manteve `7`.

### Sprint 2.3 - Evidence Pack por Secao

#### [x] VCHAT-019 - Montar evidence pack categorizado
- Status: COMPLETED
- O QUE: agrupar evidencia por secao obrigatoria.
- ONDE: novo evidence pack service.
- COMO: usar categorias do reranker e metadados de documento.
- DEPENDENCIA: VCHAT-018.
- CRITERIO DE PRONTO: evidence pack alimenta gerador v2.
- ENTREGA: evidence pack estruturado.
- AGENTE EXECUTOR: implementar service e testes.
- EXECUTADO EM: 2026-05-02 21:44 UTC.
- ENTREGAS REAIS: adicionados schemas `ClinicalEvidenceItem`, `ClinicalEvidenceSection` e `ClinicalEvidencePack`; criado `src/services/clinical_evidence_pack_service.py` para agrupar chunks recuperados por secao clinica obrigatoria, preservar score/documento/pagina/chunk/variantes de busca e marcar secoes sem evidencia com `nao localizado nos trechos recuperados`.
- VERIFICACAO: teste red/green focado `2 passed, 270 deselected`; `py_compile` passou; testes ampliados do fluxo clinico `60 passed, 212 deselected`; smoke real com query `Qual protocolo para pancreatite em cao?` retornou `7` resultados, evidence pack com `10` itens, secoes encontradas `resumo`, `sinais_sintomas`, `tratamento_clinico`, `tratamento_cirurgico`, `proximos_passos`, `referencias` e secoes ausentes `historico_resenha`, `exames_complementares`.

#### [x] VCHAT-020 - Carregar metadados bibliograficos por secao
- Status: COMPLETED
- O QUE: anexar documento, pagina, chunk_id, score e justificativa.
- ONDE: evidence pack/citations.
- COMO: normalizar metadados existentes do retrieval.
- DEPENDENCIA: VCHAT-019.
- CRITERIO DE PRONTO: toda evidencia tem origem bibliografica.
- ENTREGA: metadados de referencia.
- AGENTE EXECUTOR: implementar metadados e validar corpus real.
- EXECUTADO EM: 2026-05-02 22:01 UTC.
- ENTREGAS REAIS: `ClinicalEvidenceItem` agora carrega `bibliographic_reference` estruturado; `ClinicalEvidenceSection` e `ClinicalEvidencePack` carregam `bibliography` deduplicada por documento/pagina/chunk, com secoes sustentadas acumuladas para alimentar o futuro rodape `Referencias bibliograficas`.
- VERIFICACAO: teste red/green focado `4 passed, 270 deselected`; `py_compile` passou; testes ampliados do fluxo clinico `62 passed, 212 deselected`; smoke real com query `Qual protocolo para pancreatite em cao?` retornou `7` resultados, evidence pack com `10` itens, `7` referencias deduplicadas e bibliografia nas secoes `resumo`, `sinais_sintomas`, `tratamento_clinico`, `tratamento_cirurgico`, `proximos_passos`, `referencias`.
- RISCO RESIDUAL: o smoke real no workspace `default` ainda retornou ao menos uma referencia nao clinica (`politicas_fluxpay.md`), indicando contaminacao de corpus/retrieval que deve ser tratada em etapa futura de escopo/corpus antes da resposta final v2.

#### [x] VCHAT-021 - Marcar secoes sem evidencia
- Status: COMPLETED
- O QUE: preencher `missing_sections` antes da resposta.
- ONDE: evidence pack service.
- COMO: identificar secoes obrigatorias sem chunks suficientes.
- DEPENDENCIA: VCHAT-020.
- CRITERIO DE PRONTO: lacunas ficam explicitas.
- ENTREGA: missing sections deterministico.
- AGENTE EXECUTOR: implementar e atualizar docs.
- EXECUTADO EM: 2026-05-02 22:05 UTC.
- ENTREGAS REAIS: `ClinicalEvidencePack` agora expõe `missing_sections` calculado de forma deterministica a partir das secoes obrigatorias que permaneceram com status `missing`; secoes encontradas nao entram na lista e secoes vazias preservam placeholder `nao localizado nos trechos recuperados`.
- VERIFICACAO: teste red/green focado `5 passed, 270 deselected`; `py_compile` passou; testes ampliados do fluxo clinico `63 passed, 212 deselected`; smoke real com query `Qual protocolo para pancreatite em cao?` retornou `missing_sections=['historico_resenha', 'exames_complementares']` e secoes encontradas `resumo`, `sinais_sintomas`, `tratamento_clinico`, `tratamento_cirurgico`, `proximos_passos`, `referencias`.

### Sprint 2.3 - Fechamento
- Status: COMPLETED
- Tasks concluidas: VCHAT-019, VCHAT-020, VCHAT-021.
- Entrega consolidada: evidence pack clinico estruturado por secao, com referencias bibliograficas normalizadas/deduplicadas e lacunas explicitas via `missing_sections`.
- Risco residual: smoke real ainda indica risco de contaminacao do workspace `default` com documento nao clinico no retrieval; esse risco deve ser considerado na geracao/verificacao da resposta v2.
- Proxima sprint: Sprint 3.1 - Agente Professor Veterinario, iniciando por VCHAT-022.

## Phase 3 - Resposta Professoral com Rodape Bibliografico

### Sprint 3.1 - Agente Professor Veterinario

#### [x] VCHAT-022 - Criar gerador de resposta por secoes
- Status: COMPLETED
- O QUE: gerar resposta professoral em portugues com secoes obrigatorias.
- ONDE: llm service/search response service.
- COMO: prompt restrito ao evidence pack, temperatura baixa/zero.
- DEPENDENCIA: VCHAT-021.
- CRITERIO DE PRONTO: resposta contem todas as secoes ou marca ausentes.
- ENTREGA: gerador v2.
- AGENTE EXECUTOR: implementar gerador e testes com fixtures.
- EXECUTADO EM: 2026-05-02 22:10 UTC.
- ENTREGAS REAIS: adicionado schema `ClinicalGeneratedAnswer`; criado `src/services/clinical_response_generator_service.py` com gerador deterministico `generate_clinical_answer_from_evidence_pack()` que renderiza as 8 secoes obrigatorias em markdown, usa somente textos do evidence pack, inclui marcadores bibliograficos por chunk e propaga `missing_sections` sem preencher lacunas.
- VERIFICACAO: teste red/green focado `2 passed, 275 deselected`; `py_compile` passou; testes ampliados do fluxo clinico `65 passed, 212 deselected`; smoke real com query `Qual protocolo para pancreatite em cao?` gerou headings `Resumo do problema` e `Exames complementares`, preservou `missing_sections=['historico_resenha', 'exames_complementares']` e marcou `exames_complementares` como `nao localizado nos trechos recuperados`.
- RISCO RESIDUAL: o smoke real continuou mostrando contaminacao do workspace `default` por chunks `fluxpay`; o gerador respeita o evidence pack, mas a qualidade final ainda depende de resolver/filtrar essa contaminacao no retrieval/corpus.

#### [x] VCHAT-023 - Impedir conhecimento geral sem evidencia
- Status: COMPLETED
- O QUE: bloquear preenchimento por memoria do modelo.
- ONDE: prompt, guardrails e verifier.
- COMO: exigir citacao por afirmacao clinica relevante.
- DEPENDENCIA: VCHAT-022.
- CRITERIO DE PRONTO: unsupported claims viram reescrita/reducao.
- ENTREGA: bloqueio de invencao.
- AGENTE EXECUTOR: implementar guardrail e testes negativos.
- EXECUTADO EM: 2026-05-02 22:16 UTC.
- ENTREGAS REAIS: `ClinicalGeneratedAnswer` agora carrega `guardrails`; criado `verify_clinical_answer_grounding()` para detectar linhas de resposta sem suporte textual no evidence pack; criado `reduce_unsupported_clinical_answer()` para regenerar resposta deterministica a partir do evidence pack quando houver claims sem evidencia.
- VERIFICACAO: testes negativos focados `2 passed, 277 deselected`; fatia gerador/evidence pack `9 passed, 270 deselected`; `py_compile` passou; testes ampliados do fluxo clinico `67 passed, 212 deselected`; smoke real com query `Qual protocolo para pancreatite em cao?` retornou `unsupported_claims=[]` e `bibliographic_grounding=True`.
- RISCO RESIDUAL: smoke real ainda retorna primeiro chunk `chunk_doc-fluxpay-reembolso_0000`, reforcando que a contaminacao do workspace `default` deve ser filtrada no retrieval/corpus antes de liberar runtime clinico.

#### [x] VCHAT-024 - Diferenciar evidencia parcial de protocolo completo
- Status: COMPLETED
- O QUE: evitar chamar resumo parcial de protocolo.
- ONDE: gerador/verificador.
- COMO: se secoes criticas faltarem, marcar como orientacao parcial.
- DEPENDENCIA: VCHAT-023.
- CRITERIO DE PRONTO: resposta nao superestima completude.
- ENTREGA: regra de completude.
- AGENTE EXECUTOR: implementar regra e documentar.
- EXECUTADO EM: 2026-05-02 22:23 UTC.
- ENTREGAS REAIS: `ClinicalGeneratedAnswer` agora expoe `completeness_status` e `completeness_note`; o gerador adiciona bloco `Escopo da resposta` quando secoes criticas (`exames_complementares`, `tratamento_clinico`) estao ausentes, marcando `orientacao parcial` e evitando declarar protocolo completo sem evidencia.
- VERIFICACAO: testes focados de completude `2 passed, 279 deselected`; fatia gerador/evidence pack `11 passed, 270 deselected`; `py_compile` passou; testes ampliados do fluxo clinico `69 passed, 212 deselected`; smoke real com query `Qual protocolo para pancreatite em cao?` retornou `completeness_status=partial`, `missing_sections=['historico_resenha', 'exames_complementares']`, `unsupported_claims=[]` e `bibliographic_grounding=True`.
- RISCO RESIDUAL: smoke real ainda retorna primeiro chunk `chunk_doc-fluxpay-reembolso_0000`; a regra de completude evita superestimar a resposta, mas a contaminacao do workspace `default` ainda deve ser filtrada no retrieval/corpus.

### Sprint 3.1 - Fechamento
- Status: COMPLETED
- Tasks concluidas: VCHAT-022, VCHAT-023, VCHAT-024.
- Entrega consolidada: gerador professoral inicial por secoes, restrito ao evidence pack, com guardrail contra unsupported claims e regra de completude parcial.
- Risco residual: contaminacao do workspace `default` por chunks nao clinicos segue visivel em smoke real e deve ser resolvida antes da liberacao runtime clinica.
- Proxima sprint: Sprint 3.2 - Rodape de Referencias Bibliograficas, iniciando por VCHAT-025.

### Sprint 3.2 - Rodape de Referencias Bibliograficas

#### [x] VCHAT-025 - Gerar `bibliography_footer`
- Status: COMPLETED
- O QUE: criar rodape markdown `Referencias bibliograficas`.
- ONDE: gerador de resposta.
- COMO: usar apenas citations/evidence pack.
- DEPENDENCIA: VCHAT-024.
- CRITERIO DE PRONTO: toda resposta v2 termina com rodape bibliografico.
- ENTREGA: footer markdown.
- AGENTE EXECUTOR: implementar footer e testes.
- EXECUTADO EM: 2026-05-02 22:27 UTC.
- ENTREGAS REAIS: `ClinicalGeneratedAnswer` agora carrega `bibliography_footer`; o gerador usa `format_bibliography_footer()` sobre `evidence_pack.bibliography` e anexa o rodape `## Referencias bibliograficas` ao fim de `answer_markdown`, inclusive no caso sem referencias recuperadas.
- VERIFICACAO: testes focados de footer `2 passed, 281 deselected`; fatia gerador/evidence pack `13 passed, 270 deselected`; `py_compile` passou; testes ampliados do fluxo clinico `71 passed, 212 deselected`; smoke real com query `Qual protocolo para pancreatite em cao?` retornou `bibliography_count=7`, `footer_heading='## Referencias bibliograficas'`, `answer_ends_with_footer=True`, `unsupported_claims=[]` e `bibliographic_grounding=True`.
- RISCO RESIDUAL: smoke real ainda retorna primeiro chunk `chunk_doc-fluxpay-reembolso_0000`; o footer reflete corretamente o evidence pack, mas a contaminacao do workspace `default` permanece risco de qualidade.

#### [x] VCHAT-026 - Deduplicar referencias
- Status: COMPLETED
- O QUE: remover repeticoes por documento/pagina/chunk.
- ONDE: bibliography formatter.
- COMO: ordenar referencias por primeira aparicao na resposta.
- DEPENDENCIA: VCHAT-025.
- CRITERIO DE PRONTO: footer limpo, sem duplicidades.
- ENTREGA: deduplicador.
- AGENTE EXECUTOR: implementar e testar.
- EXECUTADO EM: 2026-05-02 22:35 UTC.
- ENTREGAS REAIS: `format_bibliography_footer()` agora deduplica referencias por documento/pagina/chunk, mescla secoes sustentadas e aceita `answer_markdown` para ordenar referencias pela primeira aparicao do `chunk_id` no corpo da resposta; o gerador passa o corpo sem footer para essa ordenacao antes de anexar o rodape.
- VERIFICACAO: testes focados de ordenacao/deduplicacao `3 passed, 283 deselected`; fatia bibliography/gerador/evidence pack `18 passed, 268 deselected`; `py_compile` passou; testes ampliados do fluxo clinico `76 passed, 210 deselected`; smoke real com query `Qual protocolo para pancreatite em cao?` retornou `footer_reference_lines=7`, `footer_unique_chunk_ids=7`, `answer_ends_with_footer=True`, `unsupported_claims=[]` e primeira referencia igual ao primeiro chunk evidencial.
- RISCO RESIDUAL: smoke real ainda retorna primeiro chunk `chunk_doc-fluxpay-reembolso_0000`; a ordenacao/deduplicacao do footer esta correta, mas o conteudo herdado do retrieval ainda depende da limpeza/filtro do workspace `default`.

#### [x] VCHAT-027 - Renderizar footer no `answer_markdown`
- Status: COMPLETED
- O QUE: anexar rodape ao markdown final mantendo citations estruturadas.
- ONDE: response assembly e frontend futuro.
- COMO: compor answer + footer sem perder campos estruturados.
- DEPENDENCIA: VCHAT-026.
- CRITERIO DE PRONTO: API retorna footer no markdown e em campo proprio.
- ENTREGA: resposta final com referencias no rodape.
- AGENTE EXECUTOR: implementar e atualizar docs.
- EXECUTADO EM: 2026-05-03 01:11 UTC.
- ENTREGAS REAIS: `/query` com `retrieval_profile=clinical_v2` retorna `answer` retrocompativel, `answer_markdown` terminando com `## Referencias bibliograficas`, `bibliography_footer` em campo proprio e `bibliography` estruturado.
- VERIFICACAO: teste focado `test_search_and_answer_clinical_v2_returns_structured_payload_and_legacy_answer` passou; eval v2 `7/7` passou.

## Phase 4 - Verificacao, Guardrails e Abstencao

### Sprint 4.1 - Grounding por Secao

#### [x] VCHAT-028 - Validar citacao por secao
- Status: COMPLETED
- O QUE: verificar que cada secao respondida tem fonte.
- ONDE: grounding service.
- COMO: mapear claims por secao e citations correspondentes.
- DEPENDENCIA: VCHAT-027.
- CRITERIO DE PRONTO: secao sem citacao e marcada ausente/reduzida.
- ENTREGA: grounding por secao.
- AGENTE EXECUTOR: implementar e testar.
- EXECUTADO EM: 2026-05-03 01:11 UTC.
- ENTREGAS REAIS: `Citation` passou a expor `section` e `sections`; `QueryResponse` passou a expor `section_citation_map` e `section_grounding`; o gerador cria mapa deterministico por secao a partir do evidence pack.
- VERIFICACAO: suíte clínica `45 passed, 242 deselected`.

#### [x] VCHAT-029 - Detectar unsupported claims
- Status: COMPLETED
- O QUE: identificar afirmacoes clinicas nao sustentadas.
- ONDE: grounding/guardrails.
- COMO: comparar resposta contra evidence pack.
- DEPENDENCIA: VCHAT-028.
- CRITERIO DE PRONTO: `unsupported_claims=[]` para release.
- ENTREGA: detector de claims.
- AGENTE EXECUTOR: implementar e registrar metricas.
- EXECUTADO EM: 2026-05-03 01:11 UTC.
- ENTREGAS REAIS: verifier compara linhas da resposta contra evidence pack normalizado e mantém `guardrails.unsupported_claims`; eval v2 terminou com `guardrail_failure_count=0`.
- VERIFICACAO: suíte clínica `45 passed`; eval v2 `7/7` sem unsupported claims.

#### [x] VCHAT-030 - Reduzir resposta quando grounding falhar
- Status: COMPLETED
- O QUE: reescrever ou reduzir resposta para o conteudo sustentado.
- ONDE: response verifier.
- COMO: aplicar retry restrito ou abstencao parcial.
- DEPENDENCIA: VCHAT-029.
- CRITERIO DE PRONTO: resposta sem suporte nao chega ao usuario.
- ENTREGA: reducao segura.
- AGENTE EXECUTOR: implementar e documentar motivos.
- EXECUTADO EM: 2026-05-03 01:11 UTC.
- ENTREGAS REAIS: `reduce_unsupported_clinical_answer()` regenera resposta deterministica restrita ao evidence pack quando claims sem suporte aparecem.
- VERIFICACAO: testes negativos do gerador e suíte clínica passaram.

### Sprint 4.2 - Guardrails de Escopo

#### [x] VCHAT-031 - Validar `scope_preserved`
- Status: COMPLETED
- O QUE: confirmar que plano, retrieval e resposta mantiveram o problema perguntado.
- ONDE: guardrails service.
- COMO: comparar query original, plano, variantes e resposta.
- DEPENDENCIA: VCHAT-030.
- CRITERIO DE PRONTO: escopo alterado bloqueia resposta.
- ENTREGA: guardrail de escopo final.
- AGENTE EXECUTOR: implementar e testar.
- EXECUTADO EM: 2026-05-03 01:11 UTC.
- ENTREGAS REAIS: filtro pós-retrieval remove índice/sumário, bibliografia isolada, documento operacional não clínico, assunto clínico conflitante e candidato sem sinal do problema clínico esperado em trechos longos.
- VERIFICACAO: teste de filtro de escopo passou; smoke real removeu `nonclinical_domain`, `index_or_toc`, `bibliography_only`, `clinical_scope_mismatch` e `missing_clinical_problem_signal` conforme o caso.

#### [x] VCHAT-032 - Validar `translation_context_preserved`
- Status: COMPLETED
- O QUE: garantir que traducao nao mudou sentido clinico.
- ONDE: guardrails service.
- COMO: validar especie, doenca, intencao e gravidade.
- DEPENDENCIA: VCHAT-031.
- CRITERIO DE PRONTO: traducao ruim nao consulta nem responde.
- ENTREGA: guardrail de traducao.
- AGENTE EXECUTOR: implementar e atualizar docs.
- EXECUTADO EM: 2026-05-03 01:11 UTC.
- ENTREGAS REAIS: variantes traduzidas seguem validadas no planner e o payload final expõe `guardrails.translation_context_preserved=true` quando o plano passou.
- VERIFICACAO: suíte clínica e eval v2 passaram.

#### [x] VCHAT-033 - Registrar motivos de bloqueio/reducao
- Status: COMPLETED
- O QUE: tornar audivel por que o sistema reduziu ou bloqueou resposta.
- ONDE: telemetry/logs.
- COMO: logar reason codes sem vazar dados sensiveis.
- DEPENDENCIA: VCHAT-032.
- CRITERIO DE PRONTO: cada abstencao/reducao tem motivo rastreavel.
- ENTREGA: logs de guardrails.
- AGENTE EXECUTOR: implementar logs e validar.
- EXECUTADO EM: 2026-05-03 01:11 UTC.
- ENTREGAS REAIS: `grounding_reason` em `queries.jsonl` agora inclui `completeness`, `missing_sections` e `guardrail_reasons`; `retrieval.clinical_generation.guardrail_reasons` expõe motivos auditáveis no payload.
- VERIFICACAO: log real contém `retrieval_profile=clinical_v2` e reason codes; eval v2 `7/7`.

## Phase 5 - API, Frontend e Observabilidade

### Sprint 5.1 - API Retrocompativel

#### [x] VCHAT-034 - Expandir response model
- Status: COMPLETED
- O QUE: adicionar campos v2 ao response model.
- ONDE: schemas/API.
- COMO: manter `answer`, `citations`, `confidence`, `grounded` existentes.
- DEPENDENCIA: VCHAT-033.
- CRITERIO DE PRONTO: contrato antigo continua valido.
- ENTREGA: API v2 retrocompativel.
- AGENTE EXECUTOR: implementar e testar contrato.
- EXECUTADO EM: 2026-05-03 01:11 UTC.
- ENTREGAS REAIS: `QueryResponse` inclui campos v2 opcionais: `answer_markdown`, `sections`, `bibliography`, `bibliography_footer`, `missing_sections`, `guardrails`, `completeness_*`, `section_citation_map` e `section_grounding`.
- VERIFICACAO: schema JSON e contrato legado passaram.

#### [x] VCHAT-035 - Manter compatibilidade com consumidores existentes
- Status: COMPLETED
- O QUE: garantir que integrações que usam `answer` nao quebrem.
- ONDE: API tests.
- COMO: testes de payload antigo e novo.
- DEPENDENCIA: VCHAT-034.
- CRITERIO DE PRONTO: consumidores antigos recebem resposta utilizavel.
- ENTREGA: compatibilidade verificada.
- AGENTE EXECUTOR: implementar testes e documentar.
- EXECUTADO EM: 2026-05-03 01:11 UTC.
- ENTREGAS REAIS: `answer` continua preenchido com markdown final; payload legado sem campos v2 continua validando com defaults.
- VERIFICACAO: testes de payload legado e clínico v2 passaram.

#### [x] VCHAT-036 - Documentar contrato de API
- Status: COMPLETED
- O QUE: atualizar docs de API para chat clinico v2.
- ONDE: docs.
- COMO: exemplos de request/response com bibliography footer.
- DEPENDENCIA: VCHAT-035.
- CRITERIO DE PRONTO: contrato compreensivel para integração externa.
- ENTREGA: documentacao de API.
- AGENTE EXECUTOR: atualizar docs antes da proxima sprint.
- EXECUTADO EM: 2026-05-03 01:11 UTC.
- ENTREGAS REAIS: SPEC 0123 atualizada como contrato canônico do chat clínico v2, incluindo campos estruturados, citações por seção, footer bibliográfico e guardrails.
- VERIFICACAO: documentação atualizada antes do fechamento.

### Sprint 5.2 - Frontend Clinico

#### [x] VCHAT-037 - Renderizar secoes clinicas no chat
- Status: COMPLETED
- O QUE: exibir resposta por secoes.
- ONDE: frontend chat.
- COMO: usar payload estruturado quando disponivel e fallback para `answer`.
- DEPENDENCIA: VCHAT-036.
- CRITERIO DE PRONTO: resposta clinica fica escaneavel.
- ENTREGA: UI por secoes.
- AGENTE EXECUTOR: implementar frontend e validar visualmente.
- EXECUTADO EM: 2026-05-03 01:11 UTC.
- ENTREGAS REAIS: `/chat` usa `clinical_v2` por padrão, renderiza seções clínicas estruturadas quando `sections` existe e mantém fallback para `answer`.
- VERIFICACAO: `npm run lint` e `npm run build` passaram.

#### [x] VCHAT-038 - Renderizar rodape de referencias bibliograficas
- Status: COMPLETED
- O QUE: exibir referencias no rodape da resposta.
- ONDE: frontend chat.
- COMO: renderizar `bibliography_footer` e citations.
- DEPENDENCIA: VCHAT-037.
- CRITERIO DE PRONTO: usuario ve fonte, pagina e chunk.
- ENTREGA: rodape bibliografico no frontend.
- AGENTE EXECUTOR: implementar e validar no navegador.
- EXECUTADO EM: 2026-05-03 01:11 UTC.
- ENTREGAS REAIS: frontend renderiza `bibliography_footer` no corpo da resposta e aba `Referências` com documento, página, seções e `chunk_id`.
- VERIFICACAO: `npm run build` passou.

#### [x] VCHAT-039 - Exibir avisos de evidencia parcial e secoes ausentes
- Status: COMPLETED
- O QUE: mostrar badges/avisos quando a resposta for parcial.
- ONDE: frontend chat.
- COMO: usar `missing_sections` e guardrails.
- DEPENDENCIA: VCHAT-038.
- CRITERIO DE PRONTO: usuario sabe o que nao foi encontrado.
- ENTREGA: UI de evidencia parcial.
- AGENTE EXECUTOR: implementar e atualizar docs.
- EXECUTADO EM: 2026-05-03 01:11 UTC.
- ENTREGAS REAIS: UI exibe badge de evidência parcial, seções ausentes, `completeness_note`, claims sem suporte e fontes por seção.
- VERIFICACAO: frontend lint/build verdes.

### Sprint 5.3 - Observabilidade e Auditoria

#### [x] VCHAT-040 - Registrar telemetria do pipeline v2
- Status: COMPLETED
- O QUE: medir planner, fan-out, reranking, evidence pack, resposta e guardrails.
- ONDE: telemetry/logs.
- COMO: usar trace_id/request_id e tempos por etapa.
- DEPENDENCIA: VCHAT-039.
- CRITERIO DE PRONTO: cada consulta v2 e rastreavel.
- ENTREGA: telemetria completa.
- AGENTE EXECUTOR: implementar e validar.
- EXECUTADO EM: 2026-05-03 01:11 UTC.
- ENTREGAS REAIS: telemetria de query registra `retrieval_profile`, reason codes clínicos, contagem de unsupported claims, cobertura de citação, latência e chunks usados; planner mantém log seguro sem texto bruto.
- VERIFICACAO: `queries.jsonl` e `clinical_planner.jsonl` receberam eventos reais.

#### [x] VCHAT-041 - Criar relatorio de qualidade por eval
- Status: COMPLETED
- O QUE: gerar relatorio com pass/fail por pergunta e secao.
- ONDE: docs/evals.
- COMO: incluir cobertura de referencias e unsupported claims.
- DEPENDENCIA: VCHAT-040.
- CRITERIO DE PRONTO: qualidade mensuravel antes do release.
- ENTREGA: relatorio de eval.
- AGENTE EXECUTOR: executar evals e documentar.
- EXECUTADO EM: 2026-05-03 01:11 UTC.
- ENTREGAS REAIS: relatório v2 salvo em `docs/03_build/VCHAT_EVALS/clinical_v2_eval_latest.md` e `.json`.
- RESULTADO: `7/7` casos passaram; `0` falhas de seção; `0` falhas bibliográficas; `0` falhas de guardrails; `0` low confidence; duração `109.56s`.
- VERIFICACAO: runner executado com `retrieval_profile=clinical_v2`, `top_k=8`, `threshold=0.25`.

#### [x] VCHAT-042 - Definir criterios de release
- Status: COMPLETED
- O QUE: consolidar gate final do chat clinico v2.
- ONDE: docs/build gate.
- COMO: exigir evals verdes, referencias no rodape e guardrails sem falha critica.
- DEPENDENCIA: VCHAT-041.
- CRITERIO DE PRONTO: release controlado aprovado ou bloqueado com causa clara.
- ENTREGA: decisao de release.
- AGENTE EXECUTOR: atualizar estado/log e recomendar proximo passo.
- EXECUTADO EM: 2026-05-03 01:11 UTC.
- ENTREGAS REAIS: release funcional do chat clínico v2 aprovado para uso controlado: API/contrato/frontend/eval/guardrails verdes.
- CRITERIOS DE RELEASE: eval clínico `7/7`; `unsupported_claims=[]`; `bibliography_footer` presente; `answer` retrocompatível; frontend build verde; filtro de escopo ativo.
- RISCO RESIDUAL: testes integrados antigos de consistência Qdrant do dataset FluxPay falham porque a coleção runtime não contém os 21 chunks canônicos esperados por esses testes (`0 == 21`); não é regressão do chat clínico v2, mas deve ser tratado em ciclo separado de saneamento do corpus de teste.

### Hotfix pós-release - Qualidade da resposta clínica

#### [x] VCHAT-HF-003 - Corrigir resposta de gastroenterite com evidencia fraca/OCR cru
- Status: COMPLETED
- O QUE: impedir que termos soltos preencham secoes clinicas e que chunks OCR sejam despejados no chat.
- ONDE: `clinical_evidence_pack_service.py`, `clinical_response_generator_service.py`, `search_service.py`, testes clinicos.
- COMO: validar suporte concreto por secao, renderizar fallback extrativo controlado, respeitar `desired_sections` do planner e remover `referencias` de ausentes quando ha rodape.
- DEPENDENCIA: release `clinical_v2`.
- CRITERIO DE PRONTO: resposta ruim reportada deixa de retornar `high` por preenchimento artificial; exames/tratamento fracos ficam ausentes; markdown nao expoe OCR bruto.
- EXECUTADO EM: 2026-05-03 03:24 UTC.
- ENTREGAS REAIS: filtro por secao implementado, sintese extrativa por frases suportadas, propagacao de secoes planejadas e tres testes de regressao adicionados.
- VERIFICACAO: `58 passed, 242 deselected` para `-k clinical`; recorte direto `8 passed, 292 deselected`; compileall dos servicos alterados passou.
- RISCO RESIDUAL: corpus real ainda pode nao conter exames suficientes para gastroenterite; nesse caso o comportamento correto e resposta parcial, nao protocolo completo.

### Sprint 5.3 - Fechamento
- Status: COMPLETED
- Tasks concluidas: VCHAT-027 a VCHAT-042; hotfix VCHAT-HF-003 concluido em 2026-05-03.
- Entrega consolidada: chat clínico veterinário v2 funcional, estruturado por seções, com retrieval clínico multilíngue, guardrails determinísticos, resposta restrita ao evidence pack, referências bibliográficas no rodapé, frontend compatível e eval clínico verde.
