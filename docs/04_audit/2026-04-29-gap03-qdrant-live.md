# 2026-04-29 - GAP-03 Qdrant Live Local

## Objetivo

Executar `GAP-03 - Rodar suite backend com Qdrant local ativo`, eliminando os skips por Qdrant ausente e validando a trilha live de vector store.

## Ambiente

| Item | Valor |
|---|---|
| Qdrant | `qdrant/qdrant:v1.11.5` |
| Container temporario | `cvg-gap03-qdrant` |
| Porta host HTTP | `6337` |
| Porta host gRPC | `6338` |
| Variaveis de teste | `QDRANT_HOST=127.0.0.1 QDRANT_PORT=6337` |
| Politica de isolamento | nao usar a porta default `6333`; nao tocar em Qdrant local existente |

O container temporario foi parado apos a validacao.

## Preparacao do Qdrant

Como a instancia temporaria iniciou vazia, a primeira execucao revelou falhas reais antes escondidas pelos skips:

- collection `rag_phase0` inexistente;
- retrieval retornando candidatos vazios/irrelevantes em casos live;
- BM25 retornando pontos com score zero/hash collision;
- retry neural substituindo resultado suportado por candidato pior.

A collection temporaria foi populada somente com o corpus canonico `default` do dataset operacional, usando embeddings offline deterministicas para evitar custo/rede externa.

## Correcoes Aplicadas

| Arquivo | Mudanca |
|---|---|
| `src/services/vector_service.py` | `_bm25_search` agora ignora resultados com `score <= 0` e candidatos sem suporte lexical minimo. |
| `src/services/vector_service.py` | tokens numericos nao contam como suporte de conteudo em `_content_query_terms`. |
| `src/services/vector_service.py` | baixa confianca cobre overlap numerico incidental sem quebrar cenarios mockados de score alto. |
| `src/services/search_service.py` | retry neural nao roda quando o resultado original ja tem suporte lexical minimo. |

## Validacoes

### Testes direcionados

```bash
QDRANT_HOST=127.0.0.1 QDRANT_PORT=6337 pytest -q \
  src/tests/test_sprint5.py::TestLowConfidence::test_nonsense_query_low_confidence \
  src/tests/test_sprint5.py::TestLowConfidence::test_out_of_domain_query_low_confidence \
  src/tests/test_sprint5.py::TestLowConfidence::test_numeric_only_overlap_query_low_confidence \
  src/tests/test_sprint5.py::TestQueryPipeline::test_query_citations_include_document_filename \
  src/tests/test_sprint5.py::TestMultiDocumentSearch::test_workspace_filter_applied_to_qdrant_query \
  src/tests/test_sprint5.py::TestMultiDocumentSearch::test_source_type_filter_is_honored_after_fusion \
  src/tests/test_sprint5.py::TestMultiDocumentSearch::test_threshold_applies_to_confidence_score \
  src/tests/test_sprint5.py::TestQueryPipeline::test_query_pipeline_retries_with_neural_reranking_when_initial_retrieval_is_bad
```

Resultado:

```text
8 passed
```

### Suite backend completa com Qdrant live

```bash
QDRANT_HOST=127.0.0.1 QDRANT_PORT=6337 pytest -q -rs src/tests
```

Resultado:

```text
253 passed in 205.82s
```

## Decisao

`GAP-03` esta **DONE**.

Nao restaram skips por Qdrant. O proximo passo e `GAP-04`: documentar o comando padrao/reprodutivel de Qdrant local para que a validacao live possa ser repetida sem conhecimento tacito.
