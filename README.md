# CFO Sync

Aplicativo desktop para orquestrar coleta e exportacao de dados de plataformas sem distribuir credenciais para analistas.

## Arquitetura alvo

1. Credenciais de APIs ficam somente no servidor.
2. O ETL roda no servidor.
3. O desktop conecta em uma API segura, lista plataformas/clientes e dispara jobs.
4. O desktop nao precisa de `secrets` com credenciais das plataformas.

## Componentes implementados nesta fase

- API servidor (HTTP):
  - `GET /v1/health`
  - `GET /v1/catalog`
  - `POST /v1/jobs`
  - `GET /v1/jobs/{id}`
  - `GET /v1/jobs/{id}/logs`
  - `POST /v1/generators/link`
  - `GET /v1/oauth/mercado_livre/callback`
  - `GET /v1/oauth/mercado_pago/callback`
  - `GET /v1/oauth/bling/callback`
  - `GET /v1/oauth/tiktok_ads/callback`
  - `GET /v1/oauth/tiktok/callback`
- Autenticacao por Bearer token.
- RBAC por plataforma/cliente via arquivo `server_access.json`.
- Fila de jobs em background no servidor.
- Launcher desktop com:
  - URL da API
  - Token Bearer
  - botao `Conectar servidor`
  - coleta/exportacao usando jobs remotos

## Estrutura de arquivos (fase atual)

- API servidor:
  - `src/cfo_sync/server/access.py`
  - `src/cfo_sync/server/jobs.py`
  - `src/cfo_sync/server/service.py`
  - `src/cfo_sync/server/http_server.py`
  - `src/cfo_sync/server/main.py`
- Desktop remoto:
  - `src/cfo_sync/core/remote_api.py`
  - `launcher_desktop.py`
- Exemplo de permissao:
  - `tools/server_access.example.json`

## Setup detalhado do servidor (Docker)

Esse e o fluxo recomendado para substituir os 3 comandos manuais por um unico script.

Para a operacao de producao/staging e o fluxo de validar branch antes de
promover para `main`, veja `docs/infra-deploy-ambientes.md`.

### 1. Preparar a estrutura unica do servidor

No servidor, use uma raiz unica (padrao `C:\srv`) com estas pastas:

- `C:\srv\secrets`
- `C:\srv\cfo_sync`
- `C:\srv\data`

Dentro de `C:\srv\secrets`, mantenha os arquivos sensiveis do ETL, por exemplo:

- `app_config.json`
- `google_service_account.json`
- `yampi_credentials.json`
- `meta_ads_credentials.json`
- `google_ads_credentials.json`
- `tiktok_ads_credentials.json`
- `omie_credentials.json`
- `omie_2025.json`
- `mercado_livre_credentials.json`
- `mercado_livre_oauth_app.json`
- `mercado_pago_credentials.json`
- `mercado_pago_oauth_app.json`
- `pagarme_credentials.json`
- `bling_credentials.json`
- `bling_oauth_app.json`

Para o Bling, registre no `app_config.json` apenas os nomes dos arquivos privados:

```json
"bling": {
  "credentials_file": "bling_credentials.json",
  "oauth_app_file": "bling_oauth_app.json"
}
```

Importante:
- essa pasta deve existir apenas no servidor;
- nao distribuir esses arquivos para as maquinas dos analistas.

### Credenciais por plataforma

Mercado Livre, Mercado Pago, Bling e TikTok Shop usam o Gerador para criar link
OAuth. O analista preenche plataforma, cliente, GID da aba do cliente e, quando
aplicavel, alias/filial/loja. O link deve ser enviado para o dono da conta
autorizar. O callback grava os tokens no `secrets` do servidor e atualiza o
cadastro do cliente.

Para Mercado Pago, mantenha as credenciais do app em
`secrets/mercado_pago_oauth_app.json`:

```json
{
  "client_id": "APP_CLIENT_ID",
  "client_secret": "APP_CLIENT_SECRET",
  "public_key": "APP_PUBLIC_KEY",
  "redirect_uri": "https://api.ecfo.com.br/v1/oauth/mercado_pago/callback"
}
```

O `redirect_uri` deve estar cadastrado no app do Mercado Pago e precisa apontar
para a URL publica real do servidor. As contas autorizadas pelos clientes ficam
em `secrets/mercado_pago_credentials.json`.

Pagar.me nao usa OAuth nesta versao. Cada conta precisa ser cadastrada com
credenciais diretas em `secrets/pagarme_credentials.json`:

```json
{
  "base_url": "https://api.pagar.me/core/v5",
  "companies": {
    "Cliente": [
      {
        "account_name": "Loja Principal",
        "account_id": "acc_xxx",
        "public_key": "pk_xxx",
        "secret_key": "sk_xxx"
      }
    ]
  }
}
```

Mercado Livre pode demorar mais que outras plataformas por volume e pelas
chamadas de detalhe da API. O servidor segmenta jobs por alias/mes quando
possivel, e o desktop aguarda mais tempo para evitar timeout durante exports
longos.

> Release/deploy de producao deve seguir o runbook em
> [`docs/release-deploy-runbook.md`](docs/release-deploy-runbook.md). Ele cobre
> validacao de `CHANGELOG.md`, tag/release, update do repositorio no servidor,
> rebuild Docker e healthcheck.

### 2. Rodar o script unico de bootstrap Docker

No repo (`C:\CFO-Sync`), execute:

```powershell
.\settings\setup_docker_server.ps1 -HostRoot "C:\srv" -Port 8088 -Workers 2
```

Para usar tunnel nomeado com dominio fixo, passe o token do tunnel e hostname:

```powershell
.\settings\setup_docker_server.ps1 -HostRoot "C:\srv" -Port 8088 -Workers 2 -WithTunnel -TunnelToken "SEU_TUNNEL_TOKEN" -TunnelHostname "ecfo.com.br"
```

O script executa automaticamente:

1. `docker compose build cfo-sync-server`
2. gera `C:\srv\cfo_sync\server_access.json` (se nao existir)
3. sobe os containers (`cfo-sync-server` e `cfo-sync-tunnel` quando usar `-WithTunnel` com `-TunnelToken`)

Arquivos usados:

- `settings/docker/server.Dockerfile`
- `settings/docker-compose.server.yml`
- `settings/docker-server.env` (gerado automaticamente)

### 3. Ajustar tokens/permissoes (RBAC)

Abra `C:\srv\cfo_sync\server_access.json` e edite os escopos por analista.

Exemplo:

```json
{
  "tokens": [
    {
      "name": "analista_financeiro",
      "token": "TOKEN_FORTE_AQUI",
      "allowed_platforms": ["yampi", "meta_ads"],
      "allowed_clients": {
        "yampi": ["Aurha", "Avozon"],
        "meta_ads": ["*"]
      },
      "can_manage_secrets": false,
      "can_select_server_version": false,
      "allowed_server_versions": []
    }
  ]
}
```

Para permitir visualizar/editar arquivos `.json` da pasta `secrets` pela tela
`Server > Secrets do servidor`, marque apenas tokens administrativos com:

```json
"can_manage_secrets": true
```

Para permitir o seletor de versao do servidor na aba `Configuracoes`, marque
apenas o token de validacao com `can_select_server_version`.

Para liberar todas as versoes publicadas pelo servidor, deixe
`allowed_server_versions` vazio:

```json
"can_select_server_version": true,
"allowed_server_versions": []
```

Se precisar restringir um token a nomes especificos, preencha a lista, por
exemplo `["production", "staging"]`.

As versoes disponiveis sao publicadas pelo servidor via
`CFO_SYNC_RUNTIME_VERSIONS`, no formato JSON
`{"production":"https://api.ecfo.com.br/","staging":"https://staging-api.ecfo.com.br/"}`.
No bootstrap Docker, o mesmo valor pode ser persistido com:

```powershell
.\settings\setup_docker_server.ps1 -RuntimeVersions '{"production":"https://api.ecfo.com.br/","staging":"https://staging-api.ecfo.com.br/"}'
```

Se precisar recriar token/template do zero:

```powershell
.\settings\setup_docker_server.ps1 -HostRoot "C:\srv" -ForceRecreateAccess
```

### 4. Validar API localmente

Substitua `SEU_TOKEN`:

```powershell
$token = "SEU_TOKEN"
irm http://127.0.0.1:8088/v1/health
irm http://127.0.0.1:8088/v1/catalog -Headers @{ Authorization = "Bearer $token" }
```

### 5. URL publica (quando usar tunnel)

Para acompanhar logs do tunnel:

```powershell
docker compose --env-file .\settings\docker-server.env -f .\settings\docker-compose.server.yml logs -f cfo-sync-tunnel
```

Use seu dominio fixo configurado no Cloudflare (exemplo `https://ecfo.com.br`).

### Operacao diaria (Docker)

Subir apenas servidor (sem tunnel):

```powershell
docker compose --env-file .\settings\docker-server.env -f .\settings\docker-compose.server.yml up -d cfo-sync-server
```

Subir servidor + tunnel:

```powershell
docker compose --env-file .\settings\docker-server.env -f .\settings\docker-compose.server.yml --profile tunnel up -d
```

Parar stack:

```powershell
docker compose --env-file .\settings\docker-server.env -f .\settings\docker-compose.server.yml down
```

### Automacao diaria de categorias Omie

O script abaixo atualiza a aba de categorias da Omie uma vez ao dia. Ele busca
as categorias na Omie, compara por `origem` + `codigo` e deixa a planilha
sincronizada com os dados atuais da API. Linhas novas ou alteradas recebem nova
`data_atualizacao`; linhas inalteradas preservam a data anterior.

Execucao manual:

```powershell
python .\scripts\task_scheduler\omie_categorias_diario.py
```

Destino padrao:

- Planilha: informe por `--spreadsheet-id` ou `CFO_SYNC_OMIE_CATEGORIAS_SPREADSHEET_ID`
- GID: informe por `--gid` ou `CFO_SYNC_OMIE_CATEGORIAS_GID`

Se precisar usar outro arquivo de credenciais Omie:

```powershell
python .\scripts\task_scheduler\omie_categorias_diario.py --credentials-file "omie_cfo.json"
```

## Setup detalhado do desktop (analista)

1. Abrir `CFO Sync`.
2. Ir na aba `Configuracoes`.
3. Preencher:
   - `URL da API servidor`: `https://ecfo.com.br`
   - `Token Bearer`: token entregue para o analista.
4. Clicar `Conectar servidor`.
5. Validar que o status mudou para `Conectado`.
6. Selecionar plataforma/cliente/periodo e usar:
   - `Coletar no banco`
   - `Exportar para Sheets`
7. Para cadastrar nova conta/credencial em cliente existente:
   - para plataformas com OAuth, ir na aba `Gerador`, selecionar a plataforma,
     cliente e GID da aba do cliente, gerar o link e enviar para autorizacao;
   - para plataformas com credencial direta, ir na aba `Clientes`, selecionar a
     plataforma, selecionar `Cliente`, preencher `GID da aba do cliente` e os
     campos da plataforma, e clicar `Registrar cliente`.
   - os dados ficam salvos no `secrets` do servidor e passam a valer para todos os usuarios conectados no mesmo servidor.
   - para refletir imediatamente em outra estacao, use `Atualizar catalogo do servidor` (ou reconecte).

## Contrato de API (resumo)

### GET /v1/health

Resposta:

```json
{
  "status": "ok",
  "version": "1.3.26",
  "build_branch": "1.2.20",
  "build_commit": "d899dbe...",
  "server_time": "2026-04-02T12:00:00+00:00"
}
```

### GET /v1/catalog

Auth: `Authorization: Bearer <token>`

Resposta (exemplo reduzido):

```json
{
  "generated_at": "2026-04-02T12:00:00+00:00",
  "platforms": [
    {
      "key": "yampi",
      "label": "Yampi",
      "resources": [
        { "name": "financeiro", "endpoint": "/orders", "field_map": {} }
      ],
      "clients": [
        { "name": "Aurha", "sub_clients": ["Loja 1", "Loja 2"] }
      ]
    }
  ]
}
```

### GET /v1/secrets/files

Auth: `Authorization: Bearer <token>` com `can_manage_secrets: true`

Lista arquivos `.json` dentro da pasta `secrets`, incluindo `path`,
`modified_at` e `size_bytes`.

### GET /v1/secrets/file

Auth: `Authorization: Bearer <token>` com `can_manage_secrets: true`

Query: `?path=app_config.json`

Retorna metadados e o conteudo do JSON.

### POST /v1/secrets/file

Auth: `Authorization: Bearer <token>` com `can_manage_secrets: true`

Request:

```json
{
  "path": "app_config.json",
  "content": "{\"platforms\": []}"
}
```

O servidor valida o JSON antes de salvar e bloqueia caminhos fora de `secrets`.

### POST /v1/jobs

Auth: `Authorization: Bearer <token>`

Request:

```json
{
  "action": "export",
  "platform_key": "yampi",
  "client": "Aurha",
  "start_date": "2026-04-01",
  "end_date": "2026-04-02",
  "resource_names": ["financeiro"],
  "sub_clients": ["Loja 1"]
}
```

Response:

```json
{
  "job_id": "f2c5...",
  "status": "queued"
}
```

### GET /v1/jobs

Auth: `Authorization: Bearer <token>` com `can_manage_secrets: true`

Lista o estado operacional da fila em memoria do servidor: totais por status,
quantidade de workers, profundidade da fila e jobs recentes com payload
sanitizado.

Observacao: a fila atual e em memoria; reiniciar o container limpa o historico
visivel neste endpoint.

Response:

```json
{
  "summary": {
    "total": 6,
    "queued": 2,
    "running": 1,
    "completed": 2,
    "failed": 1,
    "workers": 2,
    "queue_depth": 2
  },
  "jobs": [
    {
      "id": "f2c5...",
      "requested_by": "analista_financeiro",
      "status": "queued",
      "queue_state": "waiting",
      "created_at": "...",
      "started_at": null,
      "finished_at": null,
      "payload": {
        "action": "export",
        "platform_key": "yampi",
        "client": "Aurha"
      },
      "error": null,
      "log_count": 1
    }
  ]
}
```

### POST /v1/clients

Auth: `Authorization: Bearer <token>`

Observacao: `client_name` deve ser um cliente ja existente na plataforma selecionada.
Observacao: `gid` e o GID da aba (sheetId) do cliente no Google Sheets. O ID da planilha ja vem do cadastro atual.

Request (exemplo):

```json
{
  "platform_key": "yampi",
  "client_name": "Aurha",
  "gid": "123456789",
  "credentials": {
    "alias": "Loja Principal",
    "user_token": "TOKEN",
    "user_secret_key": "SECRET"
  },
  "resource_gids": {
    "sku": "987654321"
  }
}
```

Response:

```json
{
  "message": "Cadastro registrado com sucesso.",
  "platform_key": "yampi",
  "client_name": "Aurha",
  "updated_resources": ["financeiro", "sku"],
  "updated_files": [".../app_config.json", ".../yampi_credentials.json"]
}
```

### POST /v1/generators/link

Auth: `Authorization: Bearer <token>`

Gera um link de autorizacao para plataformas OAuth suportadas pelo Gerador. Use
para Mercado Livre, Mercado Pago, Bling e TikTok Shop quando o cliente precisa
autorizar a propria conta.

Request (exemplo Mercado Pago):

```json
{
  "registration_mode": "existing_client",
  "platform_key": "mercado_pago",
  "client_name": "Unfair",
  "gid": "123456789",
  "credentials": {
    "account_alias": "Le Moritz"
  }
}
```

Response:

```json
{
  "platform_key": "mercado_pago",
  "client_name": "Unfair",
  "authorization_url": "https://auth.mercadopago.com/authorization?..."
}
```

### GET /v1/jobs/{id}

Auth: `Authorization: Bearer <token>`

Response:

```json
{
  "id": "f2c5...",
  "requested_by": "analista_financeiro",
  "status": "completed",
  "created_at": "...",
  "started_at": "...",
  "finished_at": "...",
  "result": {
    "action": "export",
    "platform_key": "yampi",
    "client": "Aurha",
    "count": 120
  },
  "error": null
}
```

### GET /v1/jobs/{id}/logs

Auth: `Authorization: Bearer <token>`

Response:

```json
{
  "logs": [
    "[2026-04-02T12:00:00+00:00] Job enfileirado.",
    "[2026-04-02T12:00:01+00:00] Job iniciado."
  ]
}
```

### GET /v1/oauth/mercado_livre/callback

Endpoint de callback OAuth do Mercado Livre para receber `code`, trocar por
tokens e atualizar `secrets/mercado_livre_credentials.json` no servidor.

### GET /v1/oauth/mercado_pago/callback

Endpoint de callback OAuth do Mercado Pago para receber `code`, trocar por
tokens e atualizar `secrets/mercado_pago_credentials.json` no servidor.

### GET /v1/oauth/bling/callback

Endpoint de callback OAuth do Bling para receber `code`, trocar por tokens e
atualizar `secrets/bling_credentials.json` no servidor.

### GET /v1/oauth/tiktok_ads/callback

Endpoint de callback OAuth do TikTok Ads para receber `auth_code`, trocar por `access_token` e atualizar `secrets/tiktok_ads_credentials.json` no servidor.

### GET /v1/oauth/tiktok/callback

Endpoint de callback OAuth do TikTok Shop para receber `code`, trocar por
tokens e atualizar `secrets/tiktok_shop_credentials.json` no servidor.

## Segurança recomendada (producao)

1. Usar tunnel nomeado + dominio fixo (ja suportado em `setup_docker_server.ps1`).
2. Proteger endpoint com camada de acesso (Zero Trust/IdP).
3. Tokens por analista, sem compartilhamento.
4. Rotacao periodica de tokens.
5. Limitar `allowed_platforms` e `allowed_clients` por perfil.
6. Registrar logs de auditoria em storage central.
7. Executar servidor atras de firewall + TLS.

## Limitações desta fase

1. Fluxo remoto de SKU ainda nao foi habilitado.
2. Token ainda e armazenado no `desktop_settings.json` local (proxima fase: armazenamento seguro no OS keychain/DPAPI).
3. Autenticacao atual e Bearer token; proxima fase recomendada: SSO/OIDC.

## Build local

```powershell
.\tools\build_windows_package.ps1
```
