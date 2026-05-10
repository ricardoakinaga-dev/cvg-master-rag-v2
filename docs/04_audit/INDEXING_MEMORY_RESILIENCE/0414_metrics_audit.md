# Metrics Audit - Indexing Memory Resilience

## Resultado

Status: ADERENTE

## `/health?workspace_id=imr_validation`

| Campo | Valor |
|---|---:|
| `status` | `healthy` |
| `telemetry.ingestion_batches.count` | `421` |
| `telemetry.ingestion_batches.errors` | `0` |
| `telemetry.ingestion_batches.rss_peak_mb` | `157.6` |
| `telemetry.ingestion_batches.latest_ingestion_id` | `imr-real-book-2026-05-01` |
| `qdrant.workspace_points` | `0` |

## `/metrics?workspace_id=imr_validation`

| Campo | Valor |
|---|---:|
| `ingestion.total_documents_processed` | `1` |
| `ingestion.parse_success_rate` | `1.0` |
| `ingestion.avg_chunks_per_document` | `2809.0` |
| `ingestion_batches.total_batches` | `421` |
| `ingestion_batches.pages_processed` | `842` |
| `ingestion_batches.chunks_created` | `2809` |
| `ingestion_batches.points_indexed` | `2809` |
| `ingestion_batches.errors` | `0` |

## Conclusao

As metricas sao suficientes para operar canario de upload grande com acompanhamento de progresso, throughput e memoria.
