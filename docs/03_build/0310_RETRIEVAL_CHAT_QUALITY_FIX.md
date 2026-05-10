# 0310 - Retrieval/Chat Quality Fix

## Contexto
- Data: 2026-05-01
- Escopo: chat e busca apos conclusao do indexador 400MB.
- Problema observado: perguntas veterinarias em portugues retornavam chunks fracos ou abstencao, mesmo com livros grandes indexados corretamente.

## Diagnostico
- O corpus operacional contem livros majoritariamente em ingles e portugues.
- Consultas em portugues sobre temas presentes em livros em ingles nao atravessavam bem para termos como `fracture`, `external skeletal fixation`, `postoperative care`, `status epilepticus`.
- O default `threshold=0.70` era alto para o score normalizado atual; resultados corretos observados ficam tipicamente entre `0.25` e `0.50`.
- Reranking BM25F existia, mas estava desligado por padrao no runtime.
- O frontend preservava `threshold=0.70` em storage local, mantendo comportamento antigo para usuarios que ja tinham aberto chat/busca.

## Decisao Tecnica
- Ajustar `DEFAULT_THRESHOLD` operacional para `0.25`.
- Ativar `RERANKING_ENABLED=true` com `RERANKING_METHOD=bm25f`.
- Ampliar a ponte terminologica portugues -> ingles para termos clinicos/cirurgicos comuns.
- Aplicar a ponte terminologica tambem no caminho de `/search`, nao apenas no retry do `/query`.
- Versionar storage local do frontend para forcar novo default em chat e busca.

## Evidencia Antes
- Query: `como tratar fratura em gato com fixador esquelético externo`
- Resultado: chunks de `Semiologia Veterinaria Canary.pdf`, `low_confidence=true`, chat com abstencao.

## Evidencia Depois
- Query: `como tratar fratura em gato com fixador esquelético externo`
- Resultado: chunks do livro de cirurgia, paginas `907`, `1325`, `917`, `low_confidence=false`.
- Chat: `low_confidence=false`, `confidence=high`, `grounded=true`, `citations=5`.
- Query: `cuidados pós-operatórios em cirurgia veterinária`
- Resultado: chunks do livro de cirurgia/perioperatorio, `low_confidence=false`.

## Tasks Executadas
- [x] RQ-001: reproduzir falha com consultas veterinarias em portugues.
- [x] RQ-002: confirmar corpus operacional e collection Qdrant correta.
- [x] RQ-003: ampliar ponte terminologica portugues -> ingles.
- [x] RQ-004: aplicar ponte terminologica no caminho comum de busca.
- [x] RQ-005: baixar threshold operacional para score normalizado.
- [x] RQ-006: ativar reranking BM25F por padrao.
- [x] RQ-007: resetar defaults persistidos no frontend via storage versionado.
- [x] RQ-008: atualizar documentacao antes do fechamento.

## Validacao
- `src/.venv/bin/python -m py_compile src/services/search_service.py src/models/schemas.py src/core/config.py`
- `PYTHONPATH=src src/.venv/bin/pytest -q src/tests/test_sprint5.py -k 'crosslingual_bridge or query_pipeline_retries_with_crosslingual_bridge'`
- `cd frontend && npx tsc --noEmit`
- Reproducao direta com corpus real e `.env` carregado.

## Validacao Pos-Restart
- Backend, frontend e Caddy ativos.
- DNS publico `/chat`: HTTP 200.
- DNS publico `/search`: HTTP 200.
- DNS publico `/api/health?light=true`: `healthy`, collection `cvg_master_rag`.
- Query `como tratar fratura em gato com fixador esquelético externo`: `low_confidence=false`, `confidence=high`, `grounded=true`, `citation_coverage=1.0`.

## Proximo Passo
- Testar consultas reais no chat e busca pelo usuario final.
- Registrar exemplos ruins restantes para ajuste fino de ranking/evaluations.

## Ajuste Incremental - Gastroenterite
- Data: 2026-05-01 23:28 UTC.
- Evidencia do log: `me de um protocolo de gastroenterite em cão` retornava `Não sei`, apesar de `top_result_score=0.6358852907034247`.
- Causa: termos de especie (`dog/canine/cão`) e termos genericos de pedido (`protocolo/management`) recebiam peso excessivo no BM25F, permitindo chunks de ortopedia/bibliografia sem `gastroenteritis/diarrhea/vomiting`.
- Correcao: `gastroenterite` passou a expandir para `gastroenteritis`, `acute diarrhea`, `vomiting`, `dehydration`, `fluid therapy` e `antiemetic`; BM25F passou a ignorar overlap apenas de especie/genericos quando ha termos clinicos fortes.
- Correcao adicional: prompt de resposta passou a permitir resposta parcial sustentada pelos trechos, em vez de responder apenas `Não sei` quando nao houver protocolo completo.
- Governanca: respostas sem grounding >= 80% agora ficam `low_confidence=true` e `confidence=medium`, em vez de aparecerem como alta confianca.
- Resultado: a mesma query passou a recuperar chunks do Ettinger sobre doenca gastrointestinal/diarreia/vomito/desidratacao/fluidoterapia e retornar orientacao parcial cautelosa.
- Validacao: `py_compile` passou; testes focados `9 passed`; backend reiniciado e `/api/health?light=true` publico `healthy`.

## Ajuste Incremental - Hepatopatia
- Data: 2026-05-01 23:59 UTC.
- Evidencia do log: `me dê um protocolo para hepatopatia em cão` retornava `Não sei` e depois resposta generica `Os trechos só sustentam uma orientação parcial.`, apesar de a busca ja encontrar chunks com condutas e doses.
- Causa: a ponte terminologica nao cobria bem `hepatopatia/hepático/fígado` para `hepatopathy/hepatic disease/liver disease`, e a re-resposta grounded podia ser aceita mesmo quando nao listava fatos clinicos concretos.
- Correcao: aliases hepaticos adicionados (`hepatopathy`, `hepatic disease`, `liver disease`, `chronic hepatitis`, `copper-associated hepatopathy`, `hepatoprotective therapy`, `SAMe`, `ursodeoxycholic acid`) e rejeicao de re-resposta curta/generica no retry extractivo.
- Resultado `/api/search`: `low_confidence=false`, `results=8`, `top_score=0.4576232476942969`, paginas `2398`, `2196`, `2199` com SAMe, acido ursodesoxicolico, vitamina E, dieta restrita em cobre e terapia imunomodulatoria.
- Resultado `/api/query`: resposta grounded com `confidence=high`, `citation_coverage=1.0`, `low_confidence=false`, usando 8 chunks.
- Validacao: `py_compile` passou; testes focados `11 passed, 229 deselected`; backend reiniciado no servico existente; `/api/health?light=true` publico `healthy`.
