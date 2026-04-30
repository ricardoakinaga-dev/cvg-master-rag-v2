# CVG RAG Enterprise Premium

Sistema RAG enterprise orientado pelo processo CVG:

`DISCOVERY -> PRD -> SPEC -> BUILD -> AUDIT`

## Status Atual

- Backend FastAPI validado com `pytest -q src/tests`
- Frontend Next.js validado com lint, build e smoke Playwright
- Smoke E2E cobre login, rotas principais, upload, troca de tenant, busca, chat e tablet
- Secret scanning dedicado disponível em `src/scripts/scan_secrets.py` e Gitleaks complementar no CI
- Migrations documentadas em `docs/03_build/0310_MIGRATIONS.md`

Validação mais recente:

```bash
pytest -q src/tests
python3 src/scripts/scan_secrets.py
docker run --rm -v "$PWD:/repo" ghcr.io/gitleaks/gitleaks:v8.30.1 dir /repo --config /repo/.gitleaks.toml --redact --no-banner --log-level warn
cd frontend && npm run lint && npm run build && npm run test:smoke
```

## Estrutura

```text
docs/               Documentação CVG, gates, auditorias, roadmap e backlog
src/                Backend FastAPI, serviços RAG, scripts e testes Python
frontend/           Frontend Next.js canônico
.github/workflows/  CI com secret scan, backend smoke, lint, typecheck e build
```

## Execução Local

Backend:

```bash
cd src
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn api.main:app --reload --host 127.0.0.1 --port 8000
```

Frontend:

```bash
cd frontend
npm install
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000 npm run dev
```

## Testes

Backend offline:

```bash
pytest -q src/tests
```

Secret scan:

```bash
python3 src/scripts/scan_secrets.py
docker run --rm -v "$PWD:/repo" ghcr.io/gitleaks/gitleaks:v8.30.1 dir /repo --config /repo/.gitleaks.toml --redact --no-banner --log-level warn
```

Frontend:

```bash
cd frontend
npm run lint
npm run build
npm run test:smoke
```

## Testes Live com Qdrant

Alguns testes de consistência do corpus exigem Qdrant acessível em `QDRANT_HOST:QDRANT_PORT`.

Comando padrão local, usando portas isoladas para não interferir em uma instância local já existente na `6333`:

```bash
docker run -d --rm \
  --name cvg-qdrant-local \
  -p 6337:6333 \
  -p 6338:6334 \
  qdrant/qdrant:v1.11.5

curl -fsS http://127.0.0.1:6337/readyz

cd src
QDRANT_HOST=127.0.0.1 QDRANT_PORT=6337 python3 scripts/reindex_corpus.py default
QDRANT_HOST=127.0.0.1 QDRANT_PORT=6337 pytest -q -rs tests

docker stop cvg-qdrant-local
```

O reindex usa embeddings offline determinísticas quando `OPENAI_API_KEY` não está configurada.

No CI, o job `smoke-tests` sobe Qdrant como serviço.

## Migrations

O projeto ainda não usa banco relacional nem Alembic. O estado persistente atual fica em filesystem (`src/data/**`, `src/logs/**`) e Qdrant. A política operacional está em:

- `docs/03_build/0310_MIGRATIONS.md`

Qualquer mudança futura de schema em JSON, corpus, logs, Qdrant payload ou storage relacional deve seguir essa política antes de entrar em produção.

## Documentação Canônica

- Estado runtime: `docs/99_runtime_state.md`
- Log mestre: `docs/20_master_execution_log.md`
- Backlog: `docs/30_backlog_master.md`
- Auditorias: `docs/04_audit/`
