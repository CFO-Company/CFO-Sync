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


if __name__ == "__main__":
    unittest.main()
