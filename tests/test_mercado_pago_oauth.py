from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

from cfo_sync.core.client_registration import ClientRegistrationManager
from cfo_sync.core.link_generator import GeneratorLinkManager


class MercadoPagoOAuthTest(unittest.TestCase):
    def test_generator_creates_mercado_pago_authorization_link(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            secrets_dir = root / "secrets"
            secrets_dir.mkdir()
            config_path = root / "app_config.json"
            _write_config(config_path, clients=["Unfair"])
            (secrets_dir / "mercado_pago_credentials.json").write_text(
                json.dumps({"base_url": "https://api.mercadopago.com", "companies": {}}),
                encoding="utf-8",
            )
            (secrets_dir / "mercado_pago_oauth_app.json").write_text(
                json.dumps(
                    {
                        "client_id": "app123",
                        "client_secret": "secret",
                        "redirect_uri": "https://api.ecfo.com.br/v1/oauth/mercado_pago/callback",
                    }
                ),
                encoding="utf-8",
            )

            result = GeneratorLinkManager(config_path).create_link(
                {
                    "registration_mode": "existing_client",
                    "platform_key": "mercado_pago",
                    "client_name": "Unfair",
                    "gid": "123",
                    "credentials": {"account_alias": "Le Moritz"},
                },
                external_base_url="https://api.ecfo.com.br/",
            )

        authorization_url = str(result["authorization_url"])
        query = parse_qs(urlparse(authorization_url).query)
        self.assertTrue(authorization_url.startswith("https://auth.mercadopago.com/authorization?"))
        self.assertEqual(query["response_type"], ["code"])
        self.assertEqual(query["client_id"], ["app123"])
        self.assertEqual(query["platform_id"], ["mp"])
        self.assertEqual(query["redirect_uri"], ["https://api.ecfo.com.br/v1/oauth/mercado_pago/callback"])
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertIn("code_challenge", query)
        self.assertIn("state", query)

    def test_client_registration_upserts_mercado_pago_oauth_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            secrets_dir = root / "secrets"
            secrets_dir.mkdir()
            config_path = root / "app_config.json"
            _write_config(config_path, clients=["Unfair"])
            credentials_path = secrets_dir / "mercado_pago_credentials.json"
            credentials_path.write_text(
                json.dumps(
                    {
                        "base_url": "https://api.mercadopago.com",
                        "auth": {"client_id": "app123", "client_secret": "secret"},
                        "companies": {},
                    }
                ),
                encoding="utf-8",
            )

            ClientRegistrationManager(config_path).register_client(
                {
                    "registration_mode": "existing_client",
                    "platform_key": "mercado_pago",
                    "client_name": "Unfair",
                    "gid": "123",
                    "credentials": {
                        "client_id": "app123",
                        "client_secret": "secret",
                        "account_name": "Le Moritz",
                        "account_id": "2971903313",
                        "access_token": "APP_USR_ACCESS",
                        "refresh_token": "TG_REFRESH",
                        "expires_in": 21600,
                        "access_token_expires_at": "2026-05-19T20:00:00Z",
                    },
                }
            )

            payload = json.loads(credentials_path.read_text(encoding="utf-8"))

        account = payload["companies"]["Unfair"][0]
        self.assertEqual(account["account_name"], "Le Moritz")
        self.assertEqual(account["account_id"], "2971903313")
        self.assertEqual(account["refresh_token"], "TG_REFRESH")

    @patch("cfo_sync.core.link_generator.exchange_mercado_pago_code_for_tokens")
    def test_callback_consumes_state_and_adds_tokens(self, exchange_mock) -> None:
        exchange_mock.return_value = {
            "access_token": "APP_USR_ACCESS",
            "refresh_token": "TG_REFRESH",
            "user_id": 2971903313,
            "token_type": "bearer",
            "expires_in": 21600,
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            secrets_dir = root / "secrets"
            secrets_dir.mkdir()
            config_path = root / "app_config.json"
            _write_config(config_path, clients=["Unfair"])
            (secrets_dir / "mercado_pago_credentials.json").write_text(
                json.dumps({"base_url": "https://api.mercadopago.com", "companies": {}}),
                encoding="utf-8",
            )
            (secrets_dir / "mercado_pago_oauth_app.json").write_text(
                json.dumps({"client_id": "app123", "client_secret": "secret"}),
                encoding="utf-8",
            )
            manager = GeneratorLinkManager(config_path)
            result = manager.create_link(
                {
                    "registration_mode": "existing_client",
                    "platform_key": "mercado_pago",
                    "client_name": "Unfair",
                    "gid": "123",
                    "credentials": {"account_alias": "Le Moritz"},
                },
                external_base_url="https://api.ecfo.com.br",
            )
            state = parse_qs(urlparse(str(result["authorization_url"])).query)["state"][0]

            registration_payload = manager.consume_mercado_pago_callback(
                code="CODE123",
                state=state,
            )

        credentials = registration_payload["credentials"]
        self.assertEqual(credentials["account_name"], "Le Moritz")
        self.assertEqual(credentials["access_token"], "APP_USR_ACCESS")
        self.assertEqual(credentials["refresh_token"], "TG_REFRESH")
        self.assertEqual(credentials["account_id"], "2971903313")
        self.assertIn("code_verifier", exchange_mock.call_args.kwargs)


def _write_config(config_path: Path, *, clients: list[str]) -> None:
    config_path.write_text(
        json.dumps(
            {
                "database_path": "data/cfo_sync.db",
                "credentials_dir": "secrets",
                "google_sheets": {"credentials_file": "google_service_account.json"},
                "yampi": {"credentials_file": "yampi_credentials.json"},
                "meta_ads": {"credentials_file": "meta_ads_credentials.json"},
                "google_ads": {"credentials_file": "google_ads_credentials.json"},
                "tiktok_ads": {"credentials_file": "tiktok_ads_credentials.json"},
                "tiktok_shop": {"credentials_file": "tiktok_shop_credentials.json"},
                "platforms": [
                    {
                        "key": "mercado_pago",
                        "label": "Mercado Pago",
                        "clients": clients,
                        "resources": [
                            {
                                "name": "pagamentos",
                                "endpoint": "/v1/payments/search",
                                "spreadsheet_id": "sheet123",
                                "field_map": {"data": "Data"},
                                "client_tabs": {},
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    unittest.main()
