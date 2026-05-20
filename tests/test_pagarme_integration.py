from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cfo_sync.core.models import ResourceConfig
from cfo_sync.platforms.pagarme.credentials import PagarmeAccount, PagarmeCredentialsStore
from cfo_sync.platforms.pagarme.financeiro import fetch_financeiro
from cfo_sync.platforms.pagarme.orders import fetch_orders


class PagarmeIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.account = PagarmeAccount(
            company_name="Unfair",
            account_name="Le Moritz",
            account_id="acc_123",
            public_key="pk_123",
            secret_key="sk_123",
            base_url="https://api.pagar.me/core/v5",
        )
        self.resource_pedidos = ResourceConfig(
            name="pedidos",
            endpoint="/orders",
            spreadsheet_url="",
            spreadsheet_id="",
            field_map={"data": "Data"},
            client_tabs={},
        )
        self.resource_financeiro = ResourceConfig(
            name="financeiro",
            endpoint="/charges",
            spreadsheet_url="",
            spreadsheet_id="",
            field_map={"data": "Data"},
            client_tabs={},
        )

    def test_credentials_store_parses_account_names(self) -> None:
        payload = {
            "base_url": "https://api.pagar.me/core/v5",
            "companies": {
                "Unfair": [
                    {
                        "account_name": "Le Moritz",
                        "account_id": "acc_123",
                        "public_key": "pk_123",
                        "secret_key": "sk_123",
                    }
                ]
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "pagarme.json"
            path.write_text(json.dumps(payload), encoding="utf-8")

            store = PagarmeCredentialsStore.from_file(path)

        self.assertEqual(store.companies(), ["Unfair"])
        self.assertEqual(store.account_names_for_company("Unfair"), ["Le Moritz"])

    @patch("cfo_sync.platforms.pagarme.orders.list_payables")
    @patch("cfo_sync.platforms.pagarme.orders.list_charges")
    @patch("cfo_sync.platforms.pagarme.orders.list_orders")
    def test_fetch_orders_normalizes_analysis_fields(
        self,
        list_orders_mock,
        list_charges_mock,
        list_payables_mock,
    ) -> None:
        list_orders_mock.return_value = [
            {
                "id": "ord_1",
                "code": "ABC",
                "status": "paid",
                "created_at": "2026-05-01T10:30:00Z",
                "updated_at": "2026-05-01T11:00:00Z",
                "customer": {
                    "id": "cus_1",
                    "name": "Maria",
                    "email": "maria@example.com",
                },
                "amount": 12345,
                "items": [{"id": "item_1"}],
                "payments": [{"id": "pay_1"}],
            }
        ]
        list_charges_mock.return_value = [
            {
                "id": "chg_1",
                "order_id": "ord_1",
                "paid_amount": 10000,
                "refunded_amount": 0,
            },
            {
                "id": "chg_2",
                "order": {"id": "ord_1"},
                "paid_amount": 2345,
                "refunded_amount": 0,
            },
        ]
        list_payables_mock.side_effect = [
            [
                {
                    "id": "payable_1",
                    "fee": 100,
                    "anticipation_fee": 10,
                    "fraud_coverage_fee": 5,
                }
            ],
            [
                {
                    "id": "payable_2",
                    "fee": 23,
                    "anticipation_fee": 0,
                    "fraud_coverage_fee": 2,
                }
            ],
        ]

        rows = fetch_orders(
            client="Unfair",
            resource=self.resource_pedidos,
            accounts=[self.account],
            start_date="2026-05-01",
            end_date="2026-05-31",
        )

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["data"], "2026-05-01")
        self.assertEqual(row["mes_ano"], "05/2026")
        self.assertEqual(row["customer_name"], "Maria")
        self.assertEqual(row["items_count"], 1)
        self.assertEqual(row["payments_count"], 1)
        self.assertEqual(row["resource_source"], "orders")
        self.assertEqual(row["customer.name"], "Maria")
        self.assertEqual(row["fee_centavos"], 123)
        self.assertEqual(row["fee_reais"], 1.23)
        self.assertEqual(row["mdr_fee_reais"], 1.23)
        self.assertEqual(row["anticipation_fee_reais"], 0.1)
        self.assertEqual(row["fraud_coverage_fee_reais"], 0.07)
        self.assertEqual(row["taxa_pagarme_reais"], 1.4)
        self.assertEqual(row["paid_amount_reais"], 123.45)
        self.assertEqual(row["net_amount_reais"], 122.05)
        self.assertEqual(row["charges_count"], 2)

    @patch("cfo_sync.platforms.pagarme.financeiro.list_charges")
    def test_fetch_financeiro_normalizes_financial_fields(self, list_charges_mock) -> None:
        list_charges_mock.return_value = [
            {
                "id": "chg_1",
                "order_id": "ord_1",
                "status": "captured",
                "payment_method": "credit_card",
                "created_at": "2026-05-02T09:10:11Z",
                "paid_at": "2026-05-02T09:15:00Z",
                "due_at": "2026-05-10",
                "amount": 23456,
                "paid_amount": 20000,
                "refunded_amount": 0,
                "fee": 123,
                "net_amount": 23333,
                "customer": {
                    "id": "cus_2",
                    "name": "Joao",
                    "email": "joao@example.com",
                },
            }
        ]

        rows = fetch_financeiro(
            client="Unfair",
            resource=self.resource_financeiro,
            accounts=[self.account],
            start_date="2026-05-01",
            end_date="2026-05-31",
        )

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["data"], "2026-05-02")
        self.assertEqual(row["mes_ano"], "05/2026")
        self.assertEqual(row["payment_method"], "credit_card")
        self.assertEqual(row["amount_centavos"], 23456)
        self.assertEqual(row["amount_reais"], 234.56)
        self.assertEqual(row["paid_amount_reais"], 200.0)
        self.assertEqual(row["fee_reais"], 1.23)
        self.assertEqual(row["net_amount_reais"], 233.33)
        self.assertEqual(row["customer_name"], "Joao")
        self.assertEqual(row["resource_source"], "charges")


if __name__ == "__main__":
    unittest.main()
