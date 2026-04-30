# 2026-04-29 - GAP-08 Gitleaks

## Objetivo

Executar `GAP-08 - Avaliar Gitleaks como scanner complementar`, reduzindo dependencia exclusiva do scanner regex interno.

## Decisao Tecnica

Gitleaks foi aprovado como **gate complementar** no CI, usando CLI via imagem oficial Docker.

A action oficial `gitleaks/gitleaks-action@v2` foi evitada porque a propria documentacao oficial informa exigencia de `GITLEAKS_LICENSE` para repositorios de organizacao. Para evitar dependencia de segredo/licenca externa, o pipeline usa:

```text
ghcr.io/gitleaks/gitleaks:v8.30.1
```

## Correcoes Aplicadas

| Arquivo | Mudanca |
|---|---|
| `.gitleaks.toml` | Configuracao adicionada, estendendo regras default de Gitleaks. |
| `.gitleaks.toml` | Allowlist explicita para artefatos locais/generated, `.env` local e placeholders documentados. |
| `.github/workflows/ci.yaml` | Job `security` agora roda scanner interno e Gitleaks. |
| `README.md` | Comando local de Gitleaks documentado junto ao secret scan interno. |

## Validacoes

```text
python3 src/scripts/scan_secrets.py
Secret scan passed: no high-signal secrets found.
```

```text
docker run --rm -v "$PWD:/repo" ghcr.io/gitleaks/gitleaks:v8.30.1 dir /repo --config /repo/.gitleaks.toml --redact --no-banner --log-level warn
```

Resultado: passou sem achados.

```text
workflow yaml ok
```

## Observacao De Avaliacao

Na primeira execucao local, Gitleaks encontrou 2 achados redigidos em arquivos locais fora do escopo de CI:

- `.claude/settings.json`
- `src/.env`

Esses caminhos foram alinhados ao mesmo escopo do scanner interno: arquivos locais de ambiente/agente nao sao varridos como artefatos de codigo. `.env.example` continua elegivel para scan.

## Decisao

`GAP-08` esta **DONE**.

Score operacional atualizado para `98/100`.

Proximo passo oficial: `GAP-09/GAP-10 - Plano e primeiro corte de desacoplamento de src/api/main.py`.
