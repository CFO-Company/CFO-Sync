from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from cfo_sync.core.config_loader import load_app_config
from cfo_sync.core.models import AppConfig
from cfo_sync.core.pipeline import SyncPipeline
from cfo_sync.platforms.ui_registry import build_platform_ui_registry
from cfo_sync.server.access import AccessTokenPolicy
from cfo_sync.version import __version__


class CfoSyncServerService:
    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path
        self.config = load_app_config(config_path)
        self.platform_ui_registry = build_platform_ui_registry(self.config)

    def health_payload(self) -> dict[str, object]:
        return {
            "status": "ok",
            "version": __version__,
            "server_time": datetime.now(timezone.utc).isoformat(),
        }

    def build_catalog(self, policy: AccessTokenPolicy) -> dict[str, object]:
        platforms: list[dict[str, object]] = []
        for platform in self.config.platforms:
            if not policy.allows_platform(platform.key):
                continue

            behavior = self.platform_ui_registry.get(platform.key)
            clients = list(platform.clients)
            if behavior is not None:
                try:
                    clients = behavior.companies(clients)
                except Exception:  # noqa: BLE001
                    pass

            visible_clients: list[dict[str, object]] = []
            for client in clients:
                if not policy.allows_client(platform.key, client):
                    continue

                sub_clients: list[str] = []
                if behavior is not None:
                    try:
                        sub_clients = list(behavior.sub_client_names(client))
                    except Exception:  # noqa: BLE001
                        sub_clients = []
                visible_clients.append(
                    {
                        "name": client,
                        "sub_clients": sub_clients,
                    }
                )

            if not visible_clients:
                continue

            resources = [
                {
                    "name": resource.name,
                    "endpoint": resource.endpoint,
                    "field_map": dict(resource.field_map),
                }
                for resource in platform.resources
            ]
            platforms.append(
                {
                    "key": platform.key,
                    "label": platform.label,
                    "resources": resources,
                    "clients": visible_clients,
                }
            )

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "platforms": platforms,
        }

    def run_job(
        self,
        payload: dict[str, object],
        policy: AccessTokenPolicy,
        log: Callable[[str], None],
    ) -> dict[str, object]:
        action = str(payload.get("action") or "").strip().lower()
        platform_key = str(payload.get("platform_key") or "").strip()
        client = str(payload.get("client") or "").strip()
        start_date = _optional_string(payload.get("start_date"))
        end_date = _optional_string(payload.get("end_date"))
        resource_names = _optional_string_list(payload.get("resource_names"))
        sub_clients = _optional_string_list(payload.get("sub_clients"))

        self._validate_access(policy, platform_key, client)
        log(f"Executando action={action} platform={platform_key} client={client}")

        pipeline = SyncPipeline(self.config)
        if action == "collect":
            count = pipeline.collect(
                platform_key=platform_key,
                client=client,
                start_date=start_date,
                end_date=end_date,
                resource_names=resource_names,
                sub_clients=sub_clients,
            )
            return {
                "action": action,
                "platform_key": platform_key,
                "client": client,
                "count": count,
            }

        if action == "export":
            count = pipeline.export_to_sheets(
                platform_key=platform_key,
                client=client,
                start_date=start_date,
                end_date=end_date,
                resource_names=resource_names,
                sub_clients=sub_clients,
            )
            return {
                "action": action,
                "platform_key": platform_key,
                "client": client,
                "count": count,
            }

        raise ValueError("Acao invalida. Use 'collect' ou 'export'.")

    def _validate_access(self, policy: AccessTokenPolicy, platform_key: str, client: str) -> None:
        if not platform_key:
            raise ValueError("Campo obrigatorio ausente: platform_key")
        if not client:
            raise ValueError("Campo obrigatorio ausente: client")
        if not policy.allows_platform(platform_key):
            raise PermissionError(f"Token sem permissao para plataforma '{platform_key}'.")
        if not policy.allows_client(platform_key, client):
            raise PermissionError(
                f"Token sem permissao para cliente '{client}' na plataforma '{platform_key}'."
            )


def serialize_job(job_state) -> dict[str, object]:
    return {
        "id": job_state.id,
        "requested_by": job_state.requested_by,
        "status": job_state.status,
        "created_at": _serialize_datetime(job_state.created_at),
        "started_at": _serialize_datetime(job_state.started_at),
        "finished_at": _serialize_datetime(job_state.finished_at),
        "result": job_state.result,
        "error": job_state.error,
    }


def _serialize_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _optional_string_list(value: object) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError("Campo de lista invalido.")
    cleaned = [str(item).strip() for item in value if str(item).strip()]
    if not cleaned:
        return None
    return cleaned
