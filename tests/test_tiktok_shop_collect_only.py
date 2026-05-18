from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from cfo_sync.core.client_registration import ClientRegistrationManager
from cfo_sync.core.config_loader import load_app_config
from cfo_sync.core.link_generator import GeneratorLinkManager
from cfo_sync.platforms.tiktok_shop.api import _build_request_body


class TikTokShopCollectOnlyConfigTest(unittest.TestCase):
    def test_loads_resource_without_spreadsheet_for_collect_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "app_config.json"
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
                                "key": "tiktok_shop",
                                "label": "TikTok Shop",
                                "clients": ["Cliente A"],
                                "resources": [
                                    {
                                        "name": "pedidos",
                                        "endpoint": "POST /order/202309/orders/search",
                                        "field_map": {"id": "Pedido"},
                                    }
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            config = load_app_config(config_path)

        platform = next(item for item in config.platforms if item.key == "tiktok_shop")
        resource = platform.resources[0]
        self.assertEqual(resource.name, "pedidos")
        self.assertEqual(resource.spreadsheet_url, "")
        self.assertEqual(resource.spreadsheet_id, "")
        self.assertEqual(resource.client_tabs, {})

    def test_order_search_uses_current_period_filter_names(self) -> None:
        body = _build_request_body(
            method="POST",
            path="/order/202309/orders/search",
            start_date="2026-05-01",
            end_date="2026-05-18",
            page=1,
            page_size=100,
            next_page_token="",
            include_period=True,
        )

        self.assertIn("create_time_ge", body)
        self.assertIn("create_time_lt", body)
        self.assertNotIn("create_time_from", body)
        self.assertNotIn("create_time_to", body)

    def test_client_registration_accepts_tiktok_shop_without_gid(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            secrets_dir = root / "secrets"
            secrets_dir.mkdir()
            config_path = root / "app_config.json"
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
                                "key": "tiktok_shop",
                                "label": "TikTok Shop",
                                "clients": [],
                                "resources": [
                                    {
                                        "name": "pedidos",
                                        "endpoint": "POST /order/202309/orders/search",
                                        "field_map": {"id": "Pedido"},
                                        "client_tabs": {},
                                    }
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (secrets_dir / "tiktok_shop_credentials.json").write_text(
                json.dumps({"auth": {"app_key": "app", "app_secret": "secret"}, "accounts": []}),
                encoding="utf-8",
            )

            result = ClientRegistrationManager(config_path).register_client(
                {
                    "registration_mode": "new_client",
                    "platform_key": "tiktok_shop",
                    "client_name": "Cliente A",
                    "credentials": {
                        "account_name": "Loja A",
                        "shop_cipher": "cipher",
                        "access_token": "token",
                        "refresh_token": "refresh",
                    },
                }
            )

            credentials = json.loads(
                (secrets_dir / "tiktok_shop_credentials.json").read_text(encoding="utf-8")
            )
            updated_config = json.loads(config_path.read_text(encoding="utf-8"))

        self.assertEqual(result["client_name"], "Cliente A")
        self.assertEqual(updated_config["platforms"][0]["clients"], ["Cliente A"])
        self.assertEqual(updated_config["platforms"][0]["resources"][0]["client_tabs"], {})
        self.assertEqual(credentials["accounts"][0]["refresh_token"], "refresh")

    def test_generator_creates_tiktok_shop_authorization_link(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            secrets_dir = root / "secrets"
            secrets_dir.mkdir()
            config_path = root / "app_config.json"
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
                                "key": "tiktok_shop",
                                "label": "TikTok Shop",
                                "clients": ["Cliente A"],
                                "resources": [],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (secrets_dir / "tiktok_shop_credentials.json").write_text(
                json.dumps({"auth": {"app_key": "app123", "app_secret": "secret"}, "accounts": []}),
                encoding="utf-8",
            )

            result = GeneratorLinkManager(config_path).create_link(
                {
                    "registration_mode": "existing_client",
                    "platform_key": "tiktok_shop",
                    "client_name": "Cliente A",
                    "credentials": {"account_alias": "Loja A"},
                },
                external_base_url="https://api.ecfo.com.br/",
            )

        authorization_url = str(result["authorization_url"])
        self.assertIn("https://auth.tiktok-shops.com/oauth/authorize?", authorization_url)
        self.assertIn("app_key=app123", authorization_url)
        self.assertIn("response_type=code", authorization_url)
        self.assertIn("redirect_uri=https%3A%2F%2Fapi.ecfo.com.br%2Fv1%2Foauth%2Ftiktok%2Fcallback", authorization_url)


if __name__ == "__main__":
    unittest.main()
