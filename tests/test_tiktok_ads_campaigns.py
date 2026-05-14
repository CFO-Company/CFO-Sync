from __future__ import annotations

import unittest
from unittest.mock import patch

from cfo_sync.core.models import ResourceConfig
from cfo_sync.platforms.tiktok_ads.api import _build_request_payload
from cfo_sync.platforms.tiktok_ads.campanhas import fetch_campanhas
from cfo_sync.platforms.tiktok_ads.credentials import TikTokAdsAccount, TikTokAdsAuth


class TikTokAdsCampaignsTest(unittest.TestCase):
    def test_report_payload_defaults_to_ad_daily_breakdown(self) -> None:
        payload = _build_request_payload(
            endpoint="/open_api/v1.3/report/integrated/get/",
            advertiser_id="123",
            page=1,
            page_size=100,
            start_date="2026-05-13",
            end_date="2026-05-13",
        )

        self.assertEqual(payload["data_level"], "AUCTION_AD")
        self.assertEqual(payload["dimensions"], ["ad_id", "stat_time_day"])
        self.assertIn("spend", payload["metrics"])
        self.assertIn("ad_name", payload["metrics"])
        self.assertIn("campaign_name", payload["metrics"])
        self.assertIn("adgroup_name", payload["metrics"])

    def test_fetch_campanhas_returns_one_row_per_ad_day(self) -> None:
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
                    "ad_id": "ad-1",
                    "stat_time_day": "2026-05-13 00:00:00",
                },
                "metrics": {
                    "campaign_name": "[A] Campanha",
                    "adgroup_name": "Grupo 1",
                    "ad_name": "Anuncio 1",
                    "spend": "10.55",
                    "impressions": "1000",
                    "clicks": "50",
                    "ctr": "5.00",
                    "cpc": "0.21",
                    "cpm": "10.55",
                    "conversion": "2",
                    "cost_per_conversion": "5.275",
                    "total_purchase_value": "100.00",
                },
            },
            {
                "dimensions": {
                    "ad_id": "ad-2",
                    "stat_time_day": "2026-05-13 00:00:00",
                },
                "metrics": {
                    "campaign_name": "[R] Campanha",
                    "adgroup_name": "Grupo 2",
                    "ad_name": "Anuncio 2",
                    "spend": "20",
                    "impressions": "2000",
                    "clicks": "80",
                    "ctr": "4.00",
                    "cpc": "0.25",
                    "cpm": "10.00",
                    "conversion": "1",
                    "cost_per_conversion": "20",
                    "total_purchase_value": "50",
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
        self.assertEqual(rows[0]["data"], "13/05/2026")
        self.assertEqual(rows[0]["mes_ano"], "05/2026")
        self.assertEqual(rows[0]["empresa"], "Cicatribem")
        self.assertEqual(rows[0]["business_center_name"], "BC Cicatribem")
        self.assertEqual(rows[0]["conta"], "Conta TikTok")
        self.assertEqual(rows[0]["campaign_name"], "[A] Campanha")
        self.assertEqual(rows[0]["adgroup_name"], "Grupo 1")
        self.assertEqual(rows[0]["ad_name"], "Anuncio 1")
        self.assertEqual(rows[0]["ad_id"], "ad-1")
        self.assertEqual(rows[0]["impressoes"], 1000)
        self.assertEqual(rows[0]["cliques"], 50)
        self.assertEqual(rows[0]["tiktok_ads"], 10.55)
        self.assertEqual(rows[0]["centro_custo"], "MKT")
        self.assertEqual(rows[0]["tipo_ra"], "Aquisição")
        self.assertEqual(rows[1]["tipo_ra"], "Retenção")


if __name__ == "__main__":
    unittest.main()
