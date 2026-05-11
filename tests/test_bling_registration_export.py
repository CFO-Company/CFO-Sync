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
    def test_registers_bling_client_and_exports_after_reload(self) -> None:
        temp_root = Path.cwd() / "data" / "test-temp" / "bling-registration-export"
        shutil.rmtree(temp_root, ignore_errors=True)
        try:
            root = temp_root
            secrets_dir = root / "secrets"
            data_dir = root / "data"
            secrets_dir.mkdir(parents=True)
            data_dir.mkdir(parents=True)

            app_config_path = secrets_dir / "app_config.json"
            bling_credentials_path = secrets_dir / "bling_credentials.json"
            bling_credentials_path.write_text("{}\n", encoding="utf-8")
            app_config_path.write_text(
                json.dumps(
                    {
                        "database_path": "../data/test.db",
                        "credentials_dir": "secrets",
                        "google_sheets": {"credentials_file": "google.json"},
                        "yampi": {"credentials_file": "yampi.json"},
                        "meta_ads": {"credentials_file": "meta_ads.json"},
                        "platforms": [
                            {
                                "key": "bling",
                                "label": "Bling",
                                "clients": [],
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
                                        "client_tabs": {},
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

            registration_result = ClientRegistrationManager(app_config_path).register_client(
                {
                    "registration_mode": "new_client",
                    "platform_key": "bling",
                    "client_name": "Cliente Bling Teste",
                    "gid": "123456",
                    "credentials": {
                        "account_name": "Conta teste",
                        "access_token": "access-token-test",
                        "refresh_token": "refresh-token-test",
                        "expires_in": 21600,
                        "access_token_expires_at": "2099-01-01T00:00:00Z",
                    },
                }
            )

            self.assertEqual(registration_result["platform_key"], "bling")
            self.assertEqual(registration_result["client_name"], "Cliente Bling Teste")
            self.assertEqual(registration_result["updated_resources"], ["pedidos"])

            credentials_payload = json.loads(bling_credentials_path.read_text(encoding="utf-8"))
            self.assertEqual(credentials_payload["accounts"][0]["company_name"], "Cliente Bling Teste")
            self.assertEqual(credentials_payload["accounts"][0]["account_name"], "Conta teste")

            updated_config = load_app_config(app_config_path)
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
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
