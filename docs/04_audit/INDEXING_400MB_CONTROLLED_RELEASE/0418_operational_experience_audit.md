# Operational Experience Audit - Indexing 400MB

## Experiencia Operacional

- Frontend `/documents` mostra jobs recentes.
- Status de job inclui progresso, chunks, pontos, RSS, isolamento, heartbeat, throughput e alerta operacional.
- Se polling atrasar, UI preserva ultimo estado valido e mostra atraso em vez de falha definitiva.
- Health leve evita travamento visual causado por inventario/contagens pesadas.

## Resultado

Operacao adequada para uploads reais ate 500MiB com monitoramento humano.

## Residual

Para escala acima de 500MiB, implementar shards JSONL antes de aumentar limite.
