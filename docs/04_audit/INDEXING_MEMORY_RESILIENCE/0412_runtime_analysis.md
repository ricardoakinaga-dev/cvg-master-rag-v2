# Runtime Analysis - Indexing Memory Resilience

## Resultado

Status: ADERENTE

## Servicos

| Servico | Resultado |
|---|---|
| backend systemd | `active` |
| frontend systemd | `active` |
| Qdrant | `/health` reportou `status=ok` |

## Validacao Do Livro Real

| Metrica | Valor |
|---|---:|
| paginas | `842` |
| caracteres | `2523459` |
| chunks | `2809` |
| duracao | `458015 ms` |
| RSS inicial | `126.21 MB` |
| RSS pico | `157.6 MB` |
| RSS final | `157.4 MB` |
| pontos indexados | `2809` |
| pontos apos cleanup | `0` |

## Analise

O processamento real ficou muito abaixo do limite operacional de worker (`INGESTION_WORKER_MEMORY_LIMIT_MB=3072`). A diferenca entre RSS inicial e pico foi pequena para um PDF de `842` paginas, indicando que o processamento por lote e a limpeza de cache controlaram a retencao de memoria.

## Risco Residual

O teste real foi executado em workspace isolado e com embeddings falsos locais para evitar custo externo. A etapa de upload grande por endpoint continua bloqueada pelo limite de `25 MB`, logo a primeira liberacao deve ser feita como canario.
