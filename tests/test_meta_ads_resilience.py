import json
from io import BytesIO
import unittest
from urllib.error import HTTPError

from cfo_sync.core.models import ResourceConfig
from cfo_sync.core.sheets_exporter import GoogleSheetsExporter
from cfo_sync.platforms.meta_ads.api import _is_retryable_http_error
from cfo_sync.server.service import CfoSyncServerService


class _FakeBehavior:
    def sub_client_names(self, client: str) -> list[str]:
        return ["Conta 1", "Conta 2", "Conta 1"]


class _FakePipeline:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def export_to_sheets(self, **kwargs: object) -> int:
        self.calls.append(kwargs)
        return 10


class MetaAdsResilienceTest(unittest.TestCase):
    def test_meta_ads_segments_each_account_with_sub_clients_scope(self) -> None:
        service = CfoSyncServerService.__new__(CfoSyncServerService)
        pipeline = _FakePipeline()
        logs: list[str] = []

        result = service._run_segmented_meta_ads_job(
            pipeline=pipeline,
            action="export",
            platform_key="meta_ads",
            client="Cliente",
            start_date="2026-05-01",
            end_date="2026-05-20",
            resource_names=["contas"],
            accounts=["Conta 1", "Conta 2"],
            log=logs.append,
        )

        self.assertEqual(result["count"], 20)
        self.assertEqual(result["segments"], 2)
        self.assertEqual([call["sub_clients"] for call in pipeline.calls], [["Conta 1"], ["Conta 2"]])
        self.assertTrue(any("sub_clients" in item for item in logs))

    def test_meta_ads_should_segment_multiple_selected_accounts(self) -> None:
        service = CfoSyncServerService.__new__(CfoSyncServerService)
        service.platform_ui_registry = {"meta_ads": _FakeBehavior()}

        should_segment = service._should_segment_meta_ads_accounts(
            action="export",
            platform_key="meta_ads",
            client="Cliente",
            resource_names=["contas"],
            sub_clients=None,
        )

        self.assertTrue(should_segment)

    def test_meta_ads_retryable_403_code_4(self) -> None:
        body = json.dumps({"error": {"code": 4, "is_transient": True}})
        error = HTTPError(
            url="https://graph.facebook.com/v20.0/act_1/insights",
            code=403,
            msg="Forbidden",
            hdrs={},
            fp=BytesIO(b""),
        )

        try:
            self.assertTrue(_is_retryable_http_error(error=error, body=body))
        finally:
            error.close()

    def test_meta_ads_scope_filter_targets_only_selected_account_column(self) -> None:
        resource = ResourceConfig(
            name="contas",
            endpoint="/insights",
            spreadsheet_url="",
            spreadsheet_id="",
            field_map={"nome_ca": "Nome CA", "data": "Data"},
            client_tabs={},
        )
        policy = GoogleSheetsExporter._resolve_period_replace_policy("meta_ads", resource)

        self.assertIsNotNone(policy)
        filters = GoogleSheetsExporter._resolve_policy_scope_filters(
            resource=resource,
            policy=policy,
            sub_clients=["Conta 2"],
            rows=[{"Nome CA": "Conta 2", "Data": "20/05/2026"}],
        )

        header_index = {"Nome CA": 0, "Data": 1}
        self.assertEqual(filters, {"Nome CA": {"conta 2"}})
        self.assertFalse(
            GoogleSheetsExporter._row_matches_scope_filters(
                values=["Conta 1", "20/05/2026"],
                header_index=header_index,
                scope_filters=filters,
            )
        )
        self.assertTrue(
            GoogleSheetsExporter._row_matches_scope_filters(
                values=["Conta 2", "20/05/2026"],
                header_index=header_index,
                scope_filters=filters,
            )
        )


if __name__ == "__main__":
    unittest.main()
