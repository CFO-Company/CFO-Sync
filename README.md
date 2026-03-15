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
- `omie_credentials.json`
- `mercado_livre_credentials.json`
- `update_config.json`

Regras de seguranca:

- Nunca embutir credenciais reais no executavel/instalador.
- Distribuir apenas templates.
- Entregar credenciais reais por canal seguro para cada analista.
- Salvar sempre em `secrets/` da pasta de usuário.

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
- Inno Setup instalado (para gerar setup)

Comando:

```powershell
.\tools\build_windows_package.ps1
```

Saídas:

- `dist\installer\CFO-Sync-Setup.exe`

## Build local - macOS

Pre-requisitos:

- macOS
- `.venv` no projeto

Comando:

```bash
chmod +x ./tools/build_macos_package.sh
PYTHON_EXE=.venv/bin/python ./tools/build_macos_package.sh
```

Saídas:

- `dist/installer/CFO-Sync-macOS.dmg`

## Pipeline de release no GitHub

Arquivo:

- `.github/workflows/release.yml`

Ao criar tag `X.Y.Z`, o workflow:

- builda Windows + macOS
- gera pacotes em `dist/installer`
- publica os assets na release da tag
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

1. Instalar via setup do Windows ou DMG no macOS.
2. Abrir app.
3. Clicar em `Abrir pasta de config`.
4. Colar/preencher os arquivos em `secrets`.
5. Usar normalmente.
6. Quando houver release nova, clicar em `Atualizar app`.
