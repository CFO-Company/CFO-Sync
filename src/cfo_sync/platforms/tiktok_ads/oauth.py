from __future__ import annotations

import argparse
import html
from pathlib import Path
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

from cfo_sync.platforms.tiktok_ads.api import (
    TikTokAdsAPIError,
    exchange_auth_code_for_access_token,
    fetch_advertiser_infos,
    fetch_authorized_advertiser_ids,
)
from cfo_sync.platforms.tiktok_ads.credentials import TikTokAdsCredentialsStore


def validate_connection(
    credentials_path: Path,
    company: str | None = None,
) -> None:
    store = TikTokAdsCredentialsStore.from_file(credentials_path)
    access_token = str(store.auth.access_token or "").strip()
    if not access_token:
        raise ValueError(
            "access_token nao encontrado nas credenciais TikTok Ads. "
            "Use --auth-code ou --access-token para configurar."
        )

    authorized_ids = set(
        fetch_authorized_advertiser_ids(
            access_token=access_token,
            app_id=store.auth.app_id,
            secret=store.auth.secret,
        )
    )
    if not authorized_ids:
        print("Aviso: API nao retornou lista de advertiser_id autorizados.")

    companies = [company] if company else store.companies()
    for company_name in companies:
        accounts = store.accounts_for_company(company_name)
        ids = [account.advertiser_id for account in accounts]
        info_rows = fetch_advertiser_infos(access_token=access_token, advertiser_ids=ids)
        by_id = {
            "".join(ch for ch in str(item.get("advertiser_id") or item.get("id") or "") if ch.isdigit()): item
            for item in info_rows
            if isinstance(item, dict)
        }

        print(f"\nEmpresa: {company_name}")
        for account in accounts:
            advertiser_id = account.advertiser_id
            is_authorized = advertiser_id in authorized_ids if authorized_ids else True
            info = by_id.get(advertiser_id, {})
            remote_name = str(
                info.get("name")
                or info.get("advertiser_name")
                or info.get("company")
                or ""
            ).strip()
            status = "OK" if is_authorized else "SEM ACESSO"
            display_name = remote_name or account.account_name
            print(f"- {status} advertiser_id={advertiser_id} conta={display_name}")


def update_access_token(
    credentials_path: Path,
    access_token: str,
) -> None:
    store = TikTokAdsCredentialsStore.from_file(credentials_path)
    updated_store = store.with_updated_access_token(access_token)
    updated_store.save()


def exchange_and_save_access_token(
    credentials_path: Path,
    auth_code: str,
    app_id: str | None = None,
    secret: str | None = None,
    redirect_uri: str | None = None,
) -> str:
    store = TikTokAdsCredentialsStore.from_file(credentials_path)
    resolved_app_id = str(app_id or store.auth.app_id).strip()
    resolved_secret = str(secret or store.auth.secret).strip()
    resolved_redirect_uri = str(redirect_uri or store.auth.redirect_uri).strip()
    if not resolved_app_id or not resolved_secret:
        raise ValueError(
            "app_id/secret nao encontrados. Informe no JSON (auth.app_id/auth.secret) "
            "ou via --app-id/--secret."
        )

    access_token = exchange_auth_code_for_access_token(
        app_id=resolved_app_id,
        secret=resolved_secret,
        auth_code=auth_code,
        redirect_uri=resolved_redirect_uri,
    )
    updated_auth = store.auth.__class__(
        access_token=access_token,
        app_id=resolved_app_id,
        secret=resolved_secret,
        redirect_uri=resolved_redirect_uri,
    )
    updated_store = store.with_auth(updated_auth)
    updated_store.save()
    return access_token


def _main() -> int:
    parser = argparse.ArgumentParser(
        description="Utilitario OAuth/conexao TikTok Ads para CFO Sync.",
    )
    parser.add_argument(
        "--credentials",
        default="secrets/tiktok_ads_credentials.json",
        help="Caminho do JSON de credenciais TikTok Ads.",
    )
    parser.add_argument(
        "--company",
        default=None,
        help="Valida somente a empresa informada.",
    )
    parser.add_argument(
        "--auth-code",
        default=None,
        help="Auth code TikTok para gerar access_token via app_id/secret.",
    )
    parser.add_argument(
        "--access-token",
        default=None,
        help="Define access_token manualmente no arquivo de credenciais.",
    )
    parser.add_argument(
        "--app-id",
        default=None,
        help="App ID (opcional, sobrescreve temporariamente o JSON).",
    )
    parser.add_argument(
        "--secret",
        default=None,
        help="Secret (opcional, sobrescreve temporariamente o JSON).",
    )
    parser.add_argument(
        "--redirect-uri",
        default=None,
        help="Redirect URI (opcional, sobrescreve temporariamente o JSON).",
    )
    parser.add_argument(
        "--skip-validate",
        action="store_true",
        help="Nao executa validacao de advertiser_id apos atualizar token.",
    )
    parser.add_argument(
        "--print-auth-url",
        action="store_true",
        help="Mostra URLs de autorização para obter auth_code.",
    )
    parser.add_argument(
        "--state",
        default="cfo_sync",
        help="Parametro state para URL de autorização.",
    )
    parser.add_argument(
        "--run-local-callback",
        action="store_true",
        help="Executa callback local HTTP para capturar auth_code sem backend externo.",
    )
    parser.add_argument(
        "--local-host",
        default="127.0.0.1",
        help="Host do callback local (padrao: 127.0.0.1).",
    )
    parser.add_argument(
        "--local-port",
        type=int,
        default=8765,
        help="Porta do callback local (padrao: 8765).",
    )
    parser.add_argument(
        "--local-path",
        default="/tiktok/callback",
        help="Path do callback local (padrao: /tiktok/callback).",
    )
    parser.add_argument(
        "--callback-timeout",
        type=int,
        default=300,
        help="Tempo maximo (segundos) aguardando callback local (padrao: 300).",
    )
    parser.add_argument(
        "--open-browser",
        action="store_true",
        help="Abre automaticamente a URL de autorização no navegador.",
    )
    args = parser.parse_args()

    credentials_path = Path(args.credentials)
    if args.run_local_callback:
        local_redirect_uri = _build_local_redirect_uri(
            host=str(args.local_host).strip() or "127.0.0.1",
            port=args.local_port,
            path=str(args.local_path).strip() or "/tiktok/callback",
        )
        store = TikTokAdsCredentialsStore.from_file(credentials_path)
        app_id = str(args.app_id or store.auth.app_id).strip()
        secret = str(args.secret or store.auth.secret).strip()
        state = str(args.state).strip() or "cfo_sync"
        if not app_id or not secret:
            raise ValueError(
                "Para callback local, configure app_id e secret no JSON "
                "ou via --app-id/--secret."
            )

        urls = _build_authorization_urls(
            app_id=app_id,
            redirect_uri=local_redirect_uri,
            state=state,
        )
        print("Cadastre esta redirect_uri no app TikTok:")
        print(local_redirect_uri)
        print("\nAbra uma URL de autorização e conclua o login:")
        for url in urls:
            print(url)
        if args.open_browser:
            webbrowser.open(urls[0], new=2)

        auth_code = _wait_for_auth_code_local_callback(
            host=str(args.local_host).strip() or "127.0.0.1",
            port=args.local_port,
            path=str(args.local_path).strip() or "/tiktok/callback",
            expected_state=state,
            timeout_seconds=max(10, int(args.callback_timeout)),
        )
        token = exchange_and_save_access_token(
            credentials_path=credentials_path,
            auth_code=auth_code,
            app_id=app_id,
            secret=secret,
            redirect_uri=local_redirect_uri,
        )
        print(f"access_token atualizado com sucesso ({_mask(token)}).")
        if args.skip_validate:
            return 0
        validate_connection(
            credentials_path=credentials_path,
            company=args.company,
        )
        print("\nValidacao concluida.")
        return 0

    if args.print_auth_url:
        store = TikTokAdsCredentialsStore.from_file(credentials_path)
        app_id = str(args.app_id or store.auth.app_id).strip()
        redirect_uri = str(args.redirect_uri or store.auth.redirect_uri).strip()
        if not app_id or not redirect_uri:
            raise ValueError(
                "Para gerar URL de autorização, informe app_id e redirect_uri no JSON "
                "ou via --app-id/--redirect-uri."
            )
        for url in _build_authorization_urls(
            app_id=app_id,
            redirect_uri=redirect_uri,
            state=str(args.state).strip() or "cfo_sync",
        ):
            print(url)
        if args.skip_validate and not args.auth_code and not args.access_token:
            return 0
    if args.auth_code:
        token = exchange_and_save_access_token(
            credentials_path=credentials_path,
            auth_code=args.auth_code,
            app_id=args.app_id,
            secret=args.secret,
            redirect_uri=args.redirect_uri,
        )
        print(f"access_token atualizado com sucesso ({_mask(token)}).")

    if args.access_token:
        update_access_token(
            credentials_path=credentials_path,
            access_token=args.access_token,
        )
        print("access_token atualizado manualmente com sucesso.")

    if not args.skip_validate:
        validate_connection(
            credentials_path=credentials_path,
            company=args.company,
        )
        print("\nValidacao concluida.")
    return 0


def _mask(value: str) -> str:
    text = str(value or "").strip()
    if len(text) <= 8:
        return "*" * len(text)
    return f"{text[:4]}...{text[-4:]}"


def _build_authorization_urls(app_id: str, redirect_uri: str, state: str) -> list[str]:
    query = urlencode(
        {
            "app_id": app_id,
            "redirect_uri": redirect_uri,
            "state": state,
        }
    )
    return [
        f"https://ads.tiktok.com/marketing_api/auth?{query}",
        f"https://business-api.tiktok.com/portal/auth?{query}",
    ]


def _build_local_redirect_uri(host: str, port: int, path: str) -> str:
    normalized_path = path if path.startswith("/") else f"/{path}"
    return f"http://{host}:{int(port)}{normalized_path}"


def _wait_for_auth_code_local_callback(
    host: str,
    port: int,
    path: str,
    expected_state: str,
    timeout_seconds: int,
) -> str:
    normalized_path = path if path.startswith("/") else f"/{path}"
    result: dict[str, str] = {}
    done = threading.Event()

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # type: ignore[override]
            parsed = urlparse(self.path)
            if parsed.path != normalized_path:
                self.send_response(404)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"Not Found")
                return

            params = parse_qs(parsed.query)
            auth_code = _first_param(params, "auth_code") or _first_param(params, "code")
            state = _first_param(params, "state")
            error = _first_param(params, "error")
            error_description = _first_param(params, "error_description") or _first_param(params, "message")

            if error:
                result["error"] = f"{error}: {error_description}".strip(": ")
                self._respond_html(
                    status=400,
                    body=f"<h1>Erro TikTok</h1><p>{html.escape(result['error'])}</p>",
                )
                done.set()
                return

            if expected_state and state != expected_state:
                result["error"] = "State invalido no callback."
                self._respond_html(
                    status=400,
                    body=(
                        "<h1>State invalido</h1>"
                        "<p>O state recebido nao confere com o esperado. Nao utilize este codigo.</p>"
                    ),
                )
                done.set()
                return

            if not auth_code:
                result["error"] = "auth_code nao encontrado no callback."
                self._respond_html(
                    status=400,
                    body="<h1>auth_code ausente</h1><p>Nenhum auth_code foi recebido.</p>",
                )
                done.set()
                return

            result["auth_code"] = auth_code
            safe_code = html.escape(auth_code)
            self._respond_html(
                status=200,
                body=(
                    "<h1>Autorização concluida</h1>"
                    "<p>Voce pode fechar esta aba.</p>"
                    f"<p><strong>auth_code:</strong> <code>{safe_code}</code></p>"
                ),
            )
            done.set()

        def _respond_html(self, status: int, body: str) -> None:
            markup = (
                "<!doctype html><html><head><meta charset='utf-8'>"
                "<meta name='viewport' content='width=device-width, initial-scale=1'>"
                "<title>TikTok OAuth Callback</title></head><body>"
                f"{body}</body></html>"
            )
            encoded = markup.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A003
            return

    server = ThreadingHTTPServer((host, int(port)), CallbackHandler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    print(f"\nAguardando callback local em http://{host}:{int(port)}{normalized_path} ...")
    done.wait(timeout=max(10, int(timeout_seconds)))
    server.shutdown()
    server.server_close()
    worker.join(timeout=2)

    if not done.is_set():
        raise TimeoutError(
            f"Timeout aguardando callback local ({timeout_seconds}s). "
            "Verifique redirect_uri cadastrada no TikTok."
        )
    if "error" in result:
        raise ValueError(result["error"])
    auth_code = str(result.get("auth_code") or "").strip()
    if not auth_code:
        raise ValueError("Callback recebido, mas auth_code vazio.")
    return auth_code


def _first_param(params: dict[str, list[str]], key: str) -> str:
    values = params.get(key) or []
    if not values:
        return ""
    return str(values[0] or "").strip()


if __name__ == "__main__":
    try:
        raise SystemExit(_main())
    except (ValueError, TimeoutError, TikTokAdsAPIError) as error:
        print(f"Erro: {error}")
        raise SystemExit(1)
