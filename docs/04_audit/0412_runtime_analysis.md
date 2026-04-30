# 0412 - RUNTIME ANALYSIS

## Resultado

Runtime funcional em ambiente local auditavel.

## Gates De Runtime

| Gate | Resultado |
|---|---|
| Backend sem Qdrant live | `245 passed, 15 skipped` |
| Backend com Qdrant live | `260 passed` |
| Qdrant reindex canonico | 5 documentos, 11 pontos, verificacao PASS |
| Frontend build | passou |
| Playwright smoke | `7 passed` |

## Qdrant Live

Ambiente usado:

- imagem: `qdrant/qdrant:v1.11.5`
- container temporario: `cvg-qdrant-local`
- porta HTTP: `6337`
- porta gRPC: `6338`

O container foi parado apos a validacao.

## Interpretacao

Os 15 skips observados no gate sem Qdrant sao de ambiente, nao de produto. A auditoria final executou o mesmo backend contra Qdrant live e fechou `260 passed`, eliminando a ressalva operacional para score final.
