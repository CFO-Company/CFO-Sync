# Runbook de Release e Deploy

Este documento e o procedimento obrigatorio para publicar uma nova versao do
CFO Sync e atualizar o servidor Docker. A ordem dos passos evita os erros
recorrentes de build quebrada por `CHANGELOG.md`, tags conflitantes e servidor
rodando commit antigo.

## Principios

- Nunca criar tag antes de validar `CHANGELOG.md` para a versao.
- Nunca usar `git fetch --tags` no servidor de producao; ha tags antigas que
  podem conflitar com tags locais.
- `secrets/*.json` nao entra no Git. Configuracao de runtime deve ser aplicada
  no servidor via pasta `C:\srv\secrets` ou API de secrets.
- O healthcheck precisa mostrar a versao e commit esperados depois do deploy.
- Docker deve ser recriado pelo script oficial `settings/setup_docker_server.ps1`.

## 1. Checklist Antes da Tag

Defina a versao alvo:

```powershell
$version = "1.3.19"
```

Atualize obrigatoriamente:

- `pyproject.toml`
- `src/cfo_sync/version.py`
- trecho de exemplo de health no `README.md`, quando existir
- `CHANGELOG.md`

O `CHANGELOG.md` precisa ter uma secao exatamente neste formato:

```markdown
## [1.3.19] - 20-05-2026

### Added
- ...

### Changed
- ...
```

Antes de commitar, rode a mesma validacao usada pela GitHub Action:

```powershell
$env:PYTHONPATH = "src"
py tools\changelog_extract.py --version $version --changelog CHANGELOG.md
```

Se esse comando falhar, a build da release tambem vai falhar. Corrija antes de
seguir.

Rode os testes:

```powershell
$env:PYTHONPATH = "src"
py -m unittest discover -s tests
```

## 2. Commit, Merge e Tag

Crie o commit na branch da versao:

```powershell
git status --short --branch
git add README.md CHANGELOG.md pyproject.toml src\cfo_sync\version.py src tests
git commit -m "Prepare $version release"
git push origin $version
```

Merge para `main`:

```powershell
git switch main
git pull --ff-only origin main
git merge --no-ff $version -m "Merge release $version"
```

Rode novamente as validacoes em `main`:

```powershell
$env:PYTHONPATH = "src"
py tools\changelog_extract.py --version $version --changelog CHANGELOG.md
py -m unittest discover -s tests
```

Publique `main`:

```powershell
git push origin main
```

Crie a tag somente depois das validacoes acima:

```powershell
git tag -a $version -m "Release $version"
git push origin refs/tags/$version
```

Use `refs/tags/$version` porque geralmente existe uma branch com o mesmo nome
da versao. Isso evita o erro:

```text
src refspec 1.3.x matches more than one
```

## 3. Se a Release Quebrar Por CHANGELOG

Erro tipico:

```text
ValueError: Versao 1.3.19 nao encontrada em CHANGELOG.md
```

Corrija em `main`:

```powershell
$version = "1.3.19"

git switch main
# editar CHANGELOG.md e adicionar ## [$version]

$env:PYTHONPATH = "src"
py tools\changelog_extract.py --version $version --changelog CHANGELOG.md
py -m unittest discover -s tests

git add CHANGELOG.md
git commit -m "Add $version changelog entry"
git push origin main
```

Mova a tag para o commit corrigido:

```powershell
git tag -f -a $version -m "Release $version"
git push --force origin refs/tags/$version
```

Atualize a release no GitHub ou recrie a release se necessario.

## 4. Atualizar o Repositorio no Servidor

No servidor Windows:

```powershell
cd C:\CFO-Sync

git fetch --no-tags origin +refs/heads/main:refs/remotes/origin/main
git checkout main
git merge --ff-only origin/main

git rev-parse --short HEAD
git log -1 --oneline
```

Nao use:

```powershell
git fetch origin --tags
```

Esse comando pode falhar com:

```text
would clobber existing tag
```

## 5. Recriar Servidor Docker

Confirme que os arquivos persistidos existem:

```powershell
Test-Path C:\srv\secrets\app_config.json
Test-Path C:\srv\cfo_sync\server_access.json
Test-Path C:\CFO-Sync\settings\docker-server.env
```

Recrie pelo bootstrap oficial:

```powershell
cd C:\CFO-Sync

docker compose --env-file .\settings\docker-server.env -f .\settings\docker-compose.server.yml down

.\settings\setup_docker_server.ps1 `
  -HostRoot "C:\srv" `
  -Port 8088 `
  -Workers 2 `
  -WithTunnel `
  -TunnelHostname "api.ecfo.com.br"
```

Se o script pedir token do Cloudflare:

```powershell
.\settings\setup_docker_server.ps1 `
  -HostRoot "C:\srv" `
  -Port 8088 `
  -Workers 2 `
  -WithTunnel `
  -TunnelToken "SEU_TOKEN_CLOUDFLARE" `
  -TunnelHostname "api.ecfo.com.br"
```

Verifique containers:

```powershell
docker compose --env-file .\settings\docker-server.env -f .\settings\docker-compose.server.yml ps
```

## 6. Validacao Pos-Deploy

Local:

```powershell
irm "http://localhost:8088/v1/health"
```

Publico:

```powershell
irm "https://api.ecfo.com.br/v1/health"
```

Os campos precisam bater com a versao publicada:

```text
version      : 1.3.19
build_branch : main
build_commit : <commit atual do main>
```

Se o commit estiver antigo, o container nao foi recriado. Rode novamente o
bootstrap Docker.

Se `localhost:8088` funcionar e a URL publica der `502`, veja o tunnel:

```powershell
docker compose --env-file .\settings\docker-server.env -f .\settings\docker-compose.server.yml logs -f cfo-sync-tunnel
```

Se `localhost:8088` falhar, veja o servidor:

```powershell
docker compose --env-file .\settings\docker-server.env -f .\settings\docker-compose.server.yml logs -f cfo-sync-server
```

## 7. Atualizar Secrets no Servidor

Arquivos em `secrets/*.json` sao ignorados pelo Git. Para alterar runtime config
sem entrar no container, use a API com um token que tenha `can_manage_secrets`.

Listar arquivos:

```powershell
$token = "TOKEN_ADMIN"
$headers = @{ Authorization = "Bearer $token" }
irm "https://api.ecfo.com.br/v1/secrets/files" -Headers $headers
```

Ler arquivo:

```powershell
irm "https://api.ecfo.com.br/v1/secrets/file?path=app_config.json" -Headers $headers
```

Atualizar arquivo a partir de um JSON local:

```powershell
$token = "TOKEN_ADMIN"
$headers = @{ Authorization = "Bearer $token" }
$content = Get-Content "C:\caminho\app_config.json" -Raw
$body = @{
  path = "app_config.json"
  content = $content
} | ConvertTo-Json -Depth 20

irm "https://api.ecfo.com.br/v1/secrets/file" `
  -Method Post `
  -Headers $headers `
  -ContentType "application/json" `
  -Body $body
```

Quando o arquivo atualizado for `app_config.json`, o servidor recarrega a config
automaticamente. Mesmo assim, valide:

```powershell
irm "https://api.ecfo.com.br/v1/catalog/reload" -Method Post -Headers $headers
```

## 8. Checklist Final

- `CHANGELOG.md` tem `## [versao]`.
- `py tools\changelog_extract.py --version versao` passa.
- `py -m unittest discover -s tests` passa.
- `main` esta no commit esperado.
- Tag aponta para o commit esperado.
- Docker foi recriado com `setup_docker_server.ps1`.
- Health local e publico mostram versao/commit novos.
- Secrets necessarios foram aplicados via `C:\srv\secrets` ou API.
