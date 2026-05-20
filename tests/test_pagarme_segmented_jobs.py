import unittest

from cfo_sync.server.service import CfoSyncServerService


class _FakePagarmeBehavior:
    def sub_client_names(self, client: str) -> list[str]:
        return ["Le Moritz", "House of motors"]


class _PartiallyFailingPipeline:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def export_to_sheets(self, **kwargs: object) -> int:
        self.calls.append(kwargs)
        if kwargs.get("sub_clients") == ["Le Moritz"]:
            raise RuntimeError("403 Pagar.me")
        return 30


class PagarmeSegmentedJobsTest(unittest.TestCase):
    def test_segmented_pagarme_job_continues_after_alias_failure(self) -> None:
        service = CfoSyncServerService.__new__(CfoSyncServerService)
        pipeline = _PartiallyFailingPipeline()
        logs: list[str] = []

        result = service._run_segmented_pagarme_job(
            pipeline=pipeline,
            action="export",
            platform_key="pagarme",
            client="Unfair",
            start_date="2026-05-01",
            end_date="2026-05-20",
            resource_names=["financeiro"],
            accounts=["Le Moritz", "House of motors"],
            log=logs.append,
        )

        self.assertEqual(result["count"], 30)
        self.assertEqual(result["segments"], 2)
        self.assertEqual(result["partial_failures"], ["Le Moritz: 403 Pagar.me"])
        self.assertEqual(
            [call["sub_clients"] for call in pipeline.calls],
            [["Le Moritz"], ["House of motors"]],
        )
        self.assertTrue(any("concluido parcialmente" in item for item in logs))

    def test_pagarme_should_segment_multiple_accounts(self) -> None:
        service = CfoSyncServerService.__new__(CfoSyncServerService)
        service.platform_ui_registry = {"pagarme": _FakePagarmeBehavior()}

        should_segment = service._should_segment_pagarme_accounts(
            action="export",
            platform_key="pagarme",
            client="Unfair",
            sub_clients=None,
        )

        self.assertTrue(should_segment)


if __name__ == "__main__":
    unittest.main()
