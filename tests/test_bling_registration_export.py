from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

from cfo_sync.core.client_registration import ClientRegistrationManager
from cfo_sync.core.config_loader import load_app_config
from cfo_sync.core.pipeline import SyncPipeline


class FakeBlingConnector:
    def fetch(
        self,
        client,
        resource,
        start_date=None,
        end_date=None,
        sub_clients=None,
    ):
        return [
            {
                "id": "bling-test-row",
                "data": start_date or "2026-01-01",
                "cliente": client,
                "conta": (sub_clients or ["Conta teste"])[0],
            }
        ]


class FakeSheetsExporter:
    def __init__(self) -> None:
        self.calls = []

    def export(
        self,
        client,
        platform_key,
        resource,
        rows,
        start_date=None,
        end_date=None,
        sub_clients=None,
    ):
        self.calls.append(
            {
                "client": client,
                "platform_key": platform_key,
                "resource": resource.name,
                "rows": rows,
                "start_date": start_date,
                "end_date": end_date,
                "sub_clients": sub_clients,
            }
        )
        return len(rows)


class BlingRegistrationExportTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_root = Path.cwd() / "data" / "test-temp" / self._testMethodName
        shutil.rmtree(self.temp_root, ignore_errors=True)
        self.root = self.temp_root
        self.secrets_dir = self.root / "secrets"
        self.data_dir = self.root / "data"
        self.secrets_dir.mkdir(parents=True)
        self.data_dir.mkdir(parents=True)
        self.app_config_path = self.secrets_dir / "app_config.json"
        self.bling_credentials_path = self.secrets_dir / "bling_credentials.json"

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_root, ignore_errors=True)

    def test_registers_bling_client_and_exports_after_reload(self) -> None:
        self._write_credentials({})
        self._write_app_config(clients=[])

        registration_result = ClientRegistrationManager(self.app_config_path).register_client(
            self._registration_payload(
                mode="new_client",
                client_name="Cliente Bling Teste",
                account_name="Conta teste",
            )
        )

        self.assertEqual(registration_result["platform_key"], "bling")
        self.assertEqual(registration_result["client_name"], "Cliente Bling Teste")
        self.assertEqual(registration_result["updated_resources"], ["pedidos"])

        credentials_payload = self._read_credentials()
        self.assertEqual(credentials_payload["accounts"][0]["company_name"], "Cliente Bling Teste")
        self.assertEqual(credentials_payload["accounts"][0]["account_name"], "Conta teste")

        updated_config = load_app_config(self.app_config_path)
        self.assertEqual(updated_config.bling.oauth_app_file, "bling_oauth_app.json")
        bling_platform = next(platform for platform in updated_config.platforms if platform.key == "bling")
        self.assertIn("Cliente Bling Teste", bling_platform.clients)
        self.assertIn("Cliente Bling Teste", bling_platform.resources[0].client_tabs)

        with patch(
            "cfo_sync.core.pipeline.build_platform_registry",
            return_value={"bling": FakeBlingConnector()},
        ):
            pipeline = SyncPipeline(updated_config)
        fake_exporter = FakeSheetsExporter()
        pipeline.exporter = fake_exporter

        exported = pipeline.export_to_sheets(
            platform_key="bling",
            client="Cliente Bling Teste",
            resource_names=["pedidos"],
            start_date="2026-01-01",
            end_date="2026-01-31",
            sub_clients=["Conta teste"],
        )

        self.assertEqual(exported, 1)
        self.assertEqual(len(fake_exporter.calls), 1)
        self.assertEqual(fake_exporter.calls[0]["platform_key"], "bling")
        self.assertEqual(fake_exporter.calls[0]["resource"], "pedidos")
        self.assertEqual(fake_exporter.calls[0]["rows"][0]["id"], "bling-test-row")

    def test_new_client_duplicate_is_rejected_without_changing_credentials(self) -> None:
        self._write_credentials(
            {
                "accounts": [
                    self._account_payload(
                        company_name="Cliente Bling Teste",
                        account_name="Conta original",
                        access_token="original-access",
                    )
                ]
            }
        )
        self._write_app_config(clients=["Cliente Bling Teste"])

        before = self._read_credentials()
        with self.assertRaisesRegex(ValueError, "ja existe"):
            ClientRegistrationManager(self.app_config_path).register_client(
                self._registration_payload(
                    mode="new_client",
                    client_name="Cliente Bling Teste",
                    account_name="Conta nova",
                )
            )

        self.assertEqual(self._read_credentials(), before)

    def test_existing_client_adds_new_account_without_replacing_existing(self) -> None:
        self._write_credentials(
            {
                "accounts": [
                    self._account_payload(
                        company_name="Cliente Bling Teste",
                        account_name="Conta antiga",
                        access_token="old-access",
                    )
                ]
            }
        )
        self._write_app_config(clients=["Cliente Bling Teste"], gid="111111")

        ClientRegistrationManager(self.app_config_path).register_client(
            self._registration_payload(
                mode="existing_client",
                client_name="Cliente Bling Teste",
                account_name="Conta nova",
                access_token="new-access",
                gid="222222",
            )
        )

        accounts = self._read_credentials()["accounts"]
        self.assertEqual(len(accounts), 2)
        by_account = {account["account_name"]: account for account in accounts}
        self.assertEqual(by_account["Conta antiga"]["access_token"], "old-access")
        self.assertEqual(by_account["Conta nova"]["access_token"], "new-access")

        config_payload = json.loads(self.app_config_path.read_text(encoding="utf-8"))
        client_tab = config_payload["platforms"][0]["resources"][0]["client_tabs"]["Cliente Bling Teste"]
        self.assertEqual(client_tab["gid"], "222222")

    def test_existing_client_same_account_updates_without_duplicate(self) -> None:
        self._write_credentials(
            {
                "accounts": [
                    self._account_payload(
                        company_name="Cliente Bling Teste",
                        account_name="Conta teste",
                        access_token="old-access",
                    )
                ]
            }
        )
        self._write_app_config(clients=["Cliente Bling Teste"])

        ClientRegistrationManager(self.app_config_path).register_client(
            self._registration_payload(
                mode="existing_client",
                client_name="Cliente Bling Teste",
                account_name="Conta teste",
                access_token="updated-access",
            )
        )

        accounts = self._read_credentials()["accounts"]
        self.assertEqual(len(accounts), 1)
        self.assertEqual(accounts[0]["account_name"], "Conta teste")
        self.assertEqual(accounts[0]["access_token"], "updated-access")

    def _write_app_config(self, *, clients: list[str], gid: str = "123456") -> None:
        self.app_config_path.write_text(
            json.dumps(
                {
                    "database_path": "../data/test.db",
                    "credentials_dir": "secrets",
                    "google_sheets": {"credentials_file": "google.json"},
                    "yampi": {"credentials_file": "yampi.json"},
                    "meta_ads": {"credentials_file": "meta_ads.json"},
                    "bling": {
                        "credentials_file": "bling_credentials.json",
                        "oauth_app_file": "bling_oauth_app.json",
                    },
                    "platforms": [
                        {
                            "key": "bling",
                            "label": "Bling",
                            "clients": clients,
                            "resources": [
                                {
                                    "name": "pedidos",
                                    "endpoint": "pedidos/vendas",
                                    "spreadsheet_url": (
                                        "https://docs.google.com/spreadsheets/d/"
                                        "test-spreadsheet/edit"
                                    ),
                                    "field_map": {
                                        "id": "ID",
                                        "data": "Data",
                                        "cliente": "Cliente",
                                        "conta": "Conta",
                                    },
                                    "client_tabs": {
                                        client: {"tab_name": "", "gid": gid}
                                        for client in clients
                                    },
                                }
                            ],
                        }
                    ],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    def _write_credentials(self, payload: dict[str, object]) -> None:
        self.bling_credentials_path.write_text(
            json.dumps(payload, indent=2) + "\n",
            encoding="utf-8",
        )

    def _read_credentials(self) -> dict[str, object]:
        return json.loads(self.bling_credentials_path.read_text(encoding="utf-8"))

    def _registration_payload(
        self,
        *,
        mode: str,
        client_name: str,
        account_name: str,
        access_token: str = "access-token-test",
        gid: str = "123456",
    ) -> dict[str, object]:
        return {
            "registration_mode": mode,
            "platform_key": "bling",
            "client_name": client_name,
            "gid": gid,
            "credentials": {
                "account_name": account_name,
                "access_token": access_token,
                "refresh_token": "refresh-token-test",
                "expires_in": 21600,
                "access_token_expires_at": "2099-01-01T00:00:00Z",
            },
        }

    @staticmethod
    def _account_payload(
        *,
        company_name: str,
        account_name: str,
        access_token: str,
    ) -> dict[str, object]:
        return {
            "company_name": company_name,
            "account_name": account_name,
            "access_token": access_token,
            "refresh_token": "refresh-token-test",
            "token_type": "Bearer",
            "expires_in": 21600,
            "access_token_expires_at": "2099-01-01T00:00:00Z",
        }


if __name__ == "__main__":
    unittest.main()
