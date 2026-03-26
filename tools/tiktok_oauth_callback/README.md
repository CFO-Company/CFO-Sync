# TikTok OAuth Callback Service

Servico minimo para callback OAuth do TikTok Ads.

## Endpoints

- `GET /healthz`: health check
- `GET /tiktok/callback`: recebe `auth_code` (ou `code`) e valida `state`

## Variaveis de ambiente

- `OAUTH_STATE` (recomendado): valor esperado do parametro `state`
- `PORT`: porta HTTP (padrao local `8000`)

## Execucao local

```powershell
cd tools/tiktok_oauth_callback
python -m pip install -r requirements.txt
python app.py
```

URL local:

- `http://localhost:8000/tiktok/callback`

## Deploy (Render/Railway)

Build command:

```bash
pip install -r requirements.txt
```

Start command:

```bash
gunicorn app:app
```

Depois do deploy, use a URL publica:

- `https://SEU-SERVICO/tiktok/callback`

Essa URL deve ser cadastrada como `redirect_uri` no app do TikTok e no `secrets/tiktok_ads_credentials.json`.

## Fluxo no CFO Sync

1. Atualizar `auth.redirect_uri` em `secrets/tiktok_ads_credentials.json`.
2. Gerar URL de autorizacao:

```powershell
$env:PYTHONPATH="src"
.\.venv\Scripts\python.exe -m cfo_sync.platforms.tiktok_ads.oauth --credentials secrets/tiktok_ads_credentials.json --print-auth-url --state "SEU_STATE" --skip-validate
```

3. Autorizar no TikTok.
4. Copiar `auth_code` exibido no callback.
5. Trocar por token:

```powershell
$env:PYTHONPATH="src"
.\.venv\Scripts\python.exe -m cfo_sync.platforms.tiktok_ads.oauth --credentials secrets/tiktok_ads_credentials.json --auth-code "AUTH_CODE"
```
