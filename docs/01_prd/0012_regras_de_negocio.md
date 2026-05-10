# 0012 — Regras de Negócio

## Regras Operacionais

### RN-01: Autenticação
- Todo usuário deve se autenticar antes de acessar o sistema
- Sessões expiram após período configurável
- Credenciais devem ser validadas server-side

### RN-02: Autorização por Role
- **Admin:** Pode gerenciar tenants, usuários, configurações
- **Operator:** Pode fazer upload, queries, visualização
- **Viewer:** Pode fazer queries e visualização

### RN-03: Isolamento de Tenant
- Todo acesso a dados deve filtrar por workspace_id/tenant_id
- Um tenant não pode ver dados de outro tenant
- Filtro de workspace é obrigatório em todas as queries

### RN-04: Upload de Documentos
- Formatos aceitos: PDF, DOCX, MD, TXT
- Tamanho máximo: 50MB
- Documentos são vinculados ao workspace do uploader

### RN-05: Retrieval
- Busca híbrida usa dense + sparse + RRF
- Threshold default operacional: 0.25 para score normalizado de retrieval
- Top-k default: 5

### RN-06: Low Confidence
- Se best_score < threshold, resposta deve indicar "não sei"
- Low confidence deve ser logado

### RN-07: Groundedness
- Resposta deve incluir citações dos chunks usados
- Claims sem citação devem ser indicados

---

## Restrições

### REST-01: Sem autenticacao = Sem acesso
- Endpoints protegidos exigem autenticação válida
- Headers X-Enterprise-* não são mais aceitos como autenticação

### REST-02: Sem workspace_id = Sem query
- Toda query deve ter workspace_id válido
- Queries sem workspace são rejeitadas

### REST-03: Sem role = Sem admin
- Operações de admin requerem role=admin
- Tentativas sem permissão retornam 403

---

## Validações Obrigatórias

### VAL-01: Documento
- Extensão deve ser uma das aceitas
- Magic bytes devem confirmar tipo
- Parse deve extrair texto (não vazio)

### VAL-02: Query
- Query não pode ser vazia
- Query não pode exceder limite configurável
- Workspace_id deve existir

### VAL-03: Autenticacao
- Email deve ser válido format
- Senha deve atender requisitos mínimos
- Sessão deve existir e estar válida

---

## Permissões de Negócio

### PERM-01: Upload
- Roles: admin, operator
- Não viewer

### PERM-02: Query/Busca
- Roles: admin, operator, viewer

### PERM-03: Admin CRUD
- Roles: admin apenas
- Não operator, não viewer

### PERM-04: Métricas
- Roles: admin, operator (viewer limitado)

---

## Próximo Passo

Avançar para 0013_requisitos_funcionais.md
