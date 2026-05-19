from __future__ import annotations

import json
import unittest
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

from cfo_sync.platforms.mercado_pago.api import list_payments
from cfo_sync.platforms.mercado_pago.credentials import MercadoPagoAccount


class MercadoPagoAPITest(unittest.TestCase):
    def setUp(self) -> None:
        self.account = MercadoPagoAccount(
            company_name="Unfair",
            account_name="Le Moritz",
            account_id="123",
            public_key="APP_USR_123",
            access_token="APP_USR_TOKEN",
            base_url="https://api.mercadopago.com",
        )

    @patch("cfo_sync.platforms.mercado_pago.api.urlopen")
    def test_list_payments_paginates_and_sends_bearer_auth(self, urlopen_mock) -> None:
        urlopen_mock.side_effect = [
            _JsonResponse(
                {
                    "results": [{"id": 1}],
                    "paging": {"total": 2, "offset": 0, "limit": 1},
                }
            ),
            _JsonResponse(
                {
                    "results": [{"id": 2}],
                    "paging": {"total": 2, "offset": 1, "limit": 1},
                }
            ),
        ]

        rows = list_payments(
            account=self.account,
            start_date="2026-05-01",
            end_date="2026-05-19",
        )

        self.assertEqual(rows, [{"id": 1}, {"id": 2}])
        self.assertEqual(urlopen_mock.call_count, 2)

        first_request = urlopen_mock.call_args_list[0].args[0]
        second_request = urlopen_mock.call_args_list[1].args[0]
        first_query = parse_qs(urlparse(first_request.full_url).query)
        second_query = parse_qs(urlparse(second_request.full_url).query)

        self.assertEqual(first_request.headers["Authorization"], "Bearer APP_USR_TOKEN")
        self.assertEqual(first_request.headers["Accept"], "application/json")
        self.assertEqual(first_query["range"], ["date_created"])
        self.assertEqual(first_query["begin_date"], ["2026-05-01T00:00:00.000-03:00"])
        self.assertEqual(first_query["end_date"], ["2026-05-19T23:59:59.000-03:00"])
        self.assertEqual(first_query["offset"], ["0"])
        self.assertEqual(first_query["limit"], ["100"])
        self.assertEqual(second_query["offset"], ["100"])


class _JsonResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def __enter__(self) -> "_JsonResponse":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


if __name__ == "__main__":
    unittest.main()
