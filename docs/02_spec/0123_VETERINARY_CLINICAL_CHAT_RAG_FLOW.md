# 0123 - Veterinary Clinical Chat RAG Flow

## Contexto
- Data: 2026-05-02
- Escopo: redesenho do fluxo de consulta e resposta do chat RAG veterinario.
- Status: proposta tecnica para aprovacao antes de implementacao.

## Problema
O chat atual responde como um RAG generico: recebe a pergunta, busca top-k chunks, gera resposta curta e verifica grounding.
Isso e insuficiente para uso clinico veterinario porque:
- a pergunta do usuario nao e transformada em um plano clinico de busca;
- corpus em ingles e portugues exige retrieval multilíngue, nao apenas resposta multilíngue;
- o top-k pode trazer chunks soltos, sem cobrir historico, sinais, exames, tratamento e referencias;
- a resposta final nao segue o padrao de um professor/consultor em medicina veterinaria;
- a verificacao atual valida grounding, mas nao garante completude por secoes clinicas.

## Principio Tecnico
O problema nao deve ser tratado como incapacidade de idioma do LLM.
O LLM final pode responder em portugues, mas ele so consegue usar bem aquilo que o retrieval entregar.
Portanto, a solucao correta e uma orquestracao RAG clinica:

```
Mensagem do usuario
-> Preparador/tradutor de query clinica
-> Query de retrieval em ingles quando a entrada vier em portugues
-> Retrieval hibrido
-> Reranking clinico
-> Montagem de evidencia por secoes
-> Agente professor veterinario
-> Verificador de grounding/completude
-> Resposta estruturada em portugues brasileiro com referencias
```

## Correcao de Direcao Arquitetural - 2026-05-03

Decisao operacional: o fluxo principal do `clinical_v2` nao deve depender de catalogo local crescente de aliases por doenca para conseguir recuperar evidencia. A regra canonica de idioma passa a ser:

- se a entrada do usuario estiver em portugues, traduzir a pergunta para ingles antes do retrieval;
- se a entrada ja estiver em ingles, seguir para retrieval com a query original;
- a busca vetorial/hibrida pode operar em ingles como lingua interna principal;
- a resposta final exibida no chat deve sempre ser gerada em portugues brasileiro;
- etapas intermediarias podem usar ingles ou estrutura JSON, desde que preservem o sentido da pergunta original;
- a traducao deve ser bloqueada antes do retrieval se alterar especie, problema clinico, intencao ou remover o problema clinico;
- aliases determinísticos por problema clinico sao legado/fallback transitório e nao devem ser expandidos como mecanismo principal de busca.

## Guardrails Obrigatorios
O chat clinico v2 deve ser desenhado para reduzir criatividade e maximizar determinismo.
O LLM nao pode inventar diagnostico, tratamento, dose, exame, prognostico ou referencia.

Regras globais:
- a fase de consulta nao responde ao usuario; ela apenas prepara a query de retrieval;
- a traducao PT->EN antes da pesquisa deve preservar o contexto clinico da frase original;
- a pergunta original deve ser sempre mantida para auditoria, contexto e guardrail;
- termos traduzidos nao podem alterar especie, doenca/problema, intencao, gravidade ou contexto temporal;
- o retrieval deve limitar o escopo ao problema clinico detectado;
- a resposta final deve ser pautada nas referencias bibliograficas recuperadas;
- se os chunks nao sustentarem uma secao, a secao deve ser marcada como ausente;
- se os chunks sustentarem apenas parte do problema, a resposta deve dizer que a evidencia e parcial;
- e proibido preencher lacunas com conhecimento geral do modelo;
- e proibido responder fora do escopo clinico perguntado;
- doses, condutas, exames e indicacoes cirurgicas so podem aparecer com citacao;
- referencias bibliograficas devem vir dos documentos/chunks recuperados, nao da memoria do LLM.

Controles de determinismo:
- prompts de planejamento e resposta devem usar temperatura baixa ou zero;
- saida do planejador deve ser JSON validado por schema;
- campos clinicos essenciais devem ser normalizados antes da busca;
- o plano de busca deve ser rejeitado se mudar o sentido da pergunta original;
- a resposta deve passar por verificacao de grounding por secao;
- respostas sem citacao suficiente devem ser reescritas ou reduzidas ao conteudo sustentado.

## Fluxo Atual Resumido
1. Frontend envia `QueryRequest`.
2. API valida sessao/workspace.
3. `search_and_answer()` cria `SearchRequest`.
4. `execute_search()` aplica expansoes simples e consulta Qdrant via busca hibrida.
5. Resultado e reranqueado por BM25F/neural conforme configuracao.
6. Chunks encontrados sao enviados ao LLM gerador.
7. `verify_grounding()` verifica se a resposta esta sustentada por citacoes.
8. API retorna resposta, chunks usados, citacoes, confidence e low_confidence.

## Fluxo Alvo - Consulta

### 1. Entrada e Contexto
Objetivo: receber a pergunta sem perder contexto clinico.

Entradas:
- mensagem atual;
- historico curto da conversa;
- workspace/tenant;
- idioma preferido do usuario;
- modo de resposta: rapido ou clinico completo.

Saida esperada:
- pergunta normalizada;
- contexto conversacional relevante;
- restricoes de workspace e permissao.

### 2. No LLM - Preparador/Tradutor Clinico de Query
Objetivo: transformar a pergunta em uma query de retrieval segura, preferencialmente em ingles, sem responder ao usuario.

O LLM deve extrair em JSON:
- idioma da pergunta;
- pergunta original preservada;
- query de retrieval em ingles quando a entrada estiver em portugues;
- query original quando a entrada ja estiver em ingles;
- especie, se explicitamente presente;
- problema principal, se explicitamente presente;
- intencao: diagnostico, protocolo, tratamento, exames, resumo, prognostico;
- secoes clinicas desejadas;
- aviso de escopo quando a pergunta for ambigua ou ampla demais.

Guardrails do planejador:
- nao diagnosticar;
- nao recomendar conduta;
- nao completar informacao ausente;
- traduzir mantendo contexto e intencao;
- preservar explicitamente a frase original;
- gerar a query de retrieval em ingles como rota principal quando a entrada estiver em portugues;
- nao depender de aliases locais por doenca para completar a query;
- retornar baixa confianca sem retrieval quando uma pergunta clinica em portugues nao tiver `clinical_problem` validado;
- retornar `scope_warning` quando a pergunta for ambigua ou ampla demais.

Exemplo de rota principal para `protocolo para hepatopatia em cao`:
- entrada original preservada para auditoria: `protocolo para hepatopatia em cao`
- query interna de retrieval validada: `canine liver disease treatment chronic hepatitis copper-associated hepatopathy`
- resposta final: portugues brasileiro, sustentada apenas pelos chunks recuperados.

### 3. Query de Retrieval
Objetivo: consultar o corpus usando uma query de busca em ingles quando a entrada vier em portugues, ou a propria query original quando a entrada ja estiver em ingles.

O sistema deve buscar por:
- `clinical_translation_en`, quando a entrada estiver em portugues;
- `original_query`, quando a entrada ja estiver em ingles.

Regra importante:
- a query original nunca deve ser perdida, mesmo quando nao for a query executada no retrieval;
- a traducao para ingles e a rota principal de retrieval para entradas em portugues;
- nenhuma traducao pode mudar especie, doenca/problema, intencao clinica ou pergunta original;
- resposta final continua obrigatoriamente em portugues brasileiro.

### 4. Retrieval Hibrido
Objetivo: recuperar candidatos amplos e relevantes.

Fontes:
- dense/vector por embeddings;
- sparse/BM25;
- filtros por workspace;
- filtros futuros por idioma/documento/tags/capitulos, se existirem.

Saida:
- pool amplo de candidatos, por exemplo 60 a 120 chunks;
- score por variante de query;
- origem da variante que encontrou cada chunk.

### 5. Reranking Clinico
Objetivo: escolher chunks relevantes para a pergunta clinica, nao apenas chunks com palavras parecidas.

O reranker deve considerar:
- aderencia ao problema;
- aderencia a especie;
- presenca de conduta, dose, exame ou sinal clinico;
- autoridade do trecho;
- diversidade de secoes;
- proximidade de pagina/capitulo.

Saida:
- top chunks finais;
- motivo curto do score;
- categoria clinica do chunk.

### 6. Montagem de Evidencia
Objetivo: organizar chunks antes de enviar ao agente respondedor.

Categorias:
- resumo do problema;
- achados de historico/resenha;
- sinais e sintomas;
- exames complementares;
- tratamento clinico;
- tratamento cirurgico/intervencional;
- proximos passos;
- referencias bibliograficas.

Se uma categoria nao tiver evidencia suficiente:
- marcar internamente como ausente em `missing_sections`;
- deixar o texto da secao vazio no payload de resposta ao usuario;
- nao inventar conteudo para preencher a lacuna.

O evidence pack deve carregar, por secao:
- texto do chunk;
- documento;
- pagina;
- chunk_id;
- score;
- variante de query que encontrou o chunk;
- justificativa curta de aderencia ao problema clinico.

## Fluxo Alvo - Resposta

### 7. Agente Professor de Medicina Veterinaria
Objetivo: responder como especialista, em portugues, com estrutura clinica.

Formato obrigatorio:
1. Resumo do problema
2. Achados de historico clinico / resenha
3. Principais sinais e sintomas descritos na literatura
4. Exames complementares
5. Tratamento clinico
6. Tratamento cirurgico ou intervencional, quando aplicavel
7. Proximos passos
8. Referencias bibliograficas

Rodape obrigatorio:
- toda resposta clinica deve terminar com `Referencias bibliograficas`;
- o rodape deve listar documento, pagina e chunk_id usados;
- referencias devem ser deduplicadas;
- cada referencia deve indicar quais secoes da resposta ela sustentou;
- se nao houver referencia suficiente, a resposta deve ser reduzida ou marcada como insuficiente.

Regras:
- usar somente evidencia recuperada;
- citar documento/pagina/chunk por secao;
- diferenciar informacao forte de informacao parcial;
- nao chamar uma lista parcial de protocolo completo;
- nao dar resposta infantil ou excessivamente curta quando o modo clinico completo estiver ativo;
- se faltar evidencia, omitir a secao sem suporte da resposta visivel e preservar a lacuna nos metadados internos.
- nao usar conhecimento geral do modelo para completar secao sem evidencia;
- nao criar referencias bibliograficas;
- nao extrapolar de outra especie para a especie perguntada;
- nao transformar exemplo, indice remissivo ou bibliografia isolada em recomendacao clinica;
- quando houver conflito entre fontes, expor o conflito e nao escolher silenciosamente.

### 8. Verificador de Grounding e Completude
Objetivo: impedir resposta bonita, mas sem base.

Validacoes:
- cada secao renderizada tem citacao; secoes sem evidencia ficam ausentes no texto visivel e marcadas em `missing_sections`;
- doses e tratamentos estao citados;
- resposta nao extrapola especie ou doenca;
- resposta nao mistura chunks desconexos como se fossem um protocolo unico;
- referencias existem no payload.
- a traducao de retrieval preservou o contexto da pergunta original;
- as referencias bibliograficas citadas aparecem nos chunks recuperados;
- nao ha afirmacao clinica sem fonte recuperada;
- nao ha conteudo fora do escopo da pergunta.

Se falhar:
- pedir reescrita mais fiel ao contexto;
- ou reduzir a resposta para o que foi sustentado.

### 9. Payload Final
Resposta deve expor:
- `answer_markdown`;
- `sections`;
- `citations`;
- `confidence`;
- `grounded`;
- `missing_sections`;
- `retrieval_debug` opcional para administradores.

## Contrato de Resposta Clinica

Exemplo de secoes esperadas:

```json
{
  "answer_markdown": "...",
  "sections": {
    "resumo": "...",
    "historico_resenha": "...",
    "sinais_sintomas": "...",
    "exames_complementares": "...",
    "tratamento_clinico": "...",
    "tratamento_cirurgico": "...",
    "proximos_passos": "...",
    "referencias": "..."
  },
  "bibliography_footer": "## Referencias bibliograficas\n1. Ettinger..., p. 2196, chunk_... — tratamento_clinico",
  "bibliography": [
    {
      "document_filename": "Ettinger...",
      "page": 2196,
      "chunk_id": "chunk_...",
      "sections": ["tratamento_clinico"]
    }
  ],
  "citations": [
    {
      "document_filename": "Ettinger...",
      "page": 2196,
      "chunk_id": "chunk_...",
      "section": "tratamento_clinico",
      "sections": ["tratamento_clinico"]
    }
  ],
  "section_citation_map": {
    "tratamento_clinico": ["chunk_..."]
  },
  "section_grounding": {
    "tratamento_clinico": true,
    "exames_complementares": false
  },
  "confidence": "high|medium|low",
  "grounded": true,
  "missing_sections": [],
  "guardrails": {
    "scope_preserved": true,
    "translation_context_preserved": true,
    "unsupported_claims": [],
    "bibliographic_grounding": true
  }
}
```

## Implementacao Consolidada em 2026-05-03
- `retrieval_profile=clinical_v2` ativa o pipeline clinico completo sem quebrar consumidores antigos de `answer`.
- A rota principal prepara uma unica query de retrieval: entrada em portugues e traduzida para ingles com gate de preservacao de escopo; entrada em ingles segue como passthrough.
- Fan-out PT/EN/sinonimos e aliases determinísticos permanecem apenas como legado/fallback de testes e nao sao o fluxo principal do `clinical_v2`.
- O filtro de escopo remove indice/sumario, bibliografia isolada, documento operacional nao clinico, assunto clinico conflitante e candidatos longos sem sinal do problema clinico esperado.
- A resposta final e gerada de forma deterministica a partir do evidence pack, com `answer_markdown`, `sections`, `bibliography`, `bibliography_footer`, `section_citation_map`, `section_grounding`, `missing_sections`, `completeness_status` e `guardrails`.
- O frontend `/chat` usa `clinical_v2` por padrao e renderiza secoes, aviso de evidencia parcial, fontes por secao e aba de referencias.
- O relatorio `docs/03_build/VCHAT_EVALS/clinical_v2_eval_latest.md` registrou `7/7` casos clinicos passando com `0` falhas de bibliografia, guardrails ou low confidence.

## Backlog Corretivo Pos-Relatorio
- VCHAT-CORR-001: gate forte de preservacao PT->EN antes do retrieval.
- VCHAT-CORR-002: `clinical_problem` obrigatorio para pergunta clinica em portugues.
- VCHAT-CORR-003: classificadores/evidence pack ampliados para corpo estranho linear, obstrucao, cirurgia abdominal, enterotomy, gastrotomy e peritonitis.
- VCHAT-CORR-004: telemetria segura de traducao com idioma, aplicacao, bloqueio, motivo e hash da query EN.
- VCHAT-CORR-005: aba Retrieval restrita/sanitizada no frontend.
- VCHAT-CORR-006: esta SPEC remove fan-out/aliases como fluxo principal.
- VCHAT-007: adaptar API para retornar secoes estruturadas mantendo compatibilidade com `answer`.
- VCHAT-008: criar conjunto de avaliacoes com perguntas reais: gastroenterite, hepatopatia, convulsao, DRC, pancreatite, piometra, obstrucao uretral.
- VCHAT-009: implementar guardrails determinísticos de pre-retrieval e pos-retrieval, incluindo preservacao de contexto na traducao e bloqueio de afirmacoes sem referencia.

## Criterio de Pronto
- Uma pergunta em portugues deve recuperar evidencia em livros em portugues e ingles.
- Uma pergunta em ingles deve recuperar evidencia em livros em ingles e portugues quando aplicavel.
- A resposta deve sair em portugues quando o usuario perguntar em portugues.
- A resposta deve seguir secoes clinicas completas.
- Toda afirmacao clinica relevante deve ter citacao.
- Secoes sem evidencia devem ser marcadas como ausentes, nao inventadas.
- A traducao para busca deve preservar contexto, especie, doenca e intencao.
- O sistema deve bloquear ou reduzir respostas com afirmacoes sem suporte bibliografico recuperado.
- O sistema deve registrar guardrails aplicados e motivos de reducao/abstencao.
