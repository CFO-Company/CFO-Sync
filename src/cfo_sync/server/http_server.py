from __future__ import annotations

import html
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from cfo_sync.server.access import AccessTokenPolicy, authenticate_token, load_access_policies
from cfo_sync.server.jobs import JobManager
from cfo_sync.server.service import CfoSyncServerService, serialize_job


class CfoSyncHttpServer:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        app_config_path: Path,
        access_config_path: Path,
        worker_count: int = 2,
    ) -> None:
        self.host = host
        self.port = port
        self.service = CfoSyncServerService(app_config_path)
        self.access_policies = load_access_policies(access_config_path)
        self.policy_by_name = {policy.name: policy for policy in self.access_policies}

        def runner(payload: dict[str, object], log) -> dict[str, object]:
            policy_name = str(payload.get("_policy_name") or "").strip()
            request_payload = payload.get("_request_payload")
            if not isinstance(request_payload, dict):
                raise ValueError("Payload interno do job invalido.")

            policy = self.policy_by_name.get(policy_name)
            if policy is None:
                raise PermissionError("Token do job nao encontrado.")
            return self.service.run_job(request_payload, policy=policy, log=log)

        self.jobs = JobManager(runner=runner, worker_count=worker_count)

        handler = self._build_handler()
        self.httpd = ThreadingHTTPServer((host, port), handler)

    def serve_forever(self) -> None:
        self.httpd.serve_forever()

    def shutdown(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.jobs.stop()

    def _build_handler(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                path = parsed.path.rstrip("/") or "/"

                if path == "/v1/health":
                    self._write_json(HTTPStatus.OK, server.service.health_payload())
                    return

                if path == "/v1/oauth/mercado_livre/callback":
                    params = parse_qs(parsed.query or "")
                    oauth_error = str((params.get("error") or [""])[0] or "").strip()
                    oauth_error_description = str(
                        (params.get("error_description") or [""])[0] or ""
                    ).strip()
                    if oauth_error:
                        message = f"Autorização recusada pelo Mercado Livre: {oauth_error}"
                        if oauth_error_description:
                            message += f" ({oauth_error_description})"
                        self._write_html(
                            HTTPStatus.BAD_REQUEST,
                            _oauth_error_html(message),
                        )
                        return

                    code = str((params.get("code") or [""])[0] or "").strip()
                    state = str((params.get("state") or [""])[0] or "").strip()
                    try:
                        result = server.service.complete_mercado_livre_oauth_callback(
                            code=code,
                            state=state,
                        )
                    except (ValueError, FileNotFoundError) as error:
                        self._write_html(
                            HTTPStatus.BAD_REQUEST,
                            _oauth_error_html(str(error)),
                        )
                        return
                    except Exception as error:  # noqa: BLE001
                        self._write_html(
                            HTTPStatus.INTERNAL_SERVER_ERROR,
                            _oauth_error_html(f"Falha no callback OAuth: {error}"),
                        )
                        return

                    self._write_html(HTTPStatus.OK, _oauth_success_html(result))
                    return

                if path == "/v1/oauth/tiktok_ads/callback":
                    params = parse_qs(parsed.query or "")
                    oauth_error = str((params.get("error") or [""])[0] or "").strip()
                    oauth_error_description = str(
                        (params.get("error_description") or [""])[0] or ""
                    ).strip()
                    if oauth_error:
                        message = f"Autorização recusada pelo TikTok Ads: {oauth_error}"
                        if oauth_error_description:
                            message += f" ({oauth_error_description})"
                        self._write_html(
                            HTTPStatus.BAD_REQUEST,
                            _oauth_error_html(message),
                        )
                        return

                    code = str((params.get("auth_code") or [""])[0] or "").strip()
                    if not code:
                        code = str((params.get("code") or [""])[0] or "").strip()
                    state = str((params.get("state") or [""])[0] or "").strip()
                    try:
                        result = server.service.complete_tiktok_ads_oauth_callback(
                            code=code,
                            state=state,
                        )
                    except (ValueError, FileNotFoundError) as error:
                        self._write_html(
                            HTTPStatus.BAD_REQUEST,
                            _oauth_error_html(str(error)),
                        )
                        return
                    except Exception as error:  # noqa: BLE001
                        self._write_html(
                            HTTPStatus.INTERNAL_SERVER_ERROR,
                            _oauth_error_html(f"Falha no callback OAuth: {error}"),
                        )
                        return

                    self._write_html(HTTPStatus.OK, _oauth_tiktok_success_html(result))
                    return

                if path == "/v1/oauth/tiktok/callback":
                    params = parse_qs(parsed.query or "")
                    oauth_error = str((params.get("error") or [""])[0] or "").strip()
                    oauth_error_description = str(
                        (params.get("error_description") or [""])[0] or ""
                    ).strip()
                    if oauth_error:
                        message = f"Autorização recusada pelo TikTok Shop: {oauth_error}"
                        if oauth_error_description:
                            message += f" ({oauth_error_description})"
                        self._write_html(
                            HTTPStatus.BAD_REQUEST,
                            _oauth_error_html(message),
                        )
                        return

                    code = str((params.get("auth_code") or [""])[0] or "").strip()
                    if not code:
                        code = str((params.get("code") or [""])[0] or "").strip()
                    state = str((params.get("state") or [""])[0] or "").strip()
                    try:
                        result = server.service.complete_tiktok_shop_oauth_callback(
                            code=code,
                            state=state,
                        )
                    except (ValueError, FileNotFoundError) as error:
                        self._write_html(
                            HTTPStatus.BAD_REQUEST,
                            _oauth_error_html(str(error)),
                        )
                        return
                    except Exception as error:  # noqa: BLE001
                        self._write_html(
                            HTTPStatus.INTERNAL_SERVER_ERROR,
                            _oauth_error_html(f"Falha no callback OAuth: {error}"),
                        )
                        return

                    self._write_html(HTTPStatus.OK, _oauth_tiktok_shop_success_html(result))
                    return

                policy = self._require_auth()
                if policy is None:
                    return

                if path == "/v1/catalog":
                    payload = server.service.build_catalog(policy)
                    self._write_json(HTTPStatus.OK, payload)
                    return

                if path == "/v1/secrets/files":
                    try:
                        payload = server.service.list_secret_json_files(policy=policy)
                    except PermissionError as error:
                        self._write_json(HTTPStatus.FORBIDDEN, {"error": str(error)})
                        return
                    except Exception as error:  # noqa: BLE001
                        self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(error)})
                        return
                    self._write_json(HTTPStatus.OK, payload)
                    return

                if path == "/v1/secrets/file":
                    params = parse_qs(parsed.query or "")
                    relative_path = str((params.get("path") or [""])[0] or "").strip()
                    try:
                        payload = server.service.read_secret_json_file(relative_path, policy=policy)
                    except PermissionError as error:
                        self._write_json(HTTPStatus.FORBIDDEN, {"error": str(error)})
                        return
                    except FileNotFoundError as error:
                        self._write_json(HTTPStatus.NOT_FOUND, {"error": str(error)})
                        return
                    except ValueError as error:
                        self._write_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
                        return
                    except Exception as error:  # noqa: BLE001
                        self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(error)})
                        return
                    self._write_json(HTTPStatus.OK, payload)
                    return

                if path.startswith("/v1/jobs/") and path.endswith("/logs"):
                    job_id = path.split("/")[3]
                    job = server.jobs.get(job_id)
                    if job is None or job.requested_by != policy.name:
                        self._write_json(HTTPStatus.NOT_FOUND, {"error": "Job nao encontrado."})
                        return
                    self._write_json(HTTPStatus.OK, {"logs": job.logs})
                    return

                if path.startswith("/v1/jobs/"):
                    job_id = path.split("/")[3]
                    job = server.jobs.get(job_id)
                    if job is None or job.requested_by != policy.name:
                        self._write_json(HTTPStatus.NOT_FOUND, {"error": "Job nao encontrado."})
                        return
                    self._write_json(HTTPStatus.OK, serialize_job(job))
                    return

                self._write_json(HTTPStatus.NOT_FOUND, {"error": "Rota nao encontrada."})

            def do_POST(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                path = parsed.path.rstrip("/") or "/"

                policy = self._require_auth()
                if policy is None:
                    return

                if path == "/v1/jobs":
                    payload = self._read_json_body()
                    if payload is None:
                        return

                    job = server.jobs.enqueue(
                        requested_by=policy.name,
                        payload={
                            "_policy_name": policy.name,
                            "_request_payload": payload,
                        },
                    )
                    self._write_json(
                        HTTPStatus.ACCEPTED,
                        {
                            "job_id": job.id,
                            "status": job.status,
                        },
                    )
                    return

                if path == "/v1/clients":
                    payload = self._read_json_body()
                    if payload is None:
                        return
                    try:
                        result = server.service.register_client(payload, policy=policy)
                    except PermissionError as error:
                        self._write_json(HTTPStatus.FORBIDDEN, {"error": str(error)})
                        return
                    except (ValueError, FileNotFoundError) as error:
                        self._write_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
                        return
                    except Exception as error:  # noqa: BLE001
                        self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(error)})
                        return
                    self._write_json(HTTPStatus.CREATED, result)
                    return

                if path == "/v1/generators/link":
                    payload = self._read_json_body()
                    if payload is None:
                        return
                    try:
                        result = server.service.create_generator_link(
                            payload,
                            policy=policy,
                            external_base_url=self._external_base_url(),
                        )
                    except PermissionError as error:
                        self._write_json(HTTPStatus.FORBIDDEN, {"error": str(error)})
                        return
                    except (ValueError, FileNotFoundError) as error:
                        self._write_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
                        return
                    except Exception as error:  # noqa: BLE001
                        self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(error)})
                        return
                    self._write_json(HTTPStatus.CREATED, result)
                    return

                if path == "/v1/secrets/file":
                    payload = self._read_json_body()
                    if payload is None:
                        return
                    relative_path = str(payload.get("path") or "").strip()
                    content = str(payload.get("content") or "")
                    try:
                        result = server.service.update_secret_json_file(
                            relative_path,
                            content,
                            policy=policy,
                        )
                    except PermissionError as error:
                        self._write_json(HTTPStatus.FORBIDDEN, {"error": str(error)})
                        return
                    except FileNotFoundError as error:
                        self._write_json(HTTPStatus.NOT_FOUND, {"error": str(error)})
                        return
                    except ValueError as error:
                        self._write_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
                        return
                    except Exception as error:  # noqa: BLE001
                        self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(error)})
                        return
                    self._write_json(HTTPStatus.OK, result)
                    return

                self._write_json(HTTPStatus.NOT_FOUND, {"error": "Rota nao encontrada."})

            def _require_auth(self) -> AccessTokenPolicy | None:
                header = str(self.headers.get("Authorization") or "").strip()
                if not header.lower().startswith("bearer "):
                    self._write_json(HTTPStatus.UNAUTHORIZED, {"error": "Token Bearer ausente."})
                    return None
                token = header[7:].strip()
                policy = authenticate_token(token, server.access_policies)
                if policy is None:
                    self._write_json(HTTPStatus.UNAUTHORIZED, {"error": "Token invalido."})
                    return None
                return policy

            def _read_json_body(self) -> dict[str, object] | None:
                length_raw = self.headers.get("Content-Length")
                if not length_raw:
                    self._write_json(HTTPStatus.BAD_REQUEST, {"error": "Body JSON obrigatorio."})
                    return None

                try:
                    length = int(length_raw)
                except ValueError:
                    self._write_json(HTTPStatus.BAD_REQUEST, {"error": "Content-Length invalido."})
                    return None

                raw = self.rfile.read(length)
                try:
                    payload = json.loads(raw.decode("utf-8-sig"))
                except json.JSONDecodeError:
                    self._write_json(HTTPStatus.BAD_REQUEST, {"error": "JSON invalido."})
                    return None

                if not isinstance(payload, dict):
                    self._write_json(HTTPStatus.BAD_REQUEST, {"error": "Body deve ser objeto JSON."})
                    return None
                return payload

            def _write_json(self, status_code: HTTPStatus, payload: dict[str, object]) -> None:
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status_code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _write_html(self, status_code: HTTPStatus, html: str) -> None:
                body = str(html or "").encode("utf-8")
                self.send_response(status_code)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _external_base_url(self) -> str:
                forwarded_proto = str(self.headers.get("X-Forwarded-Proto") or "").split(",")[0].strip()
                forwarded_host = str(self.headers.get("X-Forwarded-Host") or "").split(",")[0].strip()
                host = forwarded_host or str(self.headers.get("Host") or "").strip()
                if not host:
                    host = f"{server.host}:{server.port}"
                scheme = forwarded_proto or "http"
                return f"{scheme}://{host}".rstrip("/")

            def log_message(self, format: str, *args) -> None:  # noqa: A003
                return

        return Handler


def _oauth_success_html(result: dict[str, object]) -> str:
    platform = html.escape(str(result.get("platform_key") or "").strip() or "mercado_livre")
    client_name = html.escape(str(result.get("client_name") or "").strip())
    mode = str(result.get("registration_mode") or "").strip()
    mode_label = "Novo cliente" if mode == "new_client" else "Filial/Alias"

    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>Autorização concluida</title>"
        "<style>"
        "body{font-family:Segoe UI,Arial,sans-serif;background:#f5f7fa;margin:0;padding:24px;}"
        ".card{max-width:640px;margin:0 auto;background:#fff;border:1px solid #dde3ea;"
        "border-radius:12px;padding:24px;box-shadow:0 8px 24px rgba(0,0,0,.08)}"
        "h1{margin:0 0 12px;color:#123;font-size:24px}"
        "p{margin:8px 0;color:#334}"
        "code{background:#eef2f6;padding:2px 6px;border-radius:6px}"
        ".ok{color:#0b7a43;font-weight:600}"
        "</style></head><body><div class='card'>"
        "<h1>Autorização concluida</h1>"
        "<p class='ok'>Conta Mercado Livre autorizada com sucesso.</p>"
        f"<p><strong>Plataforma:</strong> <code>{platform}</code></p>"
        f"<p><strong>Cliente:</strong> {client_name}</p>"
        f"<p><strong>Modo:</strong> {mode_label}</p>"
        "<p>Voce pode fechar esta pagina e voltar ao aplicativo CFO Sync.</p>"
        "</div></body></html>"
    )


def _oauth_error_html(message: str) -> str:
    safe = html.escape(str(message or "Erro desconhecido no callback OAuth."))
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>Erro na autorização</title>"
        "<style>"
        "body{font-family:Segoe UI,Arial,sans-serif;background:#fff5f5;margin:0;padding:24px;}"
        ".card{max-width:640px;margin:0 auto;background:#fff;border:1px solid #ffd5d5;"
        "border-radius:12px;padding:24px;box-shadow:0 8px 24px rgba(0,0,0,.08)}"
        "h1{margin:0 0 12px;color:#7a0b0b;font-size:24px}"
        "p{margin:8px 0;color:#533}"
        "code{background:#fff1f1;padding:2px 6px;border-radius:6px}"
        "</style></head><body><div class='card'>"
        "<h1>Erro na autorização</h1>"
        f"<p>{safe}</p>"
        "<p>Gere um novo link de autorização no aplicativo e tente novamente.</p>"
        "</div></body></html>"
    )


def _oauth_tiktok_success_html(result: dict[str, object]) -> str:
    state = html.escape(str(result.get("state") or "").strip())
    redirect_uri = html.escape(str(result.get("redirect_uri") or "").strip())
    token_masked = html.escape(str(result.get("access_token_masked") or "").strip())
    authorized_count = html.escape(str(result.get("authorized_count") or 0))
    warning = html.escape(str(result.get("warning") or "").strip())

    warning_html = ""
    if warning:
        warning_html = (
            "<p style='color:#8a5a00;background:#fff8e8;border:1px solid #ffe2a6;padding:10px;border-radius:8px'>"
            f"<strong>Aviso ao listar advertiser_id autorizados:</strong> {warning}</p>"
        )

    state_html = ""
    if state:
        state_html = f"<p><strong>State:</strong> <code>{state}</code></p>"

    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>Autorização concluida</title>"
        "<style>"
        "body{font-family:Segoe UI,Arial,sans-serif;background:#f5f7fa;margin:0;padding:24px;}"
        ".card{max-width:760px;margin:0 auto;background:#fff;border:1px solid #dde3ea;"
        "border-radius:12px;padding:24px;box-shadow:0 8px 24px rgba(0,0,0,.08)}"
        "h1{margin:0 0 12px;color:#123;font-size:24px}"
        "p{margin:8px 0;color:#334}"
        "code{background:#eef2f6;padding:2px 6px;border-radius:6px;word-break:break-all}"
        ".ok{color:#0b7a43;font-weight:600}"
        "</style></head><body><div class='card'>"
        "<h1>Autorização TikTok Ads concluida</h1>"
        "<p class='ok'>access_token salvo com sucesso nas credenciais do servidor.</p>"
        f"<p><strong>Token:</strong> <code>{token_masked}</code></p>"
        f"<p><strong>Advertisers autorizados:</strong> {authorized_count}</p>"
        f"<p><strong>Redirect URI:</strong> <code>{redirect_uri}</code></p>"
        f"{state_html}"
        f"{warning_html}"
        "<p>Voce pode fechar esta pagina e voltar ao aplicativo CFO Sync.</p>"
        "</div></body></html>"
    )


def _oauth_tiktok_shop_success_html(result: dict[str, object]) -> str:
    state = html.escape(str(result.get("state") or "").strip())
    redirect_uri = html.escape(str(result.get("redirect_uri") or "").strip())
    token_masked = html.escape(str(result.get("access_token_masked") or "").strip())
    refresh_token_masked = html.escape(str(result.get("refresh_token_masked") or "").strip())
    shop_id = html.escape(str(result.get("shop_id") or "").strip())
    shop_cipher = html.escape(str(result.get("shop_cipher") or "").strip())
    seller_name = html.escape(str(result.get("seller_name") or "").strip())

    state_html = ""
    if state:
        state_html = f"<p><strong>State:</strong> <code>{state}</code></p>"

    seller_html = ""
    if seller_name:
        seller_html = f"<p><strong>Loja:</strong> {seller_name}</p>"

    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>Autorização concluida</title>"
        "<style>"
        "body{font-family:Segoe UI,Arial,sans-serif;background:#f5f7fa;margin:0;padding:24px;}"
        ".card{max-width:760px;margin:0 auto;background:#fff;border:1px solid #dde3ea;"
        "border-radius:12px;padding:24px;box-shadow:0 8px 24px rgba(0,0,0,.08)}"
        "h1{margin:0 0 12px;color:#123;font-size:24px}"
        "p{margin:8px 0;color:#334}"
        "code{background:#eef2f6;padding:2px 6px;border-radius:6px;word-break:break-all}"
        ".ok{color:#0b7a43;font-weight:600}"
        "</style></head><body><div class='card'>"
        "<h1>Autorização TikTok Shop concluida</h1>"
        "<p class='ok'>access_token salvo com sucesso nas credenciais do servidor.</p>"
        f"<p><strong>Token:</strong> <code>{token_masked}</code></p>"
        f"<p><strong>Refresh token:</strong> <code>{refresh_token_masked}</code></p>"
        f"<p><strong>Shop ID:</strong> <code>{shop_id}</code></p>"
        f"<p><strong>Shop Cipher:</strong> <code>{shop_cipher}</code></p>"
        f"{seller_html}"
        f"<p><strong>Redirect URI:</strong> <code>{redirect_uri}</code></p>"
        f"{state_html}"
        "<p>Voce pode fechar esta pagina e voltar ao aplicativo CFO Sync.</p>"
        "</div></body></html>"
    )

