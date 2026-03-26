# CFO Sync 1.0.2

Aplicativo desktop para sincronizacao de dados de plataformas e exportacao para Google Sheets.

## Objetivo de distribuicao

- Usuário final instala e usa sem instalar Python manualmente.
- Atualizacao por botao dentro do app.
- Segredos/API keys fora do binario, no diretório do usuário.

## Onde ficam os dados do usuário

### Windows

- `%LOCALAPPDATA%\CFO-Sync\`

### macOS

- `~/Library/Application Support/CFO-Sync/`

Estrutura criada automaticamente no primeiro start:

- `secrets/`
- `data/`
- `sounds/`

## Secrets e chaves de API

Os templates são copiados automaticamente de `templates/secrets` na primeira execução.

Arquivos relevantes:

- `app_config.json`
- `google_service_account.json`
- `yampi_credentials.json`
- `meta_ads_credentials.json`
- `google_ads_credentials.json`
- `tiktok_ads_credentials.json`
- `omie_credentials.json`
- `mercado_livre_credentials.json`
- `update_config.json`

Regras de seguranca:

- Nunca embutir credenciais reais no executavel/instalador.
- Distribuir apenas templates.
- Entregar credenciais reais por canal seguro para cada analista.
- Salvar sempre em `secrets/` da pasta de usuário.

## Integracao Google Ads no ETL

O conector Google Ads foi integrado no mesmo fluxo atual:

- Extracao: `src/cfo_sync/platforms/google_ads/api.py` + `insights.py`
- Carga local: `SyncPipeline.collect()` -> SQLite (`raw_data`)
- Exportacao: `SyncPipeline.export_to_sheets()` -> `GoogleSheetsExporter`

### Credenciais e variaveis de ambiente

Arquivo recomendado: `secrets/google_ads_credentials.json`

```json
{
  "auth": {
    "developer_token": "SEU_DEVELOPER_TOKEN",
    "client_id": "SEU_OAUTH_CLIENT_ID",
    "client_secret": "SEU_OAUTH_CLIENT_SECRET",
    "refresh_token": "SEU_REFRESH_TOKEN",
    "login_customer_id": "1234567890"
  },
  "accounts": [
    {
      "company_name": "Nome da empresa no CFO Sync",
      "account_name": "Conta Google Ads",
      "customer_id": "1112223334",
      "cost_center": "Marketing",
      "manager_account_name": "MCC Principal"
    }
  ]
}
```

As credenciais sensiveis podem ser sobrescritas por variaveis de ambiente:

- `GOOGLE_ADS_DEVELOPER_TOKEN`
- `GOOGLE_ADS_CLIENT_ID`
- `GOOGLE_ADS_CLIENT_SECRET`
- `GOOGLE_ADS_REFRESH_TOKEN`
- `GOOGLE_ADS_LOGIN_CUSTOMER_ID`
- `GOOGLE_ADS_API_VERSION` (opcional; se definido, fixa uma versao)
- `GOOGLE_ADS_API_VERSION_FALLBACKS` (opcional; ex.: `v22,v21,v20`)

Padrao atual no conector: tenta `v22`, depois `v21`, depois `v20`.

### Exemplo de bloco no `app_config.json`

```json
{
  "google_ads": {
    "credentials_file": "google_ads_credentials.json"
  },
  "platforms": [
    {
      "key": "google_ads",
      "label": "Google Ads",
      "clients": ["Nome da empresa no CFO Sync"],
      "resources": [
        {
          "name": "insights",
          "endpoint": "/customers/{customer_id}/googleAds:searchStream",
          "spreadsheet_url": "https://docs.google.com/spreadsheets/d/SEU_ID/edit#gid=123456",
          "client_tabs": {
            "Nome da empresa no CFO Sync": {
              "tab_name": "Google Ads",
              "gid": "123456"
            }
          },
          "field_map": {
            "nome_ca": "Nome da CA",
            "nome_campanha": "Nome da Campanha",
            "nome_anuncio": "Nome do Anúncio",
            "valor_gasto": "Valor Gasto",
            "data_gasto": "Data do Gasto",
            "tipo_ra": "Tipo (R/A)",
            "centro_custo": "Centro de Custo"
          }
        }
      ]
    }
  ]
}
```

### Colunas padronizadas no Sheets (Google Ads)

- `Nome da CA`
- `Nome da Campanha`
- `Nome do Anúncio`
- `Valor Gasto`
- `Data do Gasto`
- `Tipo (R/A)`
- `Centro de Custo`

Observacao: a API retorna `metrics.cost_micros`; o ETL converte para `valor_gasto` dividindo por `1_000_000`.

### Exemplo de consulta GAQL usada

```sql
SELECT
  segments.date,
  customer.id,
  customer.descriptive_name,
  campaign.id,
  campaign.name,
  metrics.impressions,
  metrics.clicks,
  metrics.cost_micros,
  metrics.conversions
FROM campaign
WHERE segments.date BETWEEN '2026-03-01' AND '2026-03-19'
ORDER BY segments.date ASC, campaign.id ASC
```

### Exemplo de execucao (UI atual)

```powershell
$env:PYTHONPATH="src"
.\.venv\Scripts\python.exe -m cfo_sync.main
```

No seletor de plataforma, escolha `Google Ads`, cliente, recurso (`insights`/`campanhas`/`contas`) e periodo.

## Integracao TikTok Ads no ETL

Arquivo recomendado: `secrets/tiktok_ads_credentials.json`

```json
{
  "auth": {
    "access_token": "SEU_ACCESS_TOKEN",
    "app_id": "SEU_APP_ID",
    "secret": "SEU_SECRET",
    "redirect_uri": "SUA_REDIRECT_URI"
  },
  "accounts": [
    {
      "company_name": "Nome da empresa no CFO Sync",
      "account_name": "Conta TikTok Ads",
      "advertiser_id": "1234567890123456789",
      "cost_center": "Marketing"
    }
  ]
}
```

Variaveis de ambiente opcionais:

- `TIKTOK_ADS_ACCESS_TOKEN` (sobrescreve o token global do arquivo)
- `TIKTOK_ADS_APP_ID` (sobrescreve app_id do arquivo)
- `TIKTOK_ADS_SECRET` (sobrescreve secret do arquivo)
- `TIKTOK_ADS_REDIRECT_URI` (sobrescreve redirect_uri do arquivo)
- `TIKTOK_ADS_API_BASE_URL` (default: `https://business-api.tiktok.com`)

Bloco opcional no `app_config.json`:

```json
{
  "tiktok_ads": {
    "credentials_file": "tiktok_ads_credentials.json"
  }
}
```

Validar conexao e advertiser IDs configurados:

```powershell
$env:PYTHONPATH="src"
.\.venv\Scripts\python.exe -m cfo_sync.platforms.tiktok_ads.oauth --credentials secrets/tiktok_ads_credentials.json
```

Fluxo recomendado para projeto local-first (sem backend externo): callback local em `127.0.0.1`.

```powershell
$env:PYTHONPATH="src"
.\.venv\Scripts\python.exe -m cfo_sync.platforms.tiktok_ads.oauth --credentials secrets/tiktok_ads_credentials.json --run-local-callback --open-browser
```

No app TikTok, a `redirect_uri` deve ser exatamente a URL exibida no comando (padrao: `http://127.0.0.1:8765/tiktok/callback`).

Atualizar token manualmente e validar:

```powershell
$env:PYTHONPATH="src"
.\.venv\Scripts\python.exe -m cfo_sync.platforms.tiktok_ads.oauth --credentials secrets/tiktok_ads_credentials.json --access-token "SEU_TOKEN"
```

Callback OAuth com backend proprio (producao): veja `tools/tiktok_oauth_callback/README.md`.

## Botao de atualizar app

O launcher possui:

- `Atualizar app`: consulta o `latest release` no GitHub, baixa o asset da plataforma e inicia instalador.
- `Abrir pasta de config`: abre a pasta `secrets` para facilitar colagem/edicao de credenciais.

Configure `secrets/update_config.json`:

```json
{
  "enabled": true,
  "github_repo": "OWNER/REPO",
  "windows_asset_name": "CFO-Sync-Setup.exe",
  "macos_asset_name": "CFO-Sync-macOS.dmg"
}
```

## Build local - Windows

Pre-requisitos:

- Windows
- `.venv` no projeto
- Inno Setup instalado (opcional; sem ele o script gera um executavel unico `CFO-Sync-Setup.exe`)

Comando:

```powershell
.\tools\build_windows_package.ps1
```

Saídas:

- `dist\installer\CFO-Sync-Setup.exe`

## Pipeline de release no GitHub

Arquivo:

- `.github/workflows/release.yml`

Ao criar tag `X.Y.Z`, o workflow:

- gera build Windows com PyInstaller
- publica a release da tag
- anexa o asset Windows na release (`CFO-Sync-Setup.exe`)
- usa a secao da versao no `CHANGELOG.md` como corpo da release

## Changelog

Arquivo principal:

- `CHANGELOG.md`

Formato adotado:

- `## [Unreleased]` para mudancas em desenvolvimento
- `## [X.Y.Z] - AAAA-MM-DD` para versao publicada

Script utilitario:

```bash
python tools/changelog_extract.py --version 1.0.2
```

Para cada nova release:

1. Atualize `CHANGELOG.md` com a secao da nova versao.
2. Crie a tag `X.Y.Z`.
3. O workflow publica a release usando essa secao como release notes.

## Fluxo sugerido para analistas

1. Instalar via setup do Windows.
2. Abrir app.
3. Clicar em `Abrir pasta de config`.
4. Colar/preencher os arquivos em `secrets`.
5. Usar normalmente.
6. Quando houver release nova, clicar em `Atualizar app`.

## Automacao via Task Scheduler

Scripts de automacao por plataforma:

- `scripts/task_scheduler/`

Documentacao:

- `scripts/task_scheduler/README.md`
