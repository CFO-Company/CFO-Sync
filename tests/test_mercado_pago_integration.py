from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cfo_sync.core.models import ResourceConfig
from cfo_sync.platforms.mercado_pago.credentials import (
    MercadoPagoAccount,
    MercadoPagoCredentialsStore,
)
from cfo_sync.platforms.mercado_pago.payments import fetch_payments


class MercadoPagoIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.account = MercadoPagoAccount(
            company_name="Unfair",
            account_name="Le Moritz",
            account_id="123",
            public_key="APP_USR_123",
            access_token="APP_USR_TOKEN",
            base_url="https://api.mercadopago.com",
        )
        self.resource_pagamentos = ResourceConfig(
            name="pagamentos",
            endpoint="/v1/payments/search",
            spreadsheet_url="",
            spreadsheet_id="",
            field_map={"data": "Data"},
            client_tabs={},
        )

    def test_credentials_store_parses_account_names(self) -> None:
        payload = {
            "base_url": "https://api.mercadopago.com",
            "companies": {
                "Unfair": [
                    {
                        "account_name": "Le Moritz",
                        "account_id": "123",
                        "public_key": "APP_USR_123",
                        "access_token": "APP_USR_TOKEN",
                    }
                ]
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "mercado_pago.json"
            path.write_text(json.dumps(payload), encoding="utf-8")

            store = MercadoPagoCredentialsStore.from_file(path)

        self.assertEqual(store.companies(), ["Unfair"])
        self.assertEqual(store.account_names_for_company("Unfair"), ["Le Moritz"])

    @patch("cfo_sync.platforms.mercado_pago.payments.list_payments")
    def test_fetch_payments_normalizes_analysis_fields(self, list_payments_mock) -> None:
        list_payments_mock.return_value = [
            {
                "id": 123456,
                "status": "approved",
                "status_detail": "accredited",
                "payment_method_id": "pix",
                "payment_type_id": "bank_transfer",
                "external_reference": "ord_1",
                "description": "Pedido 1",
                "date_created": "2026-05-02T09:10:11.000-03:00",
                "date_approved": "2026-05-02T09:12:00.000-03:00",
                "transaction_amount": 234.56,
                "transaction_amount_refunded": 10,
                "payer": {
                    "id": "payer_1",
                    "email": "cliente@example.com",
                },
            }
        ]

        rows = fetch_payments(
            client="Unfair",
            resource=self.resource_pagamentos,
            accounts=[self.account],
            start_date="2026-05-01",
            end_date="2026-05-31",
        )

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["data"], "2026-05-02")
        self.assertEqual(row["mes_ano"], "05/2026")
        self.assertEqual(row["id"], "123456")
        self.assertEqual(row["status"], "approved")
        self.assertEqual(row["payment_method_id"], "pix")
        self.assertEqual(row["transaction_amount"], 234.56)
        self.assertEqual(row["transaction_amount_refunded"], 10.0)
        self.assertEqual(row["payer_email"], "cliente@example.com")
        self.assertEqual(row["resource_source"], "payments")


if __name__ == "__main__":
    unittest.main()
