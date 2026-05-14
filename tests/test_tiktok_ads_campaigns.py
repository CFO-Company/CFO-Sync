from __future__ import annotations

import unittest
from unittest.mock import patch

from cfo_sync.core.models import ResourceConfig
from cfo_sync.platforms.tiktok_ads.api import _build_request_payload
from cfo_sync.platforms.tiktok_ads.campanhas import fetch_campanhas
from cfo_sync.platforms.tiktok_ads.credentials import TikTokAdsAccount, TikTokAdsAuth


class TikTokAdsCampaignsTest(unittest.TestCase):
    def test_report_payload_defaults_to_advertiser_daily_spend(self) -> None:
        payload = _build_request_payload(
            endpoint="/open_api/v1.3/report/integrated/get/",
            advertiser_id="123",
            page=1,
            page_size=100,
            start_date="2026-05-13",
            end_date="2026-05-13",
        )

        self.assertEqual(payload["data_level"], "AUCTION_ADVERTISER")
        self.assertEqual(payload["dimensions"], ["stat_time_day"])
        self.assertEqual(payload["metrics"], ["spend"])

    def test_fetch_campanhas_returns_one_row_per_account_month(self) -> None:
        resource = ResourceConfig(
            name="campanhas",
            endpoint="/open_api/v1.3/report/integrated/get/",
            spreadsheet_url="https://docs.google.com/spreadsheets/d/sheet/edit#gid=1",
            spreadsheet_id="sheet",
            field_map={},
            client_tabs={},
        )
        account = TikTokAdsAccount(
            company_name="Cicatribem",
            account_name="Conta TikTok",
            advertiser_id="123",
            cost_center="MKT",
            business_center_name="BC Cicatribem",
        )
        raw_rows = [
            {
                "dimensions": {
                    "stat_time_day": "2026-05-13 00:00:00",
                },
                "metrics": {
                    "spend": "10.55",
                },
            },
            {
                "dimensions": {
                    "stat_time_day": "2026-05-14 00:00:00",
                },
                "metrics": {
                    "spend": "20",
                },
            },
            {
                "dimensions": {
                    "stat_time_day": "2026-06-01 00:00:00",
                },
                "metrics": {
                    "spend": "5",
                },
            },
        ]

        with patch(
            "cfo_sync.platforms.tiktok_ads.campanhas.fetch_paginated_rows",
            return_value=raw_rows,
        ):
            rows = fetch_campanhas(
                client="Cicatribem",
                resource=resource,
                accounts=[account],
                auth=TikTokAdsAuth(access_token="token"),
                start_date="2026-05-13",
                end_date="2026-05-13",
            )

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["mes_ano"], "05/2026")
        self.assertEqual(rows[0]["empresa"], "Cicatribem")
        self.assertEqual(rows[0]["business_center_name"], "BC Cicatribem")
        self.assertEqual(rows[0]["conta"], "Conta TikTok")
        self.assertEqual(rows[0]["tiktok_ads"], 30.55)
        self.assertEqual(rows[0]["centro_custo"], "MKT")
        self.assertEqual(rows[0]["tipo_ra"], "Não Classificado")
        self.assertNotIn("data", rows[0])
        self.assertNotIn("ad_id", rows[0])
        self.assertEqual(rows[1]["mes_ano"], "06/2026")
        self.assertEqual(rows[1]["tiktok_ads"], 5.0)


if __name__ == "__main__":
    unittest.main()
