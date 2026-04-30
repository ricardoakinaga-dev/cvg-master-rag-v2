# 2026-04-29 - GAP-06/GAP-07 CORS e Cookies

## Objetivo

Executar:

- `GAP-06 - Testar CORS permitido e negado por ambiente`.
- `GAP-07 - Verificar atributos de cookie por ambiente`.

## Falha Reproduzida

Antes do hardening, o teste novo identificou que `CORS_ALLOWED_ORIGINS=*,https://console.example.com` com `CORS_ALLOW_CREDENTIALS=true` mantinha o wildcard ativo:

```text
pytest -q src/tests/test_cors_security.py
1 failed, 6 passed
```

Falha raiz:

- wildcard `*` permanecia em `allowed_cors_origins` mesmo com credenciais habilitadas.

## Correcoes Aplicadas

| Arquivo | Mudanca |
|---|---|
| `src/core/config.py` | Centralizada a leitura booleana de env vars. |
| `src/core/config.py` | `CORS_ALLOWED_ORIGINS` agora remove `*` quando `CORS_ALLOW_CREDENTIALS=true`. |
| `src/core/config.py` | Adicionadas configuracoes `SESSION_COOKIE_SECURE` e `SESSION_COOKIE_SAMESITE`. |
| `src/api/main.py` | Cookies de sessao passaram a usar politica centralizada de config. |
| `src/tests/test_cors_security.py` | Testes de CORS por ambiente, wildcard com credenciais e cookies seguro/local. |
| `src/.env.example` | Documentadas variaveis de cookie para dev/smoke/producao. |
| `src/README.md` | Documentada politica operacional de CORS/cookies. |

## Politica Final

- CORS permite apenas origens explicitamente configuradas.
- Origem desconhecida nao recebe `access-control-allow-origin`.
- Wildcard `*` e removido quando `CORS_ALLOW_CREDENTIALS=true`.
- Cookie de sessao sempre usa `HttpOnly`.
- Cookie de sessao usa `SameSite=lax` por padrao.
- Cookie de sessao usa `Secure=true` por padrao.
- `SESSION_COOKIE_SECURE=false` e permitido apenas para HTTP local/dev/smoke.

## Validacoes

```text
pytest -q src/tests/test_cors_security.py
7 passed
```

```text
pytest -q src/tests/test_cors_security.py src/tests/test_sprint5.py::test_cookie_session_preferred_over_authorization_header_for_admin_routes src/tests/test_p0_closeout.py::test_admin_password_reset_token_can_rotate_credentials_and_revoke_old_sessions
9 passed
```

```text
python3 src/scripts/scan_secrets.py
Secret scan passed: no high-signal secrets found.
```

```text
pytest -q -rs src/tests
245 passed, 15 skipped in 123.66s
```

Os 15 skips da suite local dependem de Qdrant ativo no ambiente. A validacao live com Qdrant foi executada no GAP-03 com `253 passed`.

## Decisao

`GAP-06` esta **DONE**.

`GAP-07` esta **DONE**.

Score operacional permanece `97/100`, porque o criterio de `98/100` ainda depende do fechamento de `GAP-08`.

Proximo passo oficial: `GAP-08 - Avaliar Gitleaks como scanner complementar`.
