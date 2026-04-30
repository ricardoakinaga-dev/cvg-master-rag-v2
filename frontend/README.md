# Frontend Canônico

Este diretório é o frontend canônico da **Fase 2 — Produto Premium**.

## Status

- app ativo do produto
- integrado ao backend em `src/api/main.py`
- cobre documentos, busca, chat, dashboard e auditoria
- já inclui a fundação enterprise do `Sprint G1` com login, sessão, tenant e `/admin`
- shell responsivo com navegação desktop e drawer mobile
- validado com lint, build e `npm run test:smoke`

## Comandos

```bash
npm install
npm run dev
npm run lint
npm run build
npm run test:smoke
```

## Variáveis

Use `NEXT_PUBLIC_API_BASE_URL` para apontar o backend.

Exemplo:

```bash
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

## Observação

Não existe uma segunda base de frontend ativa neste repositório. Use apenas `frontend/` como implementação principal.

## Execução local

- use `NEXT_PUBLIC_API_BASE_URL` para apontar o backend local
- a interface principal cobre documentos, busca, chat, dashboard e auditoria sem depender de Swagger para a rotina normal
- a navegação lateral vira drawer em telas reduzidas
- o smoke test sobe backend isolado em `8010` e frontend isolado em `3015`
- o smoke cria um build de produção em `NEXT_DIST_DIR=.next-playwright` e sobe `next start`, evitando Fast Refresh/lazy compilation durante o gate E2E
