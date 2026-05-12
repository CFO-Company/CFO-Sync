# Infra e deploy dos ambientes

Este documento registra como o CFO Sync Server esta publicado e como validar
uma versao em staging antes de promover para producao.

## Ambientes atuais

| Ambiente | URL publica | Porta local | Container | Host root |
| --- | --- | --- | --- | --- |
| Producao | `https://api.ecfo.com.br/` | `127.0.0.1:8088` | `cfo-sync-server` | `C:\srv` |
| Staging | `https://staging-api.ecfo.com.br/` | `127.0.0.1:8089` | `cfo-sync-server-staging` | `C:\srv-staging` |

No Cloudflare Tunnel, os public hostnames devem ficar assim:

| Hostname | Service URL |
| --- | --- |
| `api.ecfo.com.br` | `http://127.0.0.1:8088` |
| `staging-api.ecfo.com.br` | `http://127.0.0.1:8089` |

Nao aponte staging para `127.0.0.1:8088`. Essa porta e producao.

## Publicacao no seletor do desktop

O endpoint `GET /v1/runtime/versions` da producao publica quais ambientes o
desktop pode selecionar. O valor vem de `CFO_SYNC_RUNTIME_VERSIONS` no arquivo
`settings\docker-server.env` da producao.

Valor esperado:

```powershell
$runtimeVersions = '{"production":"https://api.ecfo.com.br/","staging":"https://staging-api.ecfo.com.br/"}'
```

Para atualizar a publicacao:

```powershell
cd C:\CFO-Sync

$runtimeVersions = '{"production":"https://api.ecfo.com.br/","staging":"https://staging-api.ecfo.com.br/"}'

@(
  "CFO_SYNC_HOST_ROOT=C:/srv"
  "CFO_SYNC_SERVER_PORT=8088"
  "CFO_SYNC_WORKERS=2"
  "CFO_SYNC_RUNTIME_VERSIONS=$runtimeVersions"
) | Set-Content -LiteralPath ".\settings\docker-server.env" -Encoding ascii

docker compose --env-file ".\settings\docker-server.env" -f ".\settings\docker-compose.server.yml" up -d --force-recreate cfo-sync-server
```

O token que pode trocar ambiente precisa ter:

```json
"can_select_server_version": true,
"allowed_server_versions": []
```

Lista vazia em `allowed_server_versions` significa: liberar todas as versoes
publicadas pelo servidor. Use lista preenchida apenas quando quiser restringir
um token a nomes especificos.

## Validacao rapida

Depois de qualquer mudanca de infra, valide os quatro endpoints:

```powershell
irm "http://127.0.0.1:8088/v1/health"
irm "http://127.0.0.1:8089/v1/health"
irm "https://api.ecfo.com.br/v1/health"
irm "https://staging-api.ecfo.com.br/v1/health"
```

Todos devem responder `status: ok`.

Valide tambem o seletor:

```powershell
$token = "TOKEN_ADMIN"

irm "https://api.ecfo.com.br/v1/runtime/versions" -Headers @{
  Authorization = "Bearer $token"
} | ConvertTo-Json -Depth 10
```

A resposta deve conter `production` e `staging`.

## Criar staging em um servidor novo

Crie primeiro o ambiente local na porta `8089`. So depois configure o hostname
no Cloudflare apontando para essa porta.

```powershell
cd C:\CFO-Sync

Copy-Item ".\settings\docker-compose.server.yml" ".\settings\docker-compose.staging.yml" -Force

(Get-Content ".\settings\docker-compose.staging.yml" -Raw).Replace("container_name: cfo-sync-server", "container_name: cfo-sync-server-staging") | Set-Content ".\settings\docker-compose.staging.yml" -Encoding utf8

@(
  "CFO_SYNC_HOST_ROOT=C:/srv-staging"
  "CFO_SYNC_SERVER_PORT=8089"
  "CFO_SYNC_WORKERS=2"
) | Set-Content -LiteralPath ".\settings\docker-staging.env" -Encoding ascii

New-Item -ItemType Directory -Force -Path "C:\srv-staging\secrets","C:\srv-staging\cfo_sync","C:\srv-staging\data"
Copy-Item "C:\srv\secrets\app_config.json" "C:\srv-staging\secrets\app_config.json"
Copy-Item "C:\srv\cfo_sync\server_access.json" "C:\srv-staging\cfo_sync\server_access.json"

$svc = "cfo-sync-server"
docker compose --env-file ".\settings\docker-staging.env" -f ".\settings\docker-compose.staging.yml" -p cfo-sync-staging build $svc
docker compose --env-file ".\settings\docker-staging.env" -f ".\settings\docker-compose.staging.yml" -p cfo-sync-staging up -d --force-recreate $svc

Start-Sleep -Seconds 5
irm "http://127.0.0.1:8089/v1/health"
```

Depois que `127.0.0.1:8089` responder `ok`, configure no Cloudflare:

```text
staging-api.ecfo.com.br -> http://127.0.0.1:8089
```

## Deploy de uma branch para staging

O fluxo de validacao antes da producao e:

1. Atualizar o codigo local do servidor para a branch que sera testada.
2. Rebuildar e recriar apenas o container de staging.
3. Validar `staging-api.ecfo.com.br`.
4. Se aprovado, fazer merge da branch em `main`.
5. Atualizar o codigo para `main`.
6. Rebuildar e recriar producao.

Comandos para staging:

```powershell
cd C:\CFO-Sync

git fetch origin
git switch NOME_DA_BRANCH
git pull

docker compose --env-file ".\settings\docker-staging.env" -f ".\settings\docker-compose.staging.yml" -p cfo-sync-staging build cfo-sync-server
docker compose --env-file ".\settings\docker-staging.env" -f ".\settings\docker-compose.staging.yml" -p cfo-sync-staging up -d --force-recreate cfo-sync-server

Start-Sleep -Seconds 5
irm "https://staging-api.ecfo.com.br/v1/health"
```

Observacao importante: hoje staging e producao podem ser buildados a partir da
mesma pasta `C:\CFO-Sync`. O container de producao em execucao nao muda apenas
por trocar a branch no disco, porque o codigo foi copiado para a imagem no
build. Mesmo assim, antes de rebuildar producao, confirme que a pasta esta na
branch correta (`main`).

## Promocao para producao

Depois de validar staging e concluir o merge para `main`:

```powershell
cd C:\CFO-Sync

git fetch origin
git switch main
git pull

docker compose --env-file ".\settings\docker-server.env" -f ".\settings\docker-compose.server.yml" build cfo-sync-server
docker compose --env-file ".\settings\docker-server.env" -f ".\settings\docker-compose.server.yml" up -d --force-recreate cfo-sync-server

Start-Sleep -Seconds 5
irm "https://api.ecfo.com.br/v1/health"
```

Se o healthcheck falhar, verifique logs:

```powershell
docker logs --tail 120 cfo-sync-server
```

## Arquivos esperados no servidor

Producao:

```text
C:\srv\secrets\app_config.json
C:\srv\cfo_sync\server_access.json
C:\srv\data
```

Staging:

```text
C:\srv-staging\secrets\app_config.json
C:\srv-staging\cfo_sync\server_access.json
C:\srv-staging\data
```

Para uma validacao rapida, staging pode copiar `app_config.json` e
`server_access.json` da producao. Para testes que escrevem dados ou secrets,
prefira arquivos separados em `C:\srv-staging` para nao misturar estado com
producao.

## Recomendacao futura

Para reduzir risco operacional, o ideal e manter duas pastas de codigo no
servidor:

```text
C:\CFO-Sync
C:\CFO-Sync-staging
```

Assim producao sempre builda de `C:\CFO-Sync` em `main`, e staging sempre
builda de `C:\CFO-Sync-staging` na branch em validacao.
