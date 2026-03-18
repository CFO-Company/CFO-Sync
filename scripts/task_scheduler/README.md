# Automacao para Task Scheduler

Scripts criados para rodar sem UI, usando as mesmas regras/conectores do app.

## Scripts por plataforma

- `omie_ano_atual.ps1`: `omie_2026` do dia `01/01/ano_atual` ate hoje.
- `omie_ano_anterior.ps1`: `omie_2025` do ano anterior completo.
- `yampi_ultimos_3_meses.ps1`: mes atual + 2 meses anteriores.
- `mercado_livre_ultimos_3_meses.ps1`: mes atual + 2 meses anteriores.
- `meta_ads_dia_anterior.ps1`: somente dia anterior.
- `google_ads_dia_anterior.ps1`: somente dia anterior (com `--allow-missing-platform`).

## Scripts agrupados

- `run_3x_dia.ps1`: Omie ano atual + Omie ano anterior + Yampi + Mercado Livre.
- `run_madrugada_ads.ps1`: Meta Ads + Google Ads.

## Omie 2025

O `omie_2025` usa:

- `secrets/omie_2025.json`

Padrao: o mesmo schema de `secrets/omie_credentials.json`
(`spreadsheet_id` + `companies` com aliases e credenciais).

## Runner base

Todos os `.ps1` chamam o runner:

- `run_platform_sync.py`

Exemplo manual:

```powershell
.\scripts\task_scheduler\invoke_sync.ps1 --platform yampi --period rolling_months --months 3
```

## Logs

Os logs sao gerados em:

- `logs/automation/<plataforma>_AAAA-MM-DD.log`

Inclui:

- erro e traceback
- nao encontrado (plataforma/conector/planilha)
- planilha destino (`spreadsheet_id` e `gid`)
- tempo por tarefa (cliente/recurso)
- alerta de lentidao (`LENTIDAO` e `LENTIDAO_RUN`)

## Configuracao sugerida no Task Scheduler

Acao:

- Program/script: `powershell.exe`
- Add arguments:
  - 3x ao dia: `-ExecutionPolicy Bypass -File "C:\...\CFO-Sync\scripts\task_scheduler\run_3x_dia.ps1"`
  - Madrugada Ads: `-ExecutionPolicy Bypass -File "C:\...\CFO-Sync\scripts\task_scheduler\run_madrugada_ads.ps1"`
- Start in: `C:\...\CFO-Sync`

Gatilhos sugeridos:

- `run_3x_dia.ps1`: `03:00`, `12:00`, `19:00`.
- `run_madrugada_ads.ps1`: `03:30`.
