# Clinical Chat v2 - Release Decision

- timestamp: 2026-05-03T01:11:00Z
- status: APPROVED_FOR_CONTROLLED_USE
- retrieval_profile: clinical_v2
- dataset: veterinary_clinical_chat_v1
- report: `docs/03_build/VCHAT_EVALS/clinical_v2_eval_latest.md`

## Resultado
- evals: 7/7 pass
- missing_sections_count: 0
- bibliography_failure_count: 0
- guardrail_failure_count: 0
- low_confidence_count: 0
- latest_eval_duration: 109.56s

## Evidencias de Build
- backend clinical slice: `45 passed, 242 deselected`
- frontend lint: passed
- frontend build: passed
- py_compile clinical/backend touched modules: passed
- smoke real pancreatite: `grounded=true`, `low_confidence=false`, `bibliography=14`
- runtime publico: backend/frontend/Caddy ativos; `/api/health?light=true` healthy; `/chat` HTTP 200

## Criterios Aprovados
- resposta final mantém `answer` retrocompativel;
- resposta v2 expõe `answer_markdown`, `sections`, `bibliography_footer`, `section_citation_map`, `section_grounding`, `missing_sections` e `guardrails`;
- rodape `## Referencias bibliograficas` é renderizado no markdown final e em campo proprio;
- unsupported claims são reduzidos ao evidence pack;
- filtros de escopo removem indice/sumario, bibliografia isolada, documentos operacionais e assunto clinico divergente;
- frontend renderiza secoes, referencias e avisos de evidencia parcial.

## Risco Residual
Os testes integrados antigos de consistencia Qdrant do dataset FluxPay seguem falhando porque a colecao runtime atual nao contem os 21 chunks canonicos esperados por esses testes (`0 == 21`). Esse gap e de saneamento do corpus/test fixture do ambiente, nao do pipeline clinico v2.

## Hotfix 2026-05-03 - HCM
- causa: planner deterministico nao reconhecia `cardiomiopatia hipertrofica`, deixando o filtro de escopo aceitar chunks genericos de semiologia.
- correcao: regra HCM PT/EN, filtro por identidade do problema, bloqueio de tabela/figura solta, conflito plural de especie e `bibliographic_grounding=false` sem referencias.
- verificacao: `48 passed, 242 deselected`; pergunta real HCM retorna `confidence=low`, `grounded=false`, `low_confidence=true`, sem chunks/bibliografia quando o corpus nao sustenta protocolo.

## Decisao
Liberar o chat clinico v2 para uso controlado no produto, mantendo observacao de qualidade por perguntas reais e abrindo ciclo separado apenas se o corpus/test fixture Qdrant legado precisar ser reconciliado.
