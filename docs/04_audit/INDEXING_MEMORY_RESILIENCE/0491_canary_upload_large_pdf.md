# Canary Upload - Large PDF Via Real Endpoint

## Status

- engine: AUDIT/RUNTIME_VALIDATION
- date: 2026-05-01
- status: PASSED
- rollback_required: no
- permanent_release: not_applied

## Objetivo

Validar upload grande pelo endpoint real `/documents/upload`, exercitando o fluxo usuario/API -> upload streaming -> job persistido -> worker isolado -> PDF memory-safe -> embeddings reais -> Qdrant -> commit final.

## Configuracao Do Canario

| Campo | Valor |
|---|---|
| limite antes | `MAX_UPLOAD_BYTES=26214400` |
| limite temporario | `MAX_UPLOAD_BYTES=52428800` |
| limite apos teste | `MAX_UPLOAD_BYTES=26214400` |
| PDF | `Semiologia Veterinaria Canary.pdf` |
| tamanho aproximado | `37 MB` |
| workspace | `default` |
| endpoint | `POST /documents/upload` |

## Resultado Do Upload

| Campo | Valor |
|---|---|
| HTTP | `201` |
| status inicial | `queued` |
| ingestion_id | `1eb5a747-2ef5-427a-89d8-b18a2c46bf5f` |
| final_document_id | `5690234b-e711-4f6e-97ff-691a19dd4a51` |
| status final | `committed` |
| paginas | `842` |
| chunks escritos | `2919` |
| pontos Qdrant escritos | `2919` |
| eventos de lote do canario | `842` |
| RSS pico | `159.71 MB` |
| started_at | `2026-05-01T10:55:42.670593Z` |
| finished_at | `2026-05-01T11:10:36.870847Z` |

## Validacao Final

| Check | Resultado |
|---|---|
| raw JSON valido | `true` |
| chunks JSON valido | `true` |
| chunks em arquivo | `2919` |
| pontos Qdrant por `document_id` | `2919` |
| pontos Qdrant por `ingestion_id` | `2919` |
| upload staging removido | `true` |
| backend apos restore | `healthy` |
| frontend/backend systemd | `active` |
| limite restaurado | `MAX_UPLOAD_BYTES=26214400` |

## Health Apos Commit

`/health` retornou:

- `status=healthy`
- `qdrant.points=2940`
- `qdrant.workspace_points=2940`
- `corpus.operational_documents=1`
- `corpus.operational_chunks=2919`
- `telemetry.ingestion_batches.count=863`
- `telemetry.ingestion_batches.errors=0`
- `telemetry.ingestion_batches.rss_peak_mb=159.71`
- `telemetry.ingestion_batches.latest_ingestion_id=1eb5a747-2ef5-427a-89d8-b18a2c46bf5f`

Observacao: o contador `863` em `/health` representa os eventos de lote recentes do workspace `default`; o canario atual gerou `842` eventos, um por pagina.

## Decisao

O canario de upload grande passou. A prova cobre o fluxo real de endpoint e confirma que o upload grande nao travou a VPS.

O limite permanente nao foi liberado nesta execucao. `MAX_UPLOAD_BYTES` foi restaurado para `26214400` ao final do teste.

## Proxima Decisao

Decidir se o ambiente deve:

1. manter `MAX_UPLOAD_BYTES=26214400` e liberar grandes uploads apenas sob demanda; ou
2. promover `MAX_UPLOAD_BYTES=52428800` como limite operacional padrao para uploads grandes.
