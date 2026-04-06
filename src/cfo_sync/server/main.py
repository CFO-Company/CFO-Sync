from __future__ import annotations

import argparse
import json
import secrets
from pathlib import Path

from cfo_sync.core.runtime_paths import app_config_path, runtime_root
from cfo_sync.server.http_server import CfoSyncHttpServer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Servidor HTTP do CFO Sync (orquestracao remota).")
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host para bind (padrao: 127.0.0.1).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8088,
        help="Porta HTTP (padrao: 8088).",
    )
    parser.add_argument(
        "--app-config",
        default=str(app_config_path()),
        help="Caminho do app_config.json do servidor.",
    )
    parser.add_argument(
        "--access-config",
        default=str(runtime_root() / "settings" / "server_access.json"),
        help="Caminho do JSON de tokens e permissoes.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=2,
        help="Numero de workers de jobs em paralelo.",
    )
    parser.add_argument(
        "--init-access-template",
        action="store_true",
        help="Cria template de access-config e encerra.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    app_config = Path(args.app_config).expanduser().resolve()
    access_config = Path(args.access_config).expanduser().resolve()

    if args.init_access_template:
        _write_access_template(access_config)
        print(f"Template de acesso criado em: {access_config}")
        return 0

    server = CfoSyncHttpServer(
        host=args.host,
        port=args.port,
        app_config_path=app_config,
        access_config_path=access_config,
        worker_count=args.workers,
    )
    print("Servidor CFO Sync iniciado.")
    print(f"Bind: http://{args.host}:{args.port}")
    print(f"App config: {app_config}")
    print(f"Access config: {access_config}")
    print(
        "Endpoints: GET /v1/health | GET /v1/catalog | POST /v1/jobs | "
        "GET /v1/jobs/{id} | POST /v1/clients | POST /v1/generators/link | "
        "GET /v1/oauth/mercado_livre/callback"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
    return 0


def _write_access_template(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(48)
    payload = {
        "tokens": [
            {
                "name": "analista_principal",
                "token": token,
                "allowed_platforms": ["*"],
                "allowed_clients": {"*": ["*"]},
            }
        ]
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())

