# PLANO EXECUTIVO — CVG RAG ENTERPRISE PREMIUM

## 1) Objetivo do ciclo

Recuperar a aderência real do programa ao estado de maturidade enterprise, priorizando segurança operacional, consistência de autorização e estabilidade de fluxos críticos, sem mudar escopo funcional principal.

## 2) Estado atual de partida

- Nota consolidada após reconciliação: **79/100**.
- Meta de fechamento: **95/100**.
- Melhorias já validadas: retrieval híbrido, ranking normalizado, expansão de siglas clínicas e abstenção correta em respostas fora de escopo.
- Riscos críticos remanescentes: controle de acesso inconsistente em superfícies sensíveis e falhas pontuais em integração backend→frontend.

## 3) Decisões técnicas e de execução

1. **Não alterar a arquitetura de alto nível do produto nesta rodada.**
2. **Remediar por superfície de risco** (admin/observability → sessão/estado → UX crítica).
3. **Exigir validação por evidência** após cada etapa: suíte pytest completa + Playwright crítico.
4. **Mantêm-se os requisitos de documentação CVG**: atualizar `99_runtime_state.md` e `20_master_execution_log.md` a cada etapa concluída.

## 4) Estratégia por frente

### Frente A — Segurança e autorização (P0)
- Unificar políticas de permissão em rotas administrativas e observability.
- Normalizar resposta de acesso negado para `403` (sem 500 em falhas de permissão).
- Validar isolamento mínimo por workspace em chamadas administrativas por tenant.

### Frente B — Estabilidade de sessão e contratos críticos (P0)
- Fechar comportamento determinístico de `/queries/logs`.
- Corrigir isolamento e isolamento de estado em suíte completa (não apenas testes pontuais).

### Frente C — UX operacional e confiabilidade E2E (P1)
- Corrigir fluxo de upload autenticado e evidência esperada no frontend.
- Confirmar regressão zero em smoke com backend real, sem suposições de sandbox.

### Frente D — Governaça documental (P1)
- Alinhar textos de estado e notas dos gates com evidência de execução real.
- Consolidar lista de gaps e critérios de aceite remanescente.

## 5) Critérios de conclusão do ciclo

- `pytest -q` integral sem falhas em `src/tests`.
- Playwright crítico verde (`frontend/tests/phase2-gate.spec.ts` e cobertura de upload).
- score reconciliado reavaliado para **>= 90** após remediações iniciais.
- estado e log oficiais atualizados para refletir score final e próximos passos.

## 6) Governança de risco

| Risco | Impacto | Mitigação |
|---|---|---|
| Falha de autorização em rota sensível | Alto | Guard explícito por permissão + testes de contrato
| Instabilidade de sessão sob carga de suíte | Médio/alto | Isolamento de setup/teardown e limpeza de state entre testes
| Divergência documento/real | Médio | Bloqueio de avanço de nota sem atualização de estado/log
| Regressão de UX | Médio | Testes E2E obrigatórios por mudança funcional

## 7) Entrega esperada

Um novo estado de maturidade com base executável, sem pendências ocultas, com trilha CVG atualizada e plano de evolução residual para novo ciclo.
