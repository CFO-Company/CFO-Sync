from __future__ import annotations

import queue
import threading
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable


JobRunner = Callable[[dict[str, object], Callable[[str], None]], dict[str, object]]


@dataclass
class JobState:
    id: str
    requested_by: str
    payload: dict[str, object]
    status: str = "queued"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    finished_at: datetime | None = None
    result: dict[str, object] | None = None
    error: str | None = None
    logs: list[str] = field(default_factory=list)

    def append_log(self, message: str) -> None:
        timestamp = datetime.now(timezone.utc).isoformat()
        self.logs.append(f"[{timestamp}] {message}")


class JobManager:
    def __init__(self, runner: JobRunner, worker_count: int = 2) -> None:
        self._runner = runner
        self._queue: queue.Queue[str] = queue.Queue()
        self._jobs: dict[str, JobState] = {}
        self._lock = threading.Lock()
        self._workers: list[threading.Thread] = []
        self._stopping = threading.Event()

        for index in range(max(1, worker_count)):
            worker = threading.Thread(
                target=self._worker_loop,
                name=f"cfo-sync-job-worker-{index + 1}",
                daemon=True,
            )
            worker.start()
            self._workers.append(worker)

    def enqueue(self, requested_by: str, payload: dict[str, object]) -> JobState:
        job = JobState(
            id=uuid.uuid4().hex,
            requested_by=requested_by,
            payload=payload,
        )
        job.append_log("Job enfileirado.")
        with self._lock:
            self._jobs[job.id] = job
        self._queue.put(job.id)
        return job

    def get(self, job_id: str) -> JobState | None:
        with self._lock:
            return self._jobs.get(job_id)

    def stop(self) -> None:
        self._stopping.set()
        for _ in self._workers:
            self._queue.put("")
        for worker in self._workers:
            worker.join(timeout=2.0)

    def _worker_loop(self) -> None:
        while not self._stopping.is_set():
            job_id = self._queue.get()
            try:
                if not job_id:
                    continue
                self._run_job(job_id)
            finally:
                self._queue.task_done()

    def _run_job(self, job_id: str) -> None:
        job = self.get(job_id)
        if job is None:
            return

        with self._lock:
            job.status = "running"
            job.started_at = datetime.now(timezone.utc)
        job.append_log("Job iniciado.")

        try:
            result = self._runner(job.payload, job.append_log)
            with self._lock:
                job.status = "completed"
                job.result = result
                job.finished_at = datetime.now(timezone.utc)
            job.append_log("Job concluido com sucesso.")
        except Exception as error:  # noqa: BLE001
            trace = traceback.format_exc()
            with self._lock:
                job.status = "failed"
                job.error = str(error)
                job.finished_at = datetime.now(timezone.utc)
            job.append_log(f"Falha: {error}")
            job.append_log(trace)

