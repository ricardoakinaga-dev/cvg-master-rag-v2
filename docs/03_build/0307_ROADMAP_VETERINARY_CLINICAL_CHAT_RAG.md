# 0307 - Roadmap Veterinary Clinical Chat RAG v2

## Contexto
- Data: 2026-05-02
- Fonte da verdade: `docs/02_spec/0123_VETERINARY_CLINICAL_CHAT_RAG_FLOW.md`
- Objetivo: transformar o chat RAG generico em assistente clinico veterinario com consulta multilíngue, guardrails determinísticos, resposta professoral e rodape bibliografico.
- Status: aprovado para planejamento; implementacao ainda nao iniciada.

## Regras de Execucao
- Cada task deve ser executada na ordem da sprint.
- O agente executor deve marcar a task como `[x] Executado` ao concluir.
- O agente executor deve atualizar a documentacao da sprint, `docs/99_runtime_state.md` e `docs/20_master_execution_log.md` antes de iniciar a proxima task.
- Nenhuma task pode avancar se quebrar guardrails de nao invencao, preservacao de contexto ou grounding bibliografico.
- Nenhuma resposta clinica v2 pode ser liberada sem rodape `Referencias bibliograficas`.

## Phase 0 - Contratos, Guardrails e Baseline
Objetivo: definir contratos estruturados e testes de referencia antes de alterar o comportamento do chat.

### Sprint 0.1 - Contrato Clinico e Rodape Bibliografico
Entregas:
- schemas de plano clinico, evidence pack, secoes de resposta e rodape bibliografico;
- contrato retrocompativel com `answer`;
- regras de deduplicacao de referencias.

Tasks:
- VCHAT-001: definir contrato de resposta clinica estruturada.
- VCHAT-002: definir contrato do rodape `Referencias bibliograficas`.
- VCHAT-003: criar testes de contrato sem chamar LLM real.

Gate:
- contrato documentado e testado;
- nenhum endpoint publico quebrado.

### Sprint 0.2 - Eval Set Clinico Inicial
Entregas:
- conjunto de perguntas reais para regressao;
- criterios de aprovacao por secao clinica;
- casos negativos para fora de escopo e evidencia insuficiente.

Tasks:
- VCHAT-004: criar evals para gastroenterite, hepatopatia, convulsao, DRC, pancreatite, piometra e obstrucao uretral.
- VCHAT-005: criar fixtures esperadas de secoes obrigatorias e referencias.
- VCHAT-006: registrar baseline atual antes do chat v2.

Gate:
- eval set roda localmente;
- baseline atual registrado.

## Phase 1 - Planejador Clinico Multilíngue
Objetivo: criar o no LLM que planeja busca, traduz preservando contexto e nao responde ao usuario.

### Sprint 1.1 - Planner JSON Deterministico
Entregas:
- servico de planejamento clinico com saida JSON validada;
- temperatura baixa/zero;
- validacao de especie, problema, intencao e secoes desejadas.

Tasks:
- VCHAT-007: implementar planner pre-retrieval sem resposta ao usuario.
- VCHAT-008: validar schema e rejeitar plano invalido.
- VCHAT-009: registrar logs de plano sem expor dados sensiveis.

Gate:
- planner nao inventa conduta;
- planner retorna JSON valido para todos os evals.

### Sprint 1.2 - Traducao Contextual e Preservacao de Escopo
Entregas:
- traducao clinica PT/EN como rota adicional;
- validador de preservacao de contexto;
- bloqueio de variantes que mudem especie, doenca ou intencao.

Tasks:
- VCHAT-010: gerar query original, tecnica PT, tecnica EN e sinonimos.
- VCHAT-011: validar que a traducao preserva contexto da frase.
- VCHAT-012: rejeitar fan-out que altere escopo clinico.

Gate:
- pergunta original sempre preservada;
- variantes invalidas bloqueadas.

## Phase 2 - Retrieval Clinico e Evidence Pack
Objetivo: melhorar recuperacao e organizar evidencia antes da geracao.

### Sprint 2.1 - Fan-out de Retrieval PT/EN
Entregas:
- busca por multiplas variantes;
- score por variante;
- pooling amplo de candidatos.

Tasks:
- VCHAT-013: executar fan-out original/PT/EN/sinonimos.
- VCHAT-014: combinar candidatos sem duplicar chunks.
- VCHAT-015: expor debug administrativo da variante que encontrou cada chunk.

Gate:
- consultas em portugues encontram livros em ingles e portugues;
- consultas em ingles encontram livros relevantes quando existirem.

### Sprint 2.2 - Reranking Clinico
Entregas:
- reranking por aderencia ao problema, especie, conduta, exame, sintoma e autoridade;
- penalizacao de indice remissivo, bibliografia isolada e chunks desconexos.

Tasks:
- VCHAT-016: classificar candidatos por categoria clinica.
- VCHAT-017: reranquear com diversidade de secoes.
- VCHAT-018: bloquear chunks fora do escopo clinico.

Gate:
- top chunks cobrem mais de uma secao quando o corpus permitir;
- chunks de bibliografia isolada nao viram recomendacao clinica.

### Sprint 2.3 - Evidence Pack por Secao
Entregas:
- agrupamento de chunks por resumo, historico/resenha, sintomas, exames, tratamento, cirurgia, proximos passos e referencias;
- marcacao de secoes ausentes.

Tasks:
- VCHAT-019: montar evidence pack categorizado.
- VCHAT-020: carregar documento, pagina, chunk_id, score e justificativa por secao.
- VCHAT-021: marcar secoes sem evidencia.

Gate:
- gerador recebe evidence pack estruturado;
- lacunas sao explicitas antes da resposta.

## Phase 3 - Resposta Professoral com Rodape Bibliografico
Objetivo: gerar resposta clinica completa, didatica e restrita as evidencias recuperadas.

### Sprint 3.1 - Agente Professor Veterinario
Entregas:
- prompt/servico de resposta clinica v2;
- secoes obrigatorias;
- linguagem tecnica, clara e professoral.

Tasks:
- VCHAT-022: criar gerador de resposta por secoes.
- VCHAT-023: impedir preenchimento com conhecimento geral do modelo.
- VCHAT-024: diferenciar evidencia parcial de protocolo completo.

Gate:
- resposta nao infantil;
- resposta nao extrapola o evidence pack.

### Sprint 3.2 - Rodape de Referencias Bibliograficas
Entregas:
- rodape obrigatorio em toda resposta clinica;
- referencias deduplicadas;
- mapeamento referencia -> secoes sustentadas.

Tasks:
- VCHAT-025: gerar `bibliography_footer`.
- VCHAT-026: deduplicar por documento, pagina e chunk_id.
- VCHAT-027: renderizar rodape no `answer_markdown` e manter citations estruturadas.

Gate:
- toda resposta v2 termina com `Referencias bibliograficas`;
- nenhuma referencia e criada fora dos chunks recuperados.

## Phase 4 - Verificacao, Guardrails e Abstencao
Objetivo: impedir resposta bonita sem base, fora de escopo ou com invencao.

### Sprint 4.1 - Grounding por Secao
Entregas:
- verificador por secao;
- deteccao de afirmacoes sem fonte;
- reescrita ou reducao automatica.

Tasks:
- VCHAT-028: validar citacao por secao.
- VCHAT-029: detectar unsupported claims.
- VCHAT-030: reduzir resposta quando grounding falhar.

Gate:
- cada afirmacao clinica relevante tem fonte;
- secoes sem fonte ficam ausentes.

### Sprint 4.2 - Guardrails de Escopo
Entregas:
- validacao de escopo preservado;
- bloqueio de resposta fora do problema clinico;
- logs de motivo de abstencao/reducao.

Tasks:
- VCHAT-031: validar `scope_preserved`.
- VCHAT-032: validar `translation_context_preserved`.
- VCHAT-033: registrar motivos de bloqueio/reducao.

Gate:
- sistema nao responde fora do escopo perguntado;
- mudanca de sentido na traducao bloqueia a execucao.

## Phase 5 - API, Frontend e Observabilidade
Objetivo: disponibilizar o chat clinico v2 sem quebrar consumidores atuais.

### Sprint 5.1 - API Retrocompativel
Entregas:
- payload v2 com `sections`, `bibliography_footer`, `guardrails`, `missing_sections`;
- compatibilidade com `answer` atual.

Tasks:
- VCHAT-034: expandir response model.
- VCHAT-035: manter compatibilidade com consumidores existentes.
- VCHAT-036: documentar contrato de API.

Gate:
- clientes antigos continuam funcionando;
- clientes novos recebem resposta estruturada.

### Sprint 5.2 - Frontend Clinico
Entregas:
- renderizacao por secoes;
- rodape bibliografico visivel;
- badges de evidencia parcial/ausente.

Tasks:
- VCHAT-037: renderizar secoes clinicas no chat.
- VCHAT-038: renderizar rodape de referencias bibliograficas.
- VCHAT-039: exibir avisos de evidencia parcial e missing sections.

Gate:
- usuario ve referencias no rodape da resposta;
- resposta fica escaneavel e util em rotina clinica.

### Sprint 5.3 - Observabilidade e Auditoria
Entregas:
- logs de planner, fan-out, evidence pack, guardrails e grounding;
- metricas de cobertura por secao;
- relatorio de evals.

Tasks:
- VCHAT-040: registrar telemetria do pipeline v2.
- VCHAT-041: criar relatorio de qualidade por eval.
- VCHAT-042: definir criterios de release.

Gate:
- evals clinicos passam;
- auditoria aprova release controlado.

## Ordem Recomendada
1. Sprint 0.1
2. Sprint 0.2
3. Sprint 1.1
4. Sprint 1.2
5. Sprint 2.1
6. Sprint 2.2
7. Sprint 2.3
8. Sprint 3.1
9. Sprint 3.2
10. Sprint 4.1
11. Sprint 4.2
12. Sprint 5.1
13. Sprint 5.2
14. Sprint 5.3

## Release Gate
O chat clinico v2 so pode ser liberado quando:
- evals clinicos passarem;
- toda resposta v2 tiver rodape bibliografico;
- guardrails registrarem `scope_preserved=true`;
- `unsupported_claims=[]`;
- secoes ausentes forem explicitadas;
- API e frontend estiverem validados no DNS publico existente.
