from __future__ import annotations

import threading
import time
import unittest

from cfo_sync.server.jobs import JobManager


class JobManagerSnapshotTest(unittest.TestCase):
    def test_snapshot_reports_queue_and_public_payload(self) -> None:
        started = threading.Event()
        release = threading.Event()

        def runner(payload, log):
            started.set()
            release.wait(timeout=5)
            return {"ok": True}

        manager = JobManager(runner=runner, worker_count=1)
        try:
            first = manager.enqueue(
                "admin",
                {
                    "_policy_name": "admin",
                    "_request_payload": {
                        "action": "collect",
                        "platform_key": "yampi",
                        "client": "Cliente A",
                        "secret": "nao deve aparecer",
                    },
                },
            )
            second = manager.enqueue(
                "admin",
                {
                    "_policy_name": "admin",
                    "_request_payload": {
                        "action": "export",
                        "platform_key": "omie",
                        "client": "Cliente B",
                    },
                },
            )

            self.assertTrue(started.wait(timeout=5))
            snapshot = manager.snapshot()

            self.assertEqual(snapshot["summary"]["workers"], 1)
            self.assertEqual(snapshot["summary"]["running"], 1)
            self.assertEqual(snapshot["summary"]["queued"], 1)
            self.assertEqual(snapshot["summary"]["queue_depth"], 1)

            jobs_by_id = {job["id"]: job for job in snapshot["jobs"]}
            self.assertEqual(jobs_by_id[first.id]["status"], "running")
            self.assertEqual(jobs_by_id[second.id]["status"], "queued")
            self.assertEqual(jobs_by_id[second.id]["queue_state"], "waiting")
            self.assertEqual(jobs_by_id[first.id]["payload"]["platform_key"], "yampi")
            self.assertNotIn("secret", jobs_by_id[first.id]["payload"])
        finally:
            release.set()
            deadline = time.monotonic() + 5
            while manager.get(first.id).status == "running" and time.monotonic() < deadline:
                time.sleep(0.05)
            manager.stop()


if __name__ == "__main__":
    unittest.main()
