from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class MercadoLivreAuth:
    client_id: str
    client_secret: str
    access_token: str
    refresh_token: str
    account_alias: str = ""
    user_id: str = ""
    token_type: str = "bearer"
    expires_in: int = 21600
    access_token_expires_at: str | None = None


@dataclass(frozen=True)
class _ResolvedAuthPayload:
    auth_payload: dict[str, Any]
    company_name: str | None
    has_companies_section: bool
    selected_account_index: int | None
    account_labels: list[str]


class MercadoLivreCredentialsStore:
    def __init__(
        self,
        credentials_path: Path,
        auth: MercadoLivreAuth,
        raw_payload: dict[str, Any],
        company_name: str | None = None,
        has_companies_section: bool = False,
        selected_account_index: int | None = None,
        account_labels: list[str] | None = None,
    ) -> None:
        self.credentials_path = credentials_path
        self.auth = auth
        self.company_name = company_name
        self.account_labels = list(account_labels or [])
        self._raw_payload = raw_payload
        self._has_companies_section = has_companies_section
        self._selected_account_index = selected_account_index

    @classmethod
    def from_file(
        cls,
        credentials_path: Path,
        company_name: str | None = None,
        account_alias: str | None = None,
    ) -> "MercadoLivreCredentialsStore":
        if not credentials_path.exists():
            raise FileNotFoundError(
                f"Arquivo de credenciais Mercado Livre nao encontrado: {credentials_path}"
            )

        data = _load_json_object_with_duplicates(credentials_path.read_text(encoding="utf-8-sig"))
        resolved = cls._resolve_auth_payload(
            data=data,
            company_name=company_name,
            account_alias=account_alias,
        )
        auth_payload = resolved.auth_payload

        client_id = str(auth_payload.get("client_id") or auth_payload.get("app_id") or "").strip()
        client_secret = str(auth_payload.get("client_secret") or auth_payload.get("secret_key") or "").strip()
        access_token = str(auth_payload.get("access_token") or "").strip()
        refresh_token = str(auth_payload.get("refresh_token") or "").strip()

        if not client_id or not client_secret:
            raise ValueError(
                "Credenciais Mercado Livre invalidas: client_id/app_id e client_secret/secret_key sao obrigatorios."
            )
        if not access_token or not refresh_token:
            raise ValueError(
                "Credenciais Mercado Livre invalidas: access_token e refresh_token sao obrigatorios."
            )

        expires_in = cls._to_int(auth_payload.get("expires_in"), default=21600)
        auth = MercadoLivreAuth(
            client_id=client_id,
            client_secret=client_secret,
            access_token=access_token,
            refresh_token=refresh_token,
            account_alias=cls._extract_alias(auth_payload) or "",
            user_id=str(auth_payload.get("user_id") or "").strip(),
            token_type=str(auth_payload.get("token_type") or "bearer").strip() or "bearer",
            expires_in=expires_in,
            access_token_expires_at=cls._normalize_iso(auth_payload.get("access_token_expires_at")),
        )
        return cls(
            credentials_path=credentials_path,
            auth=auth,
            raw_payload=data,
            company_name=resolved.company_name,
            has_companies_section=resolved.has_companies_section,
            selected_account_index=resolved.selected_account_index,
            account_labels=resolved.account_labels,
        )

    def save(self) -> None:
        auth_payload = self._auth_to_payload()

        if self._has_companies_section:
            payload = dict(self._raw_payload)
            companies = payload.get("companies")
            if not isinstance(companies, dict):
                raise ValueError(
                    "Formato invalido de credenciais Mercado Livre: secao 'companies' ausente ou invalida."
                )

            if not self.company_name:
                raise ValueError(
                    "Nao foi possivel salvar credenciais Mercado Livre: cliente nao informado para secao 'companies'."
                )

            company_payload = companies.get(self.company_name)
            if isinstance(company_payload, dict):
                updated_company_payload = dict(company_payload)
            else:
                updated_company_payload = {}

            accounts = self._extract_company_accounts(updated_company_payload)
            if accounts:
                target_index = self._resolve_target_account_index(accounts)
                target_entry = dict(accounts[target_index])
                target_entry["auth"] = auth_payload
                accounts[target_index] = target_entry
            else:
                accounts = [{"auth": auth_payload}]

            updated_company_payload["accounts"] = accounts
            first_auth = accounts[0].get("auth")
            if isinstance(first_auth, dict):
                # Mantem compatibilidade com formato legado (company.auth unico).
                updated_company_payload["auth"] = dict(first_auth)
            else:
                updated_company_payload["auth"] = auth_payload

            companies[self.company_name] = updated_company_payload
            payload["companies"] = companies
        else:
            payload = dict(self._raw_payload)
            payload["auth"] = auth_payload

        self.credentials_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def with_updated_tokens(
        self,
        *,
        access_token: str,
        refresh_token: str,
        expires_in: int,
        user_id: str | None = None,
        token_type: str | None = None,
    ) -> "MercadoLivreCredentialsStore":
        expires_at = datetime.now(UTC) + timedelta(seconds=max(0, int(expires_in)))
        updated_auth = replace(
            self.auth,
            access_token=access_token.strip(),
            refresh_token=refresh_token.strip(),
            expires_in=max(0, int(expires_in)),
            user_id=(user_id if user_id is not None else self.auth.user_id).strip(),
            token_type=(token_type if token_type is not None else self.auth.token_type).strip() or "bearer",
            access_token_expires_at=expires_at.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        )
        return MercadoLivreCredentialsStore(
            credentials_path=self.credentials_path,
            auth=updated_auth,
            raw_payload=self._raw_payload,
            company_name=self.company_name,
            has_companies_section=self._has_companies_section,
            selected_account_index=self._selected_account_index,
            account_labels=self.account_labels,
        )

    def access_token_expired(self, tolerance_seconds: int = 120) -> bool:
        expires_at_raw = self.auth.access_token_expires_at
        if not expires_at_raw:
            return True

        expires_at = self._parse_iso_utc(expires_at_raw)
        if expires_at is None:
            return True

        limit = datetime.now(UTC) + timedelta(seconds=max(0, tolerance_seconds))
        return expires_at <= limit

    def _resolve_target_account_index(self, accounts: list[dict[str, Any]]) -> int:
        if not accounts:
            return 0

        if self._selected_account_index is not None:
            if 0 <= self._selected_account_index < len(accounts):
                return self._selected_account_index

        preferred_alias = self.auth.account_alias
        if preferred_alias:
            found = self._find_account_index(accounts=accounts, requested=preferred_alias)
            if found is not None:
                return found

        preferred_user_id = self.auth.user_id
        if preferred_user_id:
            found = self._find_account_index_by_user_id(accounts=accounts, requested_user_id=preferred_user_id)
            if found is not None:
                return found

        return 0

    @staticmethod
    def _to_int(value: Any, default: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default
        if parsed <= 0:
            return default
        return parsed

    @staticmethod
    def _to_optional_text(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        return text

    @staticmethod
    def _parse_iso_utc(value: str) -> datetime | None:
        text = str(value).strip()
        if not text:
            return None
        try:
            normalized = text.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    @classmethod
    def _normalize_iso(cls, value: Any) -> str | None:
        if value is None:
            return None
        parsed = cls._parse_iso_utc(str(value))
        if parsed is None:
            return None
        return parsed.replace(microsecond=0).isoformat().replace("+00:00", "Z")

    def _auth_to_payload(self) -> dict[str, Any]:
        return {
            "client_id": self.auth.client_id,
            "client_secret": self.auth.client_secret,
            "access_token": self.auth.access_token,
            "refresh_token": self.auth.refresh_token,
            "alias": self.auth.account_alias,
            "user_id": self.auth.user_id,
            "token_type": self.auth.token_type,
            "expires_in": self.auth.expires_in,
            "access_token_expires_at": self.auth.access_token_expires_at,
        }

    @classmethod
    def _resolve_auth_payload(
        cls,
        data: dict[str, Any],
        company_name: str | None,
        account_alias: str | None,
    ) -> _ResolvedAuthPayload:
        companies = data.get("companies")
        if isinstance(companies, dict):
            requested = (company_name or "").strip()
            if not requested:
                available = ", ".join(sorted(str(name) for name in companies.keys()))
                raise ValueError(
                    "Arquivo de credenciais Mercado Livre usa secao 'companies'. "
                    f"Informe o cliente para selecionar a conta. Clientes disponiveis: {available}."
                )

            resolved_name = cls._find_company_key(companies, requested)
            if resolved_name is None:
                available = ", ".join(sorted(str(name) for name in companies.keys()))
                raise ValueError(
                    f"Cliente '{company_name}' nao encontrado nas credenciais Mercado Livre. "
                    f"Clientes disponiveis: {available}."
                )

            company_payload = companies.get(resolved_name)
            if isinstance(company_payload, list):
                accounts = cls._extract_company_accounts(company_payload)
                company_payload = {"accounts": accounts} if accounts else {}
            if not isinstance(company_payload, dict):
                raise ValueError(
                    f"Formato invalido para o cliente '{resolved_name}' nas credenciais Mercado Livre."
                )

            accounts = cls._extract_company_accounts(company_payload)
            if not accounts:
                raise ValueError(
                    f"Formato invalido de credenciais do cliente '{resolved_name}' no Mercado Livre."
                )

            account_labels = cls._account_labels(accounts)
            selected_account_index = cls._resolve_account_index(
                accounts=accounts,
                requested_alias=account_alias,
                company_name=resolved_name,
                account_labels=account_labels,
            )

            selected_auth_payload = accounts[selected_account_index].get("auth")
            if not isinstance(selected_auth_payload, dict):
                raise ValueError(
                    f"Formato invalido de credenciais do cliente '{resolved_name}' no Mercado Livre."
                )

            return _ResolvedAuthPayload(
                auth_payload=selected_auth_payload,
                company_name=resolved_name,
                has_companies_section=True,
                selected_account_index=selected_account_index,
                account_labels=account_labels,
            )

        auth_payload = data.get("auth", data)
        if not isinstance(auth_payload, dict):
            raise ValueError("Formato invalido de credenciais Mercado Livre.")

        single_label = cls._account_label(auth_payload, 0)
        return _ResolvedAuthPayload(
            auth_payload=auth_payload,
            company_name=None,
            has_companies_section=False,
            selected_account_index=None,
            account_labels=[single_label] if single_label else [],
        )

    @classmethod
    def _resolve_account_index(
        cls,
        *,
        accounts: list[dict[str, Any]],
        requested_alias: str | None,
        company_name: str,
        account_labels: list[str],
    ) -> int:
        if not accounts:
            raise ValueError(
                f"Cliente '{company_name}' sem contas validas nas credenciais do Mercado Livre."
            )

        requested = str(requested_alias or "").strip()
        if not requested:
            return 0

        found = cls._find_account_index(accounts=accounts, requested=requested)
        if found is not None:
            return found

        available = ", ".join(account_labels)
        raise ValueError(
            f"Alias/filial '{requested}' nao encontrado para o cliente '{company_name}' no Mercado Livre. "
            f"Disponiveis: {available}."
        )

    @classmethod
    def _find_account_index(
        cls,
        *,
        accounts: list[dict[str, Any]],
        requested: str,
    ) -> int | None:
        target = requested.strip().casefold()
        if not target:
            return None

        for index, account in enumerate(accounts):
            auth_payload = account.get("auth")
            if not isinstance(auth_payload, dict):
                continue

            label = cls._account_label(auth_payload, index).casefold()
            if label == target:
                return index

            alias = (cls._extract_alias(auth_payload) or "").casefold()
            if alias and alias == target:
                return index

            user_id = str(auth_payload.get("user_id") or "").strip().casefold()
            if user_id and user_id == target:
                return index

        return None

    @classmethod
    def _find_account_index_by_user_id(
        cls,
        *,
        accounts: list[dict[str, Any]],
        requested_user_id: str,
    ) -> int | None:
        target = requested_user_id.strip().casefold()
        if not target:
            return None
        for index, account in enumerate(accounts):
            auth_payload = account.get("auth")
            if not isinstance(auth_payload, dict):
                continue
            user_id = str(auth_payload.get("user_id") or "").strip().casefold()
            if user_id and user_id == target:
                return index
        return None

    @classmethod
    def _account_labels(cls, accounts: list[dict[str, Any]]) -> list[str]:
        labels: list[str] = []
        for index, account in enumerate(accounts):
            auth_payload = account.get("auth")
            if not isinstance(auth_payload, dict):
                continue
            label = cls._account_label(auth_payload, index)
            if label:
                labels.append(label)
        return labels

    @classmethod
    def _account_label(cls, auth_payload: dict[str, Any], index: int) -> str:
        alias = cls._extract_alias(auth_payload)
        if alias:
            return alias
        user_id = cls._to_optional_text(auth_payload.get("user_id"))
        if user_id:
            return user_id
        return f"Conta {index + 1}"

    @classmethod
    def _extract_alias(cls, auth_payload: dict[str, Any]) -> str | None:
        return cls._to_optional_text(
            auth_payload.get("account_alias")
            or auth_payload.get("alias")
            or auth_payload.get("filial")
        )

    @classmethod
    def _extract_company_accounts(cls, company_payload: Any) -> list[dict[str, Any]]:
        if isinstance(company_payload, list):
            normalized_accounts: list[dict[str, Any]] = []
            for item in company_payload:
                if not isinstance(item, dict):
                    continue
                normalized_accounts.extend(cls._extract_company_accounts(item))
            return normalized_accounts

        if not isinstance(company_payload, dict):
            return []

        accounts_raw = company_payload.get("accounts")
        normalized_accounts: list[dict[str, Any]] = []
        if isinstance(accounts_raw, list):
            for item in accounts_raw:
                if not isinstance(item, dict):
                    continue
                auth_payload = cls._extract_account_auth_payload(item)
                if auth_payload is None:
                    continue
                normalized_item = dict(item)
                normalized_item["auth"] = dict(auth_payload)
                normalized_accounts.append(normalized_item)
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

        if cls._looks_like_auth(company_payload):
            return [{"auth": dict(company_payload)}]

        return []

    @classmethod
    def _extract_account_auth_payload(cls, item: dict[str, Any]) -> dict[str, Any] | None:
        auth_payload = item.get("auth")
        if isinstance(auth_payload, dict):
            return auth_payload
        if cls._looks_like_auth(item):
            return item
        return None

    @staticmethod
    def _looks_like_auth(payload: dict[str, Any]) -> bool:
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

    @staticmethod
    def _find_company_key(companies: dict[str, Any], requested: str) -> str | None:
        if requested in companies:
            return requested
        target = requested.strip().casefold()
        for company_key in companies.keys():
            normalized = str(company_key).strip().casefold()
            if normalized == target:
                return str(company_key)
        return None


def _load_json_object_with_duplicates(raw_text: str) -> dict[str, Any]:
    try:
        loaded = json.loads(raw_text, object_pairs_hook=_json_object_pairs_with_duplicates)
    except json.JSONDecodeError as error:
        raise ValueError(f"JSON invalido nas credenciais Mercado Livre: {error}") from error
    if not isinstance(loaded, dict):
        raise ValueError("Credenciais Mercado Livre invalidas: raiz deve ser objeto JSON.")
    return loaded


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
