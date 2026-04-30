from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Callable

from cfo_sync.core.client_registration import ClientRegistrationManager
from cfo_sync.core.config_loader import load_app_config
from cfo_sync.core.link_generator import GeneratorLinkManager
from cfo_sync.core.pipeline import SyncPipeline
from cfo_sync.platforms.tiktok_ads.api import (
    TikTokAdsAPIError,
    exchange_auth_code_for_access_token,
    fetch_authorized_advertiser_ids,
)
from cfo_sync.platforms.tiktok_ads.credentials import TikTokAdsCredentialsStore
from cfo_sync.platforms.tiktok_shop.api import (
    exchange_auth_code_for_access_token as exchange_tiktok_shop_auth_code_for_access_token,
)
from cfo_sync.platforms.tiktok_shop.credentials import TikTokShopCredentialsStore
from cfo_sync.platforms.ui_registry import build_platform_ui_registry
from cfo_sync.server.access import AccessTokenPolicy
from cfo_sync.version import __version__


class CfoSyncServerService:
    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path
        self._state_lock = RLock()
        self.registration_manager = ClientRegistrationManager(config_path)
        self.generator_manager = GeneratorLinkManager(config_path)
        self._reload_state_locked()

    def _reload_state_locked(self) -> None:
        self.config = load_app_config(self.config_path)
        self.platform_ui_registry = build_platform_ui_registry(self.config)

    def health_payload(self) -> dict[str, object]:
        return {
            "status": "ok",
            "version": __version__,
            "server_time": datetime.now(timezone.utc).isoformat(),
        }

    def build_catalog(self, policy: AccessTokenPolicy) -> dict[str, object]:
        with self._state_lock:
            config = self.config
            platform_ui_registry = self.platform_ui_registry

        platforms: list[dict[str, object]] = []
        for platform in config.platforms:
            if not policy.allows_platform(platform.key):
                continue

            behavior = platform_ui_registry.get(platform.key)
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

        with self._state_lock:
            config = self.config

        pipeline = SyncPipeline(config)
        if self._should_segment_omie_aliases(
            action=action,
            platform_key=platform_key,
            client=client,
            resource_names=resource_names,
            sub_clients=sub_clients,
        ):
            aliases = self._resolve_omie_job_aliases(
                platform_key=platform_key,
                client=client,
                sub_clients=sub_clients,
            )
            return self._run_segmented_omie_job(
                pipeline=pipeline,
                action=action,
                platform_key=platform_key,
                client=client,
                start_date=start_date,
                end_date=end_date,
                resource_names=resource_names,
                aliases=aliases,
                log=log,
            )

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

    def _should_segment_omie_aliases(
        self,
        *,
        action: str,
        platform_key: str,
        client: str,
        resource_names: list[str] | None,
        sub_clients: list[str] | None,
    ) -> bool:
        if action not in {"collect", "export"}:
            return False
        if not platform_key.startswith("omie"):
            return False
        if resource_names and "financeiro" not in resource_names:
            return False
        aliases = self._resolve_omie_job_aliases(
            platform_key=platform_key,
            client=client,
            sub_clients=sub_clients,
        )
        return len(aliases) > 1

    def _resolve_omie_job_aliases(
        self,
        *,
        platform_key: str,
        client: str,
        sub_clients: list[str] | None,
    ) -> list[str]:
        if sub_clients:
            return list(dict.fromkeys(name for name in sub_clients if name.strip()))

        behavior = self.platform_ui_registry.get(platform_key)
        if behavior is None:
            return []
        return list(dict.fromkeys(name for name in behavior.sub_client_names(client) if name.strip()))

    def _run_segmented_omie_job(
        self,
        *,
        pipeline: SyncPipeline,
        action: str,
        platform_key: str,
        client: str,
        start_date: str | None,
        end_date: str | None,
        resource_names: list[str] | None,
        aliases: list[str],
        log: Callable[[str], None],
    ) -> dict[str, object]:
        total_count = 0
        failures: list[str] = []
        period_segments = _month_period_segments(start_date=start_date, end_date=end_date)
        total_segments = len(aliases) * len(period_segments)
        log(
            "Job Omie dividido em partes: "
            f"aliases={len(aliases)} periodos={len(period_segments)} total={total_segments}."
        )

        segment_index = 0
        for alias in aliases:
            for segment_start, segment_end in period_segments:
                segment_index += 1
                period_label = f"{segment_start or ''}..{segment_end or ''}".strip(".")
                log(
                    f"Parte {segment_index}/{total_segments} iniciada: "
                    f"alias={alias} periodo={period_label}"
                )
                try:
                    if action == "collect":
                        count = pipeline.collect(
                            platform_key=platform_key,
                            client=client,
                            start_date=segment_start,
                            end_date=segment_end,
                            resource_names=resource_names,
                            sub_clients=[alias],
                        )
                    else:
                        count = pipeline.export_to_sheets(
                            platform_key=platform_key,
                            client=client,
                            start_date=segment_start,
                            end_date=segment_end,
                            resource_names=resource_names,
                            sub_clients=[alias],
                        )
                except Exception as error:  # noqa: BLE001
                    failures.append(f"{alias} {period_label}: {error}")
                    log(
                        f"Parte {segment_index}/{total_segments} falhou: "
                        f"alias={alias} periodo={period_label} erro={error}"
                    )
                    continue

                total_count += count
                log(
                    f"Parte {segment_index}/{total_segments} concluida: "
                    f"alias={alias} periodo={period_label} registros={count}"
                )

        if failures:
            raise ValueError("Falha em uma ou mais partes Omie: " + " | ".join(failures))

        return {
            "action": action,
            "platform_key": platform_key,
            "client": client,
            "count": total_count,
            "segments": total_segments,
        }

    def register_client(
        self,
        payload: dict[str, object],
        policy: AccessTokenPolicy,
    ) -> dict[str, object]:
        platform_key = str(payload.get("platform_key") or "").strip()
        client_name = str(payload.get("client_name") or payload.get("company_name") or "").strip()
        registration_mode = _registration_mode(payload.get("registration_mode"))
        self._validate_registration_access(
            policy,
            platform_key,
            client_name,
            registration_mode=registration_mode,
        )

        with self._state_lock:
            result = self.registration_manager.register_client(payload)
            self._reload_state_locked()
        return result

    def create_generator_link(
        self,
        payload: dict[str, object],
        *,
        policy: AccessTokenPolicy,
        external_base_url: str,
    ) -> dict[str, object]:
        platform_key = str(payload.get("platform_key") or "").strip()
        client_name = str(payload.get("client_name") or "").strip()
        registration_mode = _registration_mode(payload.get("registration_mode"))
        self._validate_registration_access(
            policy,
            platform_key,
            client_name,
            registration_mode=registration_mode,
        )
        with self._state_lock:
            return self.generator_manager.create_link(payload, external_base_url=external_base_url)

    def list_secret_json_files(self, *, policy: AccessTokenPolicy) -> dict[str, object]:
        self._validate_secrets_access(policy)
        secrets_root = self._secrets_root()
        files: list[dict[str, object]] = []
        if secrets_root.exists():
            for path in sorted(secrets_root.rglob("*.json"), key=lambda item: item.as_posix().casefold()):
                if not path.is_file():
                    continue
                relative_path = path.relative_to(secrets_root).as_posix()
                stat = path.stat()
                files.append(
                    {
                        "path": relative_path,
                        "name": path.name,
                        "size_bytes": stat.st_size,
                        "modified_at": datetime.fromtimestamp(
                            stat.st_mtime,
                            tz=timezone.utc,
                        ).isoformat(),
                    }
                )
        return {
            "secrets_dir": str(secrets_root),
            "files": files,
        }

    def read_secret_json_file(
        self,
        relative_path: str,
        *,
        policy: AccessTokenPolicy,
    ) -> dict[str, object]:
        self._validate_secrets_access(policy)
        path = self._resolve_secret_json_path(relative_path)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError("Arquivo JSON nao encontrado em secrets.")
        content = path.read_text(encoding="utf-8-sig")
        stat = path.stat()
        return {
            "path": path.relative_to(self._secrets_root()).as_posix(),
            "name": path.name,
            "size_bytes": stat.st_size,
            "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            "content": content,
        }

    def update_secret_json_file(
        self,
        relative_path: str,
        content: str,
        *,
        policy: AccessTokenPolicy,
    ) -> dict[str, object]:
        self._validate_secrets_access(policy)
        path = self._resolve_secret_json_path(relative_path)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError("Arquivo JSON nao encontrado em secrets.")

        try:
            json.loads(content)
        except json.JSONDecodeError as error:
            raise ValueError(f"JSON invalido: {error}") from error

        path.write_text(content.rstrip() + "\n", encoding="utf-8")
        if path.resolve() == self.config_path.resolve():
            with self._state_lock:
                self._reload_state_locked()
        return self.read_secret_json_file(relative_path, policy=policy)

    def complete_mercado_livre_oauth_callback(
        self,
        *,
        code: str,
        state: str,
    ) -> dict[str, object]:
        registration_payload = self.generator_manager.consume_mercado_livre_callback(
            code=code,
            state=state,
        )
        with self._state_lock:
            result = self.registration_manager.register_client(registration_payload)
            self._reload_state_locked()
        return result

    def complete_tiktok_ads_oauth_callback(
        self,
        *,
        code: str,
        state: str,
    ) -> dict[str, object]:
        auth_code = str(code or "").strip()
        if not auth_code:
            raise ValueError("auth_code nao informado no callback TikTok Ads.")

        with self._state_lock:
            config = self.config
            credentials_path = config.credentials_dir / config.tiktok_ads.credentials_file
            store = TikTokAdsCredentialsStore.from_file(credentials_path)
            app_id = str(store.auth.app_id or "").strip()
            secret = str(store.auth.secret or "").strip()
            redirect_uri = str(store.auth.redirect_uri or "").strip()
            if not app_id or not secret:
                raise ValueError(
                    "Credenciais TikTok Ads incompletas: informe auth.app_id e auth.secret "
                    "em tiktok_ads_credentials.json."
                )
            if not redirect_uri:
                raise ValueError(
                    "Credenciais TikTok Ads incompletas: informe auth.redirect_uri "
                    "em tiktok_ads_credentials.json."
                )

            access_token = exchange_auth_code_for_access_token(
                app_id=app_id,
                secret=secret,
                auth_code=auth_code,
                redirect_uri=redirect_uri,
            )
            updated_store = store.with_updated_access_token(access_token)
            updated_store.save()
            self._reload_state_locked()

        authorized_ids: list[str] = []
        authorization_warning = ""
        try:
            authorized_ids = fetch_authorized_advertiser_ids(
                access_token=access_token,
                app_id=app_id,
                secret=secret,
            )
        except TikTokAdsAPIError as error:
            authorization_warning = str(error)

        return {
            "platform_key": "tiktok_ads",
            "state": state,
            "redirect_uri": redirect_uri,
            "authorized_advertiser_ids": authorized_ids,
            "authorized_count": len(authorized_ids),
            "access_token_masked": _mask_secret(access_token),
            "warning": authorization_warning,
        }

    def complete_tiktok_shop_oauth_callback(
        self,
        *,
        code: str,
        state: str,
    ) -> dict[str, object]:
        auth_code = str(code or "").strip()
        if not auth_code:
            raise ValueError("auth_code nao informado no callback TikTok Shop.")

        with self._state_lock:
            config = self.config
            credentials_path = config.credentials_dir / config.tiktok_shop.credentials_file
            store = TikTokShopCredentialsStore.from_file(credentials_path)
            app_key = str(store.auth.app_key or "").strip()
            app_secret = str(store.auth.app_secret or "").strip()
            redirect_uri = str(store.auth.redirect_uri or "").strip()
            if not app_key or not app_secret:
                raise ValueError(
                    "Credenciais TikTok Shop incompletas: informe auth.app_key e auth.app_secret "
                    "em tiktok_shop_credentials.json."
                )
            if not redirect_uri:
                raise ValueError(
                    "Credenciais TikTok Shop incompletas: informe auth.redirect_uri "
                    "em tiktok_shop_credentials.json."
                )

            token_bundle = exchange_tiktok_shop_auth_code_for_access_token(
                app_key=app_key,
                app_secret=app_secret,
                auth_code=auth_code,
                redirect_uri=redirect_uri,
            )
            access_token = str(token_bundle.get("access_token") or "").strip()
            refresh_token = str(token_bundle.get("refresh_token") or "").strip()
            shop_cipher = str(token_bundle.get("shop_cipher") or "").strip()
            shop_id = str(token_bundle.get("shop_id") or "").strip()
            seller_name = str(token_bundle.get("seller_name") or "").strip()

            updated_store = store.with_updated_tokens(
                access_token=access_token,
                refresh_token=refresh_token or None,
                shop_cipher=shop_cipher or None,
                shop_id=shop_id or None,
            )
            if seller_name:
                updated_store = updated_store.with_upsert_account(
                    company_name=seller_name,
                    account_name=seller_name,
                    shop_cipher=shop_cipher,
                    shop_id=shop_id,
                    access_token=access_token,
                )
            updated_store.save()
            self._reload_state_locked()

        return {
            "platform_key": "tiktok_shop",
            "state": state,
            "redirect_uri": redirect_uri,
            "shop_id": shop_id,
            "shop_cipher": shop_cipher,
            "seller_name": seller_name,
            "access_token_masked": _mask_secret(access_token),
            "refresh_token_masked": _mask_secret(refresh_token),
        }

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

    def _validate_secrets_access(self, policy: AccessTokenPolicy) -> None:
        if not policy.can_manage_secrets:
            raise PermissionError(
                "Token sem permissao para visualizar/editar secrets. "
                "Ative can_manage_secrets no server_access.json."
            )

    def _secrets_root(self) -> Path:
        return self.config_path.parent.resolve()

    def _resolve_secret_json_path(self, relative_path: str) -> Path:
        cleaned = str(relative_path or "").replace("\\", "/").strip().lstrip("/")
        if not cleaned:
            raise ValueError("Informe o arquivo JSON de secrets.")
        if cleaned.endswith("/") or Path(cleaned).is_absolute():
            raise ValueError("Caminho invalido para arquivo de secrets.")
        path = (self._secrets_root() / cleaned).resolve()
        if self._secrets_root() not in path.parents:
            raise ValueError("Caminho fora da pasta secrets.")
        if path.suffix.casefold() != ".json":
            raise ValueError("Somente arquivos .json da pasta secrets podem ser acessados.")
        return path

    def _validate_registration_access(
        self,
        policy: AccessTokenPolicy,
        platform_key: str,
        client_name: str,
        *,
        registration_mode: str,
    ) -> None:
        if not platform_key:
            raise ValueError("Campo obrigatorio ausente: platform_key")
        if not client_name:
            raise ValueError("Campo obrigatorio ausente: client_name")
        if not policy.allows_platform(platform_key):
            raise PermissionError(f"Token sem permissao para plataforma '{platform_key}'.")
        if registration_mode == "new_client":
            return
        if not policy.allows_client(platform_key, client_name):
            raise PermissionError(
                f"Token sem permissao para cliente '{client_name}' na plataforma '{platform_key}'."
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


def _month_period_segments(
    *,
    start_date: str | None,
    end_date: str | None,
) -> list[tuple[str | None, str | None]]:
    if not start_date or not end_date:
        return [(start_date, end_date)]

    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
    except ValueError:
        return [(start_date, end_date)]

    if start > end:
        return [(start_date, end_date)]

    segments: list[tuple[str | None, str | None]] = []
    current = start
    while current <= end:
        if current.month == 12:
            next_month = date(current.year + 1, 1, 1)
        else:
            next_month = date(current.year, current.month + 1, 1)
        segment_end = min(end, next_month.replace(day=1) - date.resolution)
        segments.append((current.isoformat(), segment_end.isoformat()))
        current = next_month
    return segments


def _registration_mode(value: object) -> str:
    cleaned = str(value or "").strip().casefold()
    if cleaned in {"", "existing_client", "existing", "alias", "filial"}:
        return "existing_client"
    if cleaned in {"new_client", "new", "novo_cliente"}:
        return "new_client"
    raise ValueError(
        "Modo de cadastro invalido. Use 'existing_client' para filial/alias "
        "ou 'new_client' para novo cliente."
    )


def _mask_secret(value: str) -> str:
    text = str(value or "").strip()
    if len(text) <= 8:
        return "*" * len(text)
    return f"{text[:4]}...{text[-4:]}"
