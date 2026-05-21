from __future__ import annotations

import base64
import json
import unittest
from unittest.mock import patch

from cfo_sync.platforms.pagarme.api import list_orders, list_payables, normalize_period
from cfo_sync.platforms.pagarme.credentials import PagarmeAccount


class PagarmeAPITest(unittest.TestCase):
    def setUp(self) -> None:
        self.account = PagarmeAccount(
            company_name="Unfair",
            account_name="Le Moritz",
            account_id="acc_123",
            public_key="pk_123",
            secret_key="sk_123",
            base_url="https://api.pagar.me/core/v5",
        )

    @patch("cfo_sync.platforms.pagarme.api.urlopen")
    def test_list_orders_paginates_and_sends_basic_auth(self, urlopen_mock) -> None:
        first_response = _JsonResponse(
            {
                "data": [{"id": "ord_1"}],
                "total_pages": 2,
            }
        )
        second_response = _JsonResponse(
            {
                "data": [{"id": "ord_2"}],
                "total_pages": 2,
            }
        )
        urlopen_mock.side_effect = [first_response, second_response]

        rows = list_orders(
            account=self.account,
            start_date="2026-05-01",
            end_date="2026-05-19",
        )

        self.assertEqual(rows, [{"id": "ord_1"}, {"id": "ord_2"}])
        self.assertEqual(urlopen_mock.call_count, 2)

        first_request = urlopen_mock.call_args_list[0].args[0]
        second_request = urlopen_mock.call_args_list[1].args[0]
        expected_auth = "Basic " + base64.b64encode(b"sk_123:").decode("ascii")

        self.assertIn("/orders?created_since=2026-05-01T00%3A00%3A00Z", first_request.full_url)
        self.assertIn("created_until=2026-05-19T23%3A59%3A59Z", first_request.full_url)
        self.assertIn("page=1", first_request.full_url)
        self.assertIn("size=100", first_request.full_url)
        self.assertIn("page=2", second_request.full_url)
        self.assertEqual(first_request.headers["Authorization"], expected_auth)
        self.assertEqual(first_request.headers["Accept"], "application/json")

    def test_normalize_period_includes_full_end_date(self) -> None:
        since, until = normalize_period("2026-05-01", "2026-05-19")

        self.assertEqual(since, "2026-05-01T00:00:00Z")
        self.assertEqual(until, "2026-05-19T23:59:59Z")

    def test_normalize_period_rejects_invalid_date_instead_of_using_today(self) -> None:
        with self.assertRaisesRegex(ValueError, "Data invalida"):
            normalize_period("01/04/2026", "31/04/2026")

    def test_normalize_period_accepts_brazilian_date_format(self) -> None:
        since, until = normalize_period("01/04/2026", "30/04/2026")

        self.assertEqual(since, "2026-04-01T00:00:00Z")
        self.assertEqual(until, "2026-04-30T23:59:59Z")

    def test_normalize_period_accepts_already_expanded_iso_datetime(self) -> None:
        since, until = normalize_period("2026-04-01T00:00:00Z", "2026-04-30T23:59:59Z")

        self.assertEqual(since, "2026-04-01T00:00:00Z")
        self.assertEqual(until, "2026-04-30T23:59:59Z")

    @patch("cfo_sync.platforms.pagarme.api.urlopen")
    def test_list_payables_filters_by_charge_id(self, urlopen_mock) -> None:
        urlopen_mock.return_value = _JsonResponse(
            {
                "data": [
                    {
                        "id": "payable_1",
                        "charge_id": "chg_1",
                        "fee": 123,
                    }
                ]
            }
        )

        rows = list_payables(account=self.account, charge_id="chg_1")

        self.assertEqual(rows[0]["fee"], 123)
        request = urlopen_mock.call_args.args[0]
        self.assertIn("/payables?", request.full_url)
        self.assertIn("charge_id=chg_1", request.full_url)


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
