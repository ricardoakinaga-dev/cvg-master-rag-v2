# 2026-04-30 - E2E Smoke Estabilizado

## Escopo

Resolver o bloqueio identificado em `docs/04_audit/2026-04-30-verificacao-roadmap-gaps-98-100.md`, onde o Playwright smoke falhava no cenário `rotas principais renderizam no desktop`.

## Causa Raiz

O smoke usava `next dev` com `NEXT_DIST_DIR=.next-playwright`. Durante o primeiro ciclo de navegacao, o Next compilava rotas sob demanda e disparava Fast Refresh/full reload. Isso remonta o shell de sessao durante a validacao Playwright e podia deixar a pagina em `Carregando sessão` ou voltar para login.

## Correcao

| Arquivo | Mudanca |
|---|---|
| `frontend/playwright.config.ts` | Frontend do smoke passou a executar `next build` em `.next-playwright` e depois `next start` em `127.0.0.1:3015`. |
| `frontend/README.md` | Documentada a politica do smoke com build de producao isolado. |

## Validacoes

```text
npm run test:smoke -- tests/phase2-gate.spec.ts -g "rotas principais renderizam no desktop"
1 passed
```

```text
npm run test:smoke
7 passed
```

```text
npm exec -- tsc --noEmit
passou
```

```text
npm run lint
passou
```

## Decisao

O bloqueio E2E esta resolvido.

O programa volta ao estado `READY_FOR_NEXT_STEP`, com score operacional `98/100`, mantendo como proximo passo oficial `GAP-09/GAP-10`: plano e primeiro corte de desacoplamento de `src/api/main.py`.
