from __future__ import annotations

import html
import os
from datetime import datetime, timezone

from flask import Flask, Response, jsonify, request


app = Flask(__name__)


@app.get("/healthz")
def healthz() -> Response:
    return jsonify({"status": "ok"})


@app.get("/tiktok/callback")
def tiktok_callback() -> Response:
    expected_state = str(os.getenv("OAUTH_STATE") or "").strip()
    state = str(request.args.get("state") or "").strip()
    error = str(request.args.get("error") or "").strip()
    error_description = str(
        request.args.get("error_description")
        or request.args.get("message")
        or ""
    ).strip()
    auth_code = str(
        request.args.get("auth_code")
        or request.args.get("code")
        or ""
    ).strip()

    if error:
        return _html_error(
            title="Erro na autorizacao TikTok",
            message=f"{error}: {error_description}".strip(": "),
        )

    if expected_state and state != expected_state:
        return _html_error(
            title="State invalido",
            message=(
                "O parametro state retornado nao confere com o esperado. "
                "Nao continue com este auth_code."
            ),
        )

    if not auth_code:
        params = ", ".join(sorted(request.args.keys()))
        return _html_error(
            title="auth_code nao recebido",
            message=f"Nenhum auth_code foi encontrado na query string. Params recebidos: {params}",
        )

    now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return _html_success(auth_code=auth_code, state=state, timestamp=now_iso)


def _html_success(auth_code: str, state: str, timestamp: str) -> Response:
    safe_code = html.escape(auth_code)
    safe_state = html.escape(state)
    safe_timestamp = html.escape(timestamp)
    markup = f"""<!doctype html>
<html lang="pt-BR">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width,initial-scale=1" />
    <title>TikTok OAuth Callback</title>
    <style>
      body {{ font-family: Arial, sans-serif; margin: 32px; }}
      .ok {{ color: #1e7f39; font-weight: 700; }}
      .box {{ border: 1px solid #ddd; border-radius: 8px; padding: 16px; max-width: 840px; }}
      code {{ display: block; white-space: pre-wrap; word-break: break-all; background: #f7f7f7; padding: 12px; border-radius: 6px; }}
      button {{ margin-top: 12px; padding: 10px 14px; }}
    </style>
  </head>
  <body>
    <h1 class="ok">Autorizacao concluida</h1>
    <div class="box">
      <p><strong>auth_code:</strong></p>
      <code id="auth-code">{safe_code}</code>
      <button onclick="navigator.clipboard.writeText(document.getElementById('auth-code').innerText)">Copiar auth_code</button>
      <p><strong>state:</strong> {safe_state or "-"}</p>
      <p><strong>timestamp (UTC):</strong> {safe_timestamp}</p>
    </div>
  </body>
</html>
"""
    return Response(markup, mimetype="text/html")


def _html_error(title: str, message: str) -> Response:
    safe_title = html.escape(title)
    safe_message = html.escape(message)
    markup = f"""<!doctype html>
<html lang="pt-BR">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width,initial-scale=1" />
    <title>TikTok OAuth Callback - Erro</title>
    <style>
      body {{ font-family: Arial, sans-serif; margin: 32px; }}
      .err {{ color: #b03030; font-weight: 700; }}
      .box {{ border: 1px solid #f0caca; border-radius: 8px; padding: 16px; max-width: 840px; background: #fff6f6; }}
    </style>
  </head>
  <body>
    <h1 class="err">{safe_title}</h1>
    <div class="box">{safe_message}</div>
  </body>
</html>
"""
    return Response(markup, status=400, mimetype="text/html")


if __name__ == "__main__":
    port = int(os.getenv("PORT") or "8000")
    app.run(host="0.0.0.0", port=port)
