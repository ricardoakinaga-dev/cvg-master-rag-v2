# BACKLOG EXECUTIVO — CVG RAG Enterprise Premium

## P0 — Bloqueador (deve ficar verde para score real avançar)

### BE-01 — Unificar política de autorização admin/observability
- **Descrição:** padronizar requisitos de permissão em `/admin/*` e rotas observability, removendo inconsistências de acesso.
- **Critério de aceite:** cenários de operador/role não autorizado devem retornar `403` em todas as rotas sensíveis sem exceção.
- **Dependência:** análise de contratos de rota em `src/api/main.py`.
- **Risco:** Alto
- **Artefatos:** `src/api/main.py`, `src/services/api_security.py`

### BE-02 — Corrigir erro de autorização encapsulado em 500
- **Descrição:** garantir que falhas de `permission denied` não gerem 500 por exceção interna.
- **Critério de aceite:** nenhum teste de autorização válido retorna `500` por falta de permissão.
- **Dependência:** BE-01
- **Risco:** Alto

### BE-03 — Estabilizar `/queries/logs`
- **Descrição:** eliminar retorno 401 não determinístico sob suíte completa e garantir estado consistente.
- **Critério de aceite:** `pytest -q` sem falhas no cenário de lista de logs.
- **Dependência:** testes de integração + isolamento de sessão

### BE-04 — Corrigir fluxo autenticado de upload no Playwright
- **Descrição:** fechar evidência de upload com sessão ativa e retorno visual esperado no fluxo `/documents`.
- **Critério de aceite:** Playwright crítico passa com evidência explícita de upload concluído.
- **Dependência:** BE-03
- **Risco:** Alto

## P1 — Importante (melhoria de confiança)

### BE-05 — Remediar divergência de nota documental e evidência
- **Descrição:** atualizar `docs/99_runtime_state.md` e `docs/20_master_execution_log.md` com score reconciliado após remediação.
- **Critério de aceite:** score público igual a score validado de execução (sem divergência interna).
- **Dependência:** fechamento dos P0

### BE-06 — Reforçar suíte de contratos auth/observability
- **Descrição:** adicionar testes de regressão para rotas `/admin/*`, `/observability/*` e contratos de sessão.
- **Critério de aceite:** suíte cobre todos os fluxos de acesso críticos sem supor comportamento implícito.

### BE-07 — Revisar hardening de CORS para produção interna
- **Descrição:** reduzir superfície de origem aberta e definir política por ambiente.
- **Critério de aceite:** política por ambiente explicitada e validada por teste de preflight.
- **Dependência:** BE-01

## P2 — Melhoria contínua

### BE-08 — Reduzir acoplamento `src/api/main.py`
- **Descrição:** extrair dependências de roteamento para módulos com responsabilidades delimitadas.
- **Critério de aceite:** PR inicial com redução de complexidade (sem quebra funcional).

### BE-09 — Endurecimento de frontend session store
- **Descrição:** migrar gradualmente token bearer para fonte primária cookie HttpOnly.
- **Critério de aceite:** login/logout funcionais com fallback compat.

### BE-10 — Revisão contínua do corpus canônico/operacional
- **Descrição:** reduzir ruído operacional e melhorar auditabilidade do inventário de documentos por workspace.
- **Critério de aceite:** checklist de higiene operacional com evidência de redução de resíduos.

## Entregáveis de aceitação do backlog

- Reexecução completa de `pytest -q` e `pnpm test:smoke` sem falhas.
- `current_score` e `assessed_score` consistentes em estado/log oficiais.
- Sem regressão de funcionalidade de retrieval/query.
- Roadmap de sprint atualizado com status por item.
