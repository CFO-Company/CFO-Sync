import unittest

from cfo_sync.core.models import ResourceConfig
from cfo_sync.core.sheets_exporter import GoogleSheetsExporter, PeriodReplacePolicy


class GoogleSheetsExporterScopeFiltersTest(unittest.TestCase):
    def test_scope_filter_uses_mapped_row_value_when_alias_differs_from_origin(self) -> None:
        resource = ResourceConfig(
            name="financeiro",
            endpoint="/api/v1/financas",
            spreadsheet_url="",
            spreadsheet_id="",
            field_map={"origem": "Origem", "data": "dDtLanc"},
            client_tabs={},
        )
        policy = PeriodReplacePolicy(period_fields=("data",), scope_fields=("origem", "alias"))

        filters = GoogleSheetsExporter._resolve_policy_scope_filters(
            resource=resource,
            policy=policy,
            sub_clients=["BIOART BIOCOSMETICOS"],
            rows=[{"Origem": "Biodermo", "dDtLanc": "01/05/2026"}],
        )

        self.assertEqual(filters, {"Origem": {"biodermo"}})

    def test_extract_date_accepts_month_year_format(self) -> None:
        parsed = GoogleSheetsExporter._extract_date("05/2026")

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.isoformat(), "2026-05-01")

    def test_pagarme_has_period_replace_policy(self) -> None:
        resource = ResourceConfig(
            name="financeiro",
            endpoint="/charges",
            spreadsheet_url="",
            spreadsheet_id="",
            field_map={"data": "Data"},
            client_tabs={},
        )

        policy = GoogleSheetsExporter._resolve_period_replace_policy("pagarme", resource)

        self.assertIsNotNone(policy)
        self.assertEqual(policy.period_fields[0], "data")

    def test_pagarme_orders_include_fee_columns_without_field_map(self) -> None:
        resource = ResourceConfig(
            name="pedidos",
            endpoint="/orders",
            spreadsheet_url="",
            spreadsheet_id="",
            field_map={"data": "Data", "pedido_id": "Pedido"},
            client_tabs={},
        )
        raw_rows = [
            {
                "data": "2026-05-20",
                "pedido_id": "ord_1",
                "taxa_pagarme_reais": 1.23,
                "fee_reais": 1.23,
                "paid_amount_reais": 123.45,
                "net_amount_reais": 122.22,
                "refunded_amount_reais": 0.0,
                "charges_count": 2,
            }
        ]
        mapped_rows = [GoogleSheetsExporter._map_to_sheet_columns(resource, row) for row in raw_rows]

        ordered_columns = GoogleSheetsExporter._include_platform_columns(
            platform_key="pagarme",
            resource=resource,
            rows=raw_rows,
            mapped_rows=mapped_rows,
            ordered_columns=list(resource.field_map.values()),
        )

        self.assertIn("taxa_pagarme_reais", ordered_columns)
        self.assertEqual(mapped_rows[0]["taxa_pagarme_reais"], 1.23)
        self.assertEqual(mapped_rows[0]["net_amount_reais"], 122.22)


if __name__ == "__main__":
    unittest.main()
