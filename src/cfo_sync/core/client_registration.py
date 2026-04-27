from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cfo_sync.core.config_loader import load_app_config


class ClientRegistrationManager:
    def __init__(self, app_config_path: Path) -> None:
        self.app_config_path = app_config_path

    def register_client(self, payload: dict[str, object]) -> dict[str, object]:
        app_config = load_app_config(self.app_config_path)

        registration_mode = _registration_mode(payload.get("registration_mode"))
        platform_key = _required_text(payload.get("platform_key"), field_name="platform_key")
        requested_client_name = _required_text(
            payload.get("client_name") or payload.get("company_name"),
            field_name="client_name",
        )
        gid = _parse_gid(payload.get("gid"), field_name="gid")
        credentials = _required_dict(payload.get("credentials"), field_name="credentials")
        resource_gids = _optional_resource_gids(payload.get("resource_gids"))

        platform = next((item for item in app_config.platforms if item.key == platform_key), None)
        if platform is None:
            raise ValueError(f"Plataforma nao registrada: {platform_key}")

        if registration_mode == "new_client":
            client_name = _resolve_new_name(
                candidates=platform.clients,
                requested=requested_client_name,
                conflict_message=(
                    f"Cliente '{requested_client_name}' ja existe na plataforma '{platform_key}'. "
                    "Use o modo de cadastro de filial/alias para adicionar nova conta."
                ),
            )
        else:
            client_name = _resolve_existing_name(
                candidates=platform.clients,
                requested=requested_client_name,
                not_found_message=(
                    f"Cliente '{requested_client_name}' nao encontrado na plataforma '{platform_key}'. "
                    "Selecione um cliente existente."
                ),
            )

        credentials_path = self._resolve_credentials_path(app_config=app_config, platform_key=platform_key)
        self._append_credentials(
            registration_mode=registration_mode,
            platform_key=platform_key,
            credentials_path=credentials_path,
            client_name=client_name,
            gid=gid,
            credentials=credentials,
        )

        updated_resources: list[str] = []
        if not platform_key.startswith("omie"):
            if registration_mode == "new_client":
                updated_resources = self._add_new_client_in_app_config(
                    platform_key=platform_key,
                    client_name=client_name,
                    default_gid=gid,
                    resource_gids=resource_gids,
                )
            else:
                updated_resources = self._update_existing_client_tabs_in_app_config(
                    platform_key=platform_key,
                    client_name=client_name,
                    default_gid=gid,
                    resource_gids=resource_gids,
                )

        return {
            "message": "Cadastro registrado com sucesso.",
            "registration_mode": registration_mode,
            "platform_key": platform_key,
            "client_name": client_name,
            "updated_resources": updated_resources,
            "updated_files": [str(self.app_config_path), str(credentials_path)],
        }

    def _resolve_credentials_path(self, *, app_config, platform_key: str) -> Path:
        credentials_dir = app_config.credentials_dir
        if platform_key == "yampi":
            return credentials_dir / app_config.yampi.credentials_file
        if platform_key == "meta_ads":
            return credentials_dir / app_config.meta_ads.credentials_file
        if platform_key == "google_ads":
            return credentials_dir / app_config.google_ads.credentials_file
        if platform_key == "tiktok_ads":
            return credentials_dir / app_config.tiktok_ads.credentials_file
        if platform_key == "tiktok_shop":
            return credentials_dir / app_config.tiktok_shop.credentials_file
        if platform_key == "mercado_livre":
            return credentials_dir / "mercado_livre_credentials.json"
        if platform_key in {"omie", "omie_2026"}:
            return credentials_dir / "omie_credentials.json"
        if platform_key == "omie_2025":
            return credentials_dir / "omie_2025.json"
        raise ValueError(f"Plataforma sem mapeamento de credenciais: {platform_key}")

    def _append_credentials(
        self,
        *,
        registration_mode: str,
        platform_key: str,
        credentials_path: Path,
        client_name: str,
        gid: str,
        credentials: dict[str, object],
    ) -> None:
        payload = _read_json_file(credentials_path)

        if registration_mode == "new_client":
            if platform_key == "yampi":
                _create_yampi_client_credentials(payload, client_name, credentials)
            elif platform_key == "meta_ads":
                _create_meta_ads_client_credentials(payload, client_name, credentials)
            elif platform_key == "google_ads":
                _create_google_ads_client_credentials(payload, client_name, credentials)
            elif platform_key == "tiktok_ads":
                _create_tiktok_ads_client_credentials(payload, client_name, credentials)
            elif platform_key == "tiktok_shop":
                _create_tiktok_shop_client_credentials(payload, client_name, credentials)
            elif platform_key == "mercado_livre":
                _create_mercado_livre_client_credentials(payload, client_name, credentials)
            elif platform_key.startswith("omie"):
                _create_omie_client_credentials(payload, client_name, gid, credentials)
            else:
                raise ValueError(f"Plataforma sem suporte para cadastro: {platform_key}")
        else:
            if platform_key == "yampi":
                _append_yampi_credentials(payload, client_name, credentials)
            elif platform_key == "meta_ads":
                _append_meta_ads_credentials(payload, client_name, credentials)
            elif platform_key == "google_ads":
                _append_google_ads_credentials(payload, client_name, credentials)
            elif platform_key == "tiktok_ads":
                _append_tiktok_ads_credentials(payload, client_name, credentials)
            elif platform_key == "tiktok_shop":
                _append_tiktok_shop_credentials(payload, client_name, credentials)
            elif platform_key == "mercado_livre":
                _upsert_mercado_livre_credentials(payload, client_name, credentials)
            elif platform_key.startswith("omie"):
                _append_omie_credentials(payload, client_name, gid, credentials)
            else:
                raise ValueError(f"Plataforma sem suporte para cadastro: {platform_key}")

        _write_json_file(credentials_path, payload)

    def _add_new_client_in_app_config(
        self,
        *,
        platform_key: str,
        client_name: str,
        default_gid: str,
        resource_gids: dict[str, str],
    ) -> list[str]:
        payload = _read_json_file(self.app_config_path)

        platforms = payload.get("platforms")
        if not isinstance(platforms, list):
            raise ValueError("app_config.json invalido: campo 'platforms' ausente.")

        platform_data = None
        for item in platforms:
            if not isinstance(item, dict):
                continue
            if str(item.get("key") or "").strip() == platform_key:
                platform_data = item
                break
        if platform_data is None:
            raise ValueError(f"Plataforma '{platform_key}' nao encontrada no app_config.json.")

        raw_clients = platform_data.get("clients")
        if not isinstance(raw_clients, list):
            raise ValueError(
                f"app_config.json invalido para '{platform_key}': 'clients' deve ser lista."
            )

        if _find_key_case_insensitive(raw_clients, client_name) is not None:
            raise ValueError(
                f"Cliente '{client_name}' ja existe em app_config na plataforma '{platform_key}'."
            )
        raw_clients.append(client_name)
        platform_data["clients"] = raw_clients

        resources = platform_data.get("resources")
        if not isinstance(resources, list):
            raise ValueError(
                f"app_config.json invalido para '{platform_key}': 'resources' deve ser lista."
            )

        updated_resources: list[str] = []
        for resource in resources:
            if not isinstance(resource, dict):
                continue

            resource_name = str(resource.get("name") or "").strip()
            if not resource_name:
                continue

            gid = resource_gids.get(resource_name, default_gid)
            if not gid:
                continue

            client_tabs = resource.get("client_tabs")
            if not isinstance(client_tabs, dict):
                client_tabs = {}
                resource["client_tabs"] = client_tabs

            if _find_key_case_insensitive(client_tabs.keys(), client_name) is not None:
                raise ValueError(
                    f"Cliente '{client_name}' ja existe no recurso '{resource_name}' de '{platform_key}'."
                )

            client_tabs[client_name] = {
                "tab_name": "",
                "gid": gid,
            }
            updated_resources.append(resource_name)

        _write_json_file(self.app_config_path, payload)
        return updated_resources

    def _update_existing_client_tabs_in_app_config(
        self,
        *,
        platform_key: str,
        client_name: str,
        default_gid: str,
        resource_gids: dict[str, str],
    ) -> list[str]:
        payload = _read_json_file(self.app_config_path)

        platforms = payload.get("platforms")
        if not isinstance(platforms, list):
            raise ValueError("app_config.json invalido: campo 'platforms' ausente.")

        platform_data = None
        for item in platforms:
            if not isinstance(item, dict):
                continue
            if str(item.get("key") or "").strip() == platform_key:
                platform_data = item
                break
        if platform_data is None:
            raise ValueError(f"Plataforma '{platform_key}' nao encontrada no app_config.json.")

        raw_clients = platform_data.get("clients")
        if not isinstance(raw_clients, list):
            raise ValueError(
                f"app_config.json invalido para '{platform_key}': 'clients' deve ser lista."
            )

        resolved_client_name = _resolve_existing_name(
            candidates=raw_clients,
            requested=client_name,
            not_found_message=(
                f"Cliente '{client_name}' nao encontrado em app_config na plataforma '{platform_key}'."
            ),
        )

        resources = platform_data.get("resources")
        if not isinstance(resources, list):
            raise ValueError(
                f"app_config.json invalido para '{platform_key}': 'resources' deve ser lista."
            )

        updated_resources: list[str] = []
        for resource in resources:
            if not isinstance(resource, dict):
                continue

            resource_name = str(resource.get("name") or "").strip()
            if not resource_name:
                continue

            gid = resource_gids.get(resource_name, default_gid)
            if not gid:
                continue

            client_tabs = resource.get("client_tabs")
            if not isinstance(client_tabs, dict):
                client_tabs = {}
                resource["client_tabs"] = client_tabs

            key_in_tabs = _find_key_case_insensitive(client_tabs.keys(), resolved_client_name)
            target_key = key_in_tabs or resolved_client_name

            current = client_tabs.get(target_key)
            updated_tab: dict[str, object] = {}
            if isinstance(current, dict):
                updated_tab.update(current)
            updated_tab["gid"] = gid
            updated_tab.setdefault("tab_name", "")
            client_tabs[target_key] = updated_tab
            updated_resources.append(resource_name)

        _write_json_file(self.app_config_path, payload)
        return updated_resources


def _append_yampi_credentials(payload: dict[str, Any], client_name: str, credentials: dict[str, object]) -> None:
    companies = _required_dict(payload.get("companies"), field_name="companies")
    company_key = _resolve_existing_company_key(companies, client_name, platform_label="Yampi")

    aliases = companies.get(company_key)
    if not isinstance(aliases, list):
        raise ValueError(f"Formato invalido em Yampi para cliente '{company_key}': esperado lista.")

    alias = _required_text(credentials.get("alias"), field_name="credentials.alias")
    _ensure_unique_alias(aliases, alias, platform_label="Yampi")

    alias_payload = _build_yampi_alias_payload(credentials)
    alias_payload["alias"] = alias
    aliases.append(alias_payload)
    companies[company_key] = aliases
    payload["companies"] = companies


def _create_yampi_client_credentials(
    payload: dict[str, Any],
    client_name: str,
    credentials: dict[str, object],
) -> None:
    companies = _required_dict(payload.get("companies"), field_name="companies")
    _ensure_new_company_key(companies, client_name, platform_label="Yampi")
    companies[client_name] = [_build_yampi_alias_payload(credentials)]
    payload["companies"] = companies


def _append_meta_ads_credentials(
    payload: dict[str, Any],
    client_name: str,
    credentials: dict[str, object],
) -> None:
    accounts = payload.get("accounts")
    if not isinstance(accounts, list):
        raise ValueError("Credenciais Meta Ads invalidas: campo 'accounts' ausente.")

    normalized_target = client_name.strip().casefold()
    account_id = _required_text(credentials.get("account_id"), field_name="credentials.account_id")
    for account in accounts:
        if not isinstance(account, dict):
            continue
        same_company = str(account.get("company_name") or "").strip().casefold() == normalized_target
        same_account_id = str(account.get("account_id") or "").strip() == account_id
        if same_company and same_account_id:
            raise ValueError(
                f"Conta Meta Ads '{account_id}' ja cadastrada para cliente '{client_name}'."
            )

    accounts.append(
        {
            "company_name": client_name,
            "business_manager_name": _required_text(
                credentials.get("business_manager_name"),
                field_name="credentials.business_manager_name",
            ),
            "ad_account_name": _required_text(
                credentials.get("ad_account_name"),
                field_name="credentials.ad_account_name",
            ),
            "cost_center": _optional_text(credentials.get("cost_center")),
            "account_id": account_id,
        }
    )
    payload["accounts"] = accounts


def _create_meta_ads_client_credentials(
    payload: dict[str, Any],
    client_name: str,
    credentials: dict[str, object],
) -> None:
    accounts = payload.get("accounts")
    if not isinstance(accounts, list):
        raise ValueError("Credenciais Meta Ads invalidas: campo 'accounts' ausente.")
    _ensure_company_not_in_accounts(accounts, client_name, platform_label="Meta Ads")
    _append_meta_ads_credentials(payload, client_name, credentials)


def _append_google_ads_credentials(
    payload: dict[str, Any],
    client_name: str,
    credentials: dict[str, object],
) -> None:
    accounts = payload.get("accounts")
    if not isinstance(accounts, list):
        raise ValueError("Credenciais Google Ads invalidas: campo 'accounts' ausente.")

    normalized_target = client_name.strip().casefold()
    customer_id = _digits_only(
        _required_text(credentials.get("customer_id"), field_name="credentials.customer_id"),
        field_name="credentials.customer_id",
    )
    for account in accounts:
        if not isinstance(account, dict):
            continue
        same_company = str(account.get("company_name") or "").strip().casefold() == normalized_target
        same_customer = _digits_only_optional(str(account.get("customer_id") or ""))
        if same_company and same_customer == customer_id:
            raise ValueError(
                f"Conta Google Ads '{customer_id}' ja cadastrada para cliente '{client_name}'."
            )

    accounts.append(
        {
            "company_name": client_name,
            "account_name": _required_text(credentials.get("account_name"), field_name="credentials.account_name"),
            "customer_id": customer_id,
            "cost_center": _optional_text(credentials.get("cost_center")),
            "manager_account_name": _optional_text(credentials.get("manager_account_name")),
        }
    )
    payload["accounts"] = accounts


def _create_google_ads_client_credentials(
    payload: dict[str, Any],
    client_name: str,
    credentials: dict[str, object],
) -> None:
    accounts = payload.get("accounts")
    if not isinstance(accounts, list):
        raise ValueError("Credenciais Google Ads invalidas: campo 'accounts' ausente.")
    _ensure_company_not_in_accounts(accounts, client_name, platform_label="Google Ads")
    _append_google_ads_credentials(payload, client_name, credentials)


def _append_tiktok_ads_credentials(
    payload: dict[str, Any],
    client_name: str,
    credentials: dict[str, object],
) -> None:
    accounts = payload.get("accounts")
    if not isinstance(accounts, list):
        raise ValueError("Credenciais TikTok Ads invalidas: campo 'accounts' ausente.")

    normalized_target = client_name.strip().casefold()
    advertiser_id = _digits_only(
        _required_text(credentials.get("advertiser_id"), field_name="credentials.advertiser_id"),
        field_name="credentials.advertiser_id",
    )
    for account in accounts:
        if not isinstance(account, dict):
            continue
        same_company = str(account.get("company_name") or "").strip().casefold() == normalized_target
        same_advertiser = _digits_only_optional(str(account.get("advertiser_id") or ""))
        if same_company and same_advertiser == advertiser_id:
            raise ValueError(
                f"Conta TikTok Ads '{advertiser_id}' ja cadastrada para cliente '{client_name}'."
            )

    accounts.append(
        {
            "company_name": client_name,
            "account_name": _required_text(credentials.get("account_name"), field_name="credentials.account_name"),
            "advertiser_id": advertiser_id,
            "cost_center": _optional_text(credentials.get("cost_center")),
            "business_center_name": _optional_text(credentials.get("business_center_name")),
            "access_token": _optional_text(credentials.get("access_token")),
        }
    )
    payload["accounts"] = accounts


def _create_tiktok_ads_client_credentials(
    payload: dict[str, Any],
    client_name: str,
    credentials: dict[str, object],
) -> None:
    accounts = payload.get("accounts")
    if not isinstance(accounts, list):
        raise ValueError("Credenciais TikTok Ads invalidas: campo 'accounts' ausente.")
    _ensure_company_not_in_accounts(accounts, client_name, platform_label="TikTok Ads")
    _append_tiktok_ads_credentials(payload, client_name, credentials)


def _append_tiktok_shop_credentials(
    payload: dict[str, Any],
    client_name: str,
    credentials: dict[str, object],
) -> None:
    accounts = payload.get("accounts")
    if not isinstance(accounts, list):
        raise ValueError("Credenciais TikTok Shop invalidas: campo 'accounts' ausente.")

    normalized_target = client_name.strip().casefold()
    shop_cipher = _required_text(credentials.get("shop_cipher"), field_name="credentials.shop_cipher")
    shop_id = _optional_text(credentials.get("shop_id"))
    for account in accounts:
        if not isinstance(account, dict):
            continue
        same_company = str(account.get("company_name") or "").strip().casefold() == normalized_target
        same_shop_cipher = str(account.get("shop_cipher") or "").strip() == shop_cipher
        same_shop_id = bool(shop_id) and str(account.get("shop_id") or "").strip() == shop_id
        if same_company and (same_shop_cipher or same_shop_id):
            duplicate_ref = shop_cipher if same_shop_cipher else shop_id
            raise ValueError(
                f"Conta TikTok Shop '{duplicate_ref}' ja cadastrada para cliente '{client_name}'."
            )

    accounts.append(
        {
            "company_name": client_name,
            "account_name": _required_text(credentials.get("account_name"), field_name="credentials.account_name"),
            "shop_cipher": shop_cipher,
            "shop_id": shop_id,
            "access_token": _optional_text(credentials.get("access_token")),
        }
    )
    payload["accounts"] = accounts


def _create_tiktok_shop_client_credentials(
    payload: dict[str, Any],
    client_name: str,
    credentials: dict[str, object],
) -> None:
    accounts = payload.get("accounts")
    if not isinstance(accounts, list):
        raise ValueError("Credenciais TikTok Shop invalidas: campo 'accounts' ausente.")
    _ensure_company_not_in_accounts(accounts, client_name, platform_label="TikTok Shop")
    _append_tiktok_shop_credentials(payload, client_name, credentials)


def _upsert_mercado_livre_credentials(
    payload: dict[str, Any],
    client_name: str,
    credentials: dict[str, object],
) -> None:
    companies = payload.get("companies")
    if not isinstance(companies, dict):
        raise ValueError("Credenciais Mercado Livre invalidas: secao 'companies' ausente.")

    company_key = _resolve_existing_company_key(
        companies,
        client_name,
        platform_label="Mercado Livre",
    )
    company_payload = companies.get(company_key)
    if not isinstance(company_payload, dict):
        company_payload = {}

    accounts = _normalize_mercado_livre_accounts(company_payload)
    new_auth_payload = _build_mercado_livre_auth_payload(credentials)
    matching_index = _find_mercado_livre_account_index(
        accounts=accounts,
        auth_payload=new_auth_payload,
    )

    account_entry = {"auth": new_auth_payload}
    if matching_index is None:
        accounts.append(account_entry)
    else:
        accounts[matching_index] = account_entry

    company_payload["accounts"] = accounts
    if accounts:
        first_auth = accounts[0].get("auth")
        if isinstance(first_auth, dict):
            # Mantem compatibilidade com formato legado (company.auth unico).
            company_payload["auth"] = dict(first_auth)

    companies[company_key] = company_payload
    payload["companies"] = companies


def _create_mercado_livre_client_credentials(
    payload: dict[str, Any],
    client_name: str,
    credentials: dict[str, object],
) -> None:
    companies = payload.get("companies")
    if not isinstance(companies, dict):
        raise ValueError("Credenciais Mercado Livre invalidas: secao 'companies' ausente.")
    _ensure_new_company_key(companies, client_name, platform_label="Mercado Livre")
    auth_payload = _build_mercado_livre_auth_payload(credentials)
    companies[client_name] = {
        "accounts": [{"auth": auth_payload}],
        # Mantem compatibilidade com formato legado (company.auth unico).
        "auth": dict(auth_payload),
    }
    payload["companies"] = companies


def _append_omie_credentials(
    payload: dict[str, Any],
    client_name: str,
    gid: str,
    credentials: dict[str, object],
) -> None:
    companies = _required_dict(payload.get("companies"), field_name="companies")
    company_key = _resolve_existing_company_key(companies, client_name, platform_label="Omie")

    aliases = companies.get(company_key)
    if not isinstance(aliases, list):
        raise ValueError(f"Formato invalido em Omie para cliente '{company_key}': esperado lista.")

    alias = _required_text(credentials.get("alias"), field_name="credentials.alias")
    _ensure_unique_alias(aliases, alias, platform_label="Omie")

    alias_payload = _build_omie_alias_payload(gid=gid, credentials=credentials)
    alias_payload["alias"] = alias
    aliases.append(alias_payload)
    companies[company_key] = aliases
    payload["companies"] = companies


def _create_omie_client_credentials(
    payload: dict[str, Any],
    client_name: str,
    gid: str,
    credentials: dict[str, object],
) -> None:
    companies = _required_dict(payload.get("companies"), field_name="companies")
    _ensure_new_company_key(companies, client_name, platform_label="Omie")
    companies[client_name] = [_build_omie_alias_payload(gid=gid, credentials=credentials)]
    payload["companies"] = companies


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


def _build_yampi_alias_payload(credentials: dict[str, object]) -> dict[str, str]:
    return {
        "alias": _required_text(credentials.get("alias"), field_name="credentials.alias"),
        "user_token": _required_text(
            credentials.get("user_token"),
            field_name="credentials.user_token",
        ),
        "user_secret_key": _required_text(
            credentials.get("user_secret_key"),
            field_name="credentials.user_secret_key",
        ),
    }


def _build_omie_alias_payload(
    *,
    gid: str,
    credentials: dict[str, object],
) -> dict[str, object]:
    return {
        "alias": _required_text(credentials.get("alias"), field_name="credentials.alias"),
        "app_key": _required_text(credentials.get("app_key"), field_name="credentials.app_key"),
        "app_secret": _required_text(
            credentials.get("app_secret"),
            field_name="credentials.app_secret",
        ),
        "app_name": _optional_text(credentials.get("app_name")),
        "include_accounts_payable": _to_bool_like(
            credentials.get("include_accounts_payable", True),
            field_name="credentials.include_accounts_payable",
        ),
        "include_accounts_receivable": _to_bool_like(
            credentials.get("include_accounts_receivable", True),
            field_name="credentials.include_accounts_receivable",
        ),
        "gid": gid,
    }


def _build_mercado_livre_auth_payload(credentials: dict[str, object]) -> dict[str, Any]:
    expires_in = credentials.get("expires_in")
    try:
        parsed_expires_in = int(expires_in) if expires_in is not None else 21600
    except (TypeError, ValueError):
        raise ValueError("credentials.expires_in invalido: use inteiro positivo.") from None
    if parsed_expires_in <= 0:
        parsed_expires_in = 21600

    return {
        "client_id": _required_text(credentials.get("client_id"), field_name="credentials.client_id"),
        "client_secret": _required_text(
            credentials.get("client_secret"),
            field_name="credentials.client_secret",
        ),
        "access_token": _required_text(
            credentials.get("access_token"),
            field_name="credentials.access_token",
        ),
        "refresh_token": _required_text(
            credentials.get("refresh_token"),
            field_name="credentials.refresh_token",
        ),
        "alias": _optional_text(
            credentials.get("account_alias")
            or credentials.get("alias")
            or credentials.get("filial")
        ),
        "user_id": _optional_text(credentials.get("user_id")),
        "token_type": _optional_text(credentials.get("token_type")) or "bearer",
        "expires_in": parsed_expires_in,
        "access_token_expires_at": _optional_text(credentials.get("access_token_expires_at")),
    }


def _normalize_mercado_livre_accounts(company_payload: Any) -> list[dict[str, Any]]:
    if isinstance(company_payload, list):
        normalized_accounts: list[dict[str, Any]] = []
        for item in company_payload:
            if not isinstance(item, dict):
                continue
            for account in _normalize_mercado_livre_accounts(item):
                normalized_accounts.append(account)
        return normalized_accounts

    if not isinstance(company_payload, dict):
        return []

    accounts_raw = company_payload.get("accounts")
    normalized_accounts: list[dict[str, Any]] = []
    if isinstance(accounts_raw, list):
        for item in accounts_raw:
            if not isinstance(item, dict):
                continue
            auth_payload = item.get("auth")
            if isinstance(auth_payload, dict):
                normalized_accounts.append({"auth": dict(auth_payload)})
                continue
            if _looks_like_mercado_livre_auth(item):
                normalized_accounts.append({"auth": dict(item)})
        if normalized_accounts:
            return normalized_accounts

    auth_payload = company_payload.get("auth")
    if isinstance(auth_payload, list):
        for item in auth_payload:
            if not isinstance(item, dict):
                continue
            normalized_accounts.append({"auth": dict(item)})
        if normalized_accounts:
            return normalized_accounts

    if isinstance(auth_payload, dict):
        return [{"auth": dict(auth_payload)}]

    if _looks_like_mercado_livre_auth(company_payload):
        return [{"auth": dict(company_payload)}]

    return []


def _find_mercado_livre_account_index(
    *,
    accounts: list[dict[str, Any]],
    auth_payload: dict[str, Any],
) -> int | None:
    alias_target = _mercado_livre_alias(auth_payload)
    if alias_target:
        for index, account in enumerate(accounts):
            current_auth = account.get("auth")
            if not isinstance(current_auth, dict):
                continue
            if _mercado_livre_alias(current_auth) == alias_target:
                return index

    user_id_target = str(auth_payload.get("user_id") or "").strip().casefold()
    if user_id_target:
        for index, account in enumerate(accounts):
            current_auth = account.get("auth")
            if not isinstance(current_auth, dict):
                continue
            current_user_id = str(current_auth.get("user_id") or "").strip().casefold()
            if current_user_id == user_id_target:
                return index
    return None


def _mercado_livre_alias(auth_payload: dict[str, Any]) -> str:
    return str(
        auth_payload.get("account_alias")
        or auth_payload.get("alias")
        or auth_payload.get("filial")
        or ""
    ).strip().casefold()


def _looks_like_mercado_livre_auth(payload: dict[str, Any]) -> bool:
    return any(
        key in payload
        for key in (
            "client_id",
            "app_id",
            "client_secret",
            "secret_key",
            "access_token",
            "refresh_token",
        )
    )


def _required_text(value: object, *, field_name: str) -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        raise ValueError(f"Campo obrigatorio ausente: {field_name}")
    return cleaned


def _optional_text(value: object) -> str:
    return str(value or "").strip()


def _required_dict(value: object, *, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"Campo '{field_name}' deve ser objeto JSON.")
    return value


def _parse_gid(value: object, *, field_name: str) -> str:
    gid = _required_text(value, field_name=field_name)
    return _digits_only(gid, field_name=field_name)


def _optional_resource_gids(value: object) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("Campo 'resource_gids' deve ser objeto JSON quando informado.")

    result: dict[str, str] = {}
    for resource_name, resource_gid in value.items():
        name = str(resource_name or "").strip()
        if not name:
            continue
        gid = str(resource_gid or "").strip()
        if not gid:
            continue
        result[name] = _digits_only(gid, field_name=f"resource_gids.{name}")
    return result


def _digits_only(value: str, *, field_name: str) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if not digits:
        raise ValueError(
            f"Campo '{field_name}' deve conter o GID da aba (sheetId) em numeros."
        )
    return digits


def _digits_only_optional(value: str) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _resolve_existing_name(
    *,
    candidates: list[str],
    requested: str,
    not_found_message: str,
) -> str:
    key = _find_key_case_insensitive(candidates, requested)
    if key is None:
        raise ValueError(not_found_message)
    return key


def _resolve_new_name(
    *,
    candidates: list[str],
    requested: str,
    conflict_message: str,
) -> str:
    resolved = str(requested or "").strip()
    if _find_key_case_insensitive(candidates, resolved) is not None:
        raise ValueError(conflict_message)
    return resolved


def _resolve_existing_company_key(
    companies: dict[str, Any],
    requested_name: str,
    *,
    platform_label: str,
) -> str:
    key = _find_key_case_insensitive(companies.keys(), requested_name)
    if key is None:
        raise ValueError(
            f"Cliente '{requested_name}' nao encontrado nas credenciais de {platform_label}. "
            "Selecione um cliente existente."
        )
    return key


def _ensure_new_company_key(
    companies: dict[str, Any],
    requested_name: str,
    *,
    platform_label: str,
) -> None:
    key = _find_key_case_insensitive(companies.keys(), requested_name)
    if key is not None:
        raise ValueError(
            f"Cliente '{requested_name}' ja existe nas credenciais de {platform_label}. "
            "Use o modo de cadastro de filial/alias."
        )


def _ensure_company_not_in_accounts(
    accounts: list[Any],
    client_name: str,
    *,
    platform_label: str,
) -> None:
    target = client_name.strip().casefold()
    for account in accounts:
        if not isinstance(account, dict):
            continue
        current = str(account.get("company_name") or "").strip().casefold()
        if current == target:
            raise ValueError(
                f"Cliente '{client_name}' ja existe nas credenciais de {platform_label}. "
                "Use o modo de cadastro de filial/alias."
            )


def _find_key_case_insensitive(values: Any, target: str) -> str | None:
    normalized_target = str(target or "").strip().casefold()
    if not normalized_target:
        return None
    for value in values:
        text = str(value or "").strip()
        if text.casefold() == normalized_target:
            return text
    return None


def _ensure_unique_alias(aliases: list[Any], alias: str, *, platform_label: str) -> None:
    normalized_alias = alias.strip().casefold()
    for item in aliases:
        if not isinstance(item, dict):
            continue
        current_alias = str(item.get("alias") or item.get("alias_name") or "").strip().casefold()
        if current_alias == normalized_alias:
            raise ValueError(f"Alias '{alias}' ja cadastrado em {platform_label}.")


def _to_bool_like(value: object, *, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value or "").strip().casefold()
    if normalized in {"1", "true", "sim", "yes", "y"}:
        return True
    if normalized in {"0", "false", "nao", "não", "no", "n", ""}:
        return False
    raise ValueError(f"Campo '{field_name}' invalido: use true/false ou sim/nao.")


def _read_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Arquivo nao encontrado: {path}")
    try:
        raw_text = path.read_text(encoding="utf-8-sig")
        if path.name.lower() == "mercado_livre_credentials.json":
            loaded = json.loads(raw_text, object_pairs_hook=_json_object_pairs_with_duplicates)
        else:
            loaded = json.loads(raw_text)
    except json.JSONDecodeError as error:
        raise ValueError(f"JSON invalido em {path}: {error}") from error
    if not isinstance(loaded, dict):
        raise ValueError(f"Arquivo JSON invalido em {path}: raiz deve ser objeto.")
    return loaded


def _write_json_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _json_object_pairs_with_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        existing = result.get(key)
        if existing is None:
            result[key] = value
            continue
        if isinstance(existing, list):
            existing.append(value)
            result[key] = existing
            continue
        result[key] = [existing, value]
    return result
