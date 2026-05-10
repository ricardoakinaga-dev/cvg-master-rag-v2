# Logs Audit - Indexing 400MB

## Kernel

Consulta desde `2026-05-01 16:20 UTC` nao retornou:

- `oom`
- `killed process`
- `out of memory`
- `memory cgroup`

## Worker

Canario final:

- `ingestion_id=5e084499-7c84-435e-9c79-2bcd976bd7af`
- `status=committed`
- `rss_peak_mb=418.52`
- `error_code=null`
- `error_message=null`

## Resultado

Sem evidencia de OOM, morte por cgroup ou falha de worker no canario final.
