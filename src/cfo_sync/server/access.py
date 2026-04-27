from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AccessTokenPolicy:
    name: str
    token: str
    allowed_platforms: tuple[str, ...]
    allowed_clients: dict[str, tuple[str, ...]]
    can_manage_secrets: bool = False

    def allows_platform(self, platform_key: str) -> bool:
        return _allows_value(self.allowed_platforms, platform_key)

    def allows_client(self, platform_key: str, client_name: str) -> bool:
        direct = self.allowed_clients.get(platform_key)
        wildcard = self.allowed_clients.get("*")
        if direct is None and wildcard is None:
            return False
        if direct is not None and _allows_value(direct, client_name):
            return True
        return wildcard is not None and _allows_value(wildcard, client_name)


def load_access_policies(path: Path) -> list[AccessTokenPolicy]:
    if not path.exists():
        raise FileNotFoundError(
            f"Arquivo de acesso nao encontrado: {path}. "
            "Crie o JSON de tokens antes de iniciar o servidor."
        )

    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, dict):
        raise ValueError("Arquivo de acesso invalido: raiz deve ser objeto JSON.")

    tokens = raw.get("tokens")
    if not isinstance(tokens, list) or not tokens:
        raise ValueError("Arquivo de acesso invalido: 'tokens' deve ser lista nao vazia.")

    policies: list[AccessTokenPolicy] = []
    for index, item in enumerate(tokens):
        if not isinstance(item, dict):
            raise ValueError(f"Token de indice {index} invalido: esperado objeto.")

        name = str(item.get("name") or f"token_{index + 1}").strip()
        token = str(item.get("token") or "").strip()
        if not token:
            raise ValueError(f"Token de indice {index} sem valor em 'token'.")

        raw_platforms = item.get("allowed_platforms", ["*"])
        if not isinstance(raw_platforms, list) or not raw_platforms:
            raise ValueError(f"Token '{name}' com 'allowed_platforms' invalido.")
        allowed_platforms = tuple(str(value).strip() for value in raw_platforms if str(value).strip())
        if not allowed_platforms:
            raise ValueError(f"Token '{name}' sem plataformas permitidas.")

        raw_clients = item.get("allowed_clients", {"*": ["*"]})
        if not isinstance(raw_clients, dict) or not raw_clients:
            raise ValueError(f"Token '{name}' com 'allowed_clients' invalido.")

        allowed_clients: dict[str, tuple[str, ...]] = {}
        for platform_key, values in raw_clients.items():
            if not isinstance(values, list) or not values:
                raise ValueError(
                    f"Token '{name}' com lista de clientes invalida para plataforma '{platform_key}'."
                )
            cleaned_values = tuple(str(value).strip() for value in values if str(value).strip())
            if not cleaned_values:
                raise ValueError(
                    f"Token '{name}' sem clientes validos para plataforma '{platform_key}'."
                )
            allowed_clients[str(platform_key).strip()] = cleaned_values

        policies.append(
            AccessTokenPolicy(
                name=name,
                token=token,
                allowed_platforms=allowed_platforms,
                allowed_clients=allowed_clients,
                can_manage_secrets=bool(item.get("can_manage_secrets", False)),
            )
        )
    return policies


def authenticate_token(token: str, policies: list[AccessTokenPolicy]) -> AccessTokenPolicy | None:
    cleaned = str(token or "").strip()
    if not cleaned:
        return None
    for policy in policies:
        if secrets.compare_digest(cleaned, policy.token):
            return policy
    return None


def _allows_value(allowed: tuple[str, ...], value: str) -> bool:
    if "*" in allowed:
        return True
    return value in allowed

