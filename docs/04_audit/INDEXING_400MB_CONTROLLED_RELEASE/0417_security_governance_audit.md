# Security Governance Audit - Indexing 400MB

## Controles

- Upload permanece autenticado/autorizado pelo backend existente.
- API publica fica sob `/api/*`, evitando colisao com paginas do frontend.
- `MAX_UPLOAD_BYTES=524288000` impede uploads ilimitados.
- Preflight bloqueia disco insuficiente, Qdrant indisponivel e concorrencia grande acima de 1.
- Worker roda isolado de Uvicorn.

## Riscos

- Sem novo segredo ou dependencia adicionada nesta auditoria.
- `.env` contem configuracoes operacionais existentes; nao foi necessario criar nova credencial.

## Resultado

Governanca suficiente para release controlado de 500MiB. Aumento futuro acima desse limite exige novo ciclo SPEC/BUILD.
