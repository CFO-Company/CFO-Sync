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

Importante:
- essa pasta deve existir apenas no servidor;
- nao distribuir esses arquivos para as maquinas dos analistas.

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
      }
    }
  ]
}
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
   - ir na aba `Clientes`,
   - selecionar a plataforma,
   - selecionar `Cliente`, preencher `GID da aba do cliente` e os campos da plataforma,
   - clicar `Registrar cliente`.
   - os dados ficam salvos no `secrets` do servidor e passam a valer para todos os usuarios conectados no mesmo servidor.
   - para refletir imediatamente em outra estacao, use `Atualizar catalogo do servidor` (ou reconecte).

## Contrato de API (resumo)

### GET /v1/health

Resposta:

```json
{
  "status": "ok",
  "version": "1.2.1",
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
