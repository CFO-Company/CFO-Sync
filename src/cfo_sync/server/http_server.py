from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from cfo_sync.server.access import AccessTokenPolicy, authenticate_token, load_access_policies
from cfo_sync.server.jobs import JobManager
from cfo_sync.server.service import CfoSyncServerService, serialize_job


class CfoSyncHttpServer:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        app_config_path: Path,
        access_config_path: Path,
        worker_count: int = 2,
    ) -> None:
        self.host = host
        self.port = port
        self.service = CfoSyncServerService(app_config_path)
        self.access_policies = load_access_policies(access_config_path)
        self.policy_by_name = {policy.name: policy for policy in self.access_policies}

        def runner(payload: dict[str, object], log) -> dict[str, object]:
            policy_name = str(payload.get("_policy_name") or "").strip()
            request_payload = payload.get("_request_payload")
            if not isinstance(request_payload, dict):
                raise ValueError("Payload interno do job invalido.")

            policy = self.policy_by_name.get(policy_name)
            if policy is None:
                raise PermissionError("Token do job nao encontrado.")
            return self.service.run_job(request_payload, policy=policy, log=log)

        self.jobs = JobManager(runner=runner, worker_count=worker_count)

        handler = self._build_handler()
        self.httpd = ThreadingHTTPServer((host, port), handler)

    def serve_forever(self) -> None:
        self.httpd.serve_forever()

    def shutdown(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.jobs.stop()

    def _build_handler(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                path = parsed.path.rstrip("/") or "/"

                if path == "/v1/health":
                    self._write_json(HTTPStatus.OK, server.service.health_payload())
                    return

                policy = self._require_auth()
                if policy is None:
                    return

                if path == "/v1/catalog":
                    payload = server.service.build_catalog(policy)
                    self._write_json(HTTPStatus.OK, payload)
                    return

                if path.startswith("/v1/jobs/") and path.endswith("/logs"):
                    job_id = path.split("/")[3]
                    job = server.jobs.get(job_id)
                    if job is None or job.requested_by != policy.name:
                        self._write_json(HTTPStatus.NOT_FOUND, {"error": "Job nao encontrado."})
                        return
                    self._write_json(HTTPStatus.OK, {"logs": job.logs})
                    return

                if path.startswith("/v1/jobs/"):
                    job_id = path.split("/")[3]
                    job = server.jobs.get(job_id)
                    if job is None or job.requested_by != policy.name:
                        self._write_json(HTTPStatus.NOT_FOUND, {"error": "Job nao encontrado."})
                        return
                    self._write_json(HTTPStatus.OK, serialize_job(job))
                    return

                self._write_json(HTTPStatus.NOT_FOUND, {"error": "Rota nao encontrada."})

            def do_POST(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                path = parsed.path.rstrip("/") or "/"

                policy = self._require_auth()
                if policy is None:
                    return

                if path == "/v1/jobs":
                    payload = self._read_json_body()
                    if payload is None:
                        return

                    job = server.jobs.enqueue(
                        requested_by=policy.name,
                        payload={
                            "_policy_name": policy.name,
                            "_request_payload": payload,
                        },
                    )
                    self._write_json(
                        HTTPStatus.ACCEPTED,
                        {
                            "job_id": job.id,
                            "status": job.status,
                        },
                    )
                    return

                if path == "/v1/clients":
                    payload = self._read_json_body()
                    if payload is None:
                        return
                    try:
                        result = server.service.register_client(payload, policy=policy)
                    except PermissionError as error:
                        self._write_json(HTTPStatus.FORBIDDEN, {"error": str(error)})
                        return
                    except (ValueError, FileNotFoundError) as error:
                        self._write_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
                        return
                    except Exception as error:  # noqa: BLE001
                        self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(error)})
                        return
                    self._write_json(HTTPStatus.CREATED, result)
                    return

                self._write_json(HTTPStatus.NOT_FOUND, {"error": "Rota nao encontrada."})

            def _require_auth(self) -> AccessTokenPolicy | None:
                header = str(self.headers.get("Authorization") or "").strip()
                if not header.lower().startswith("bearer "):
                    self._write_json(HTTPStatus.UNAUTHORIZED, {"error": "Token Bearer ausente."})
                    return None
                token = header[7:].strip()
                policy = authenticate_token(token, server.access_policies)
                if policy is None:
                    self._write_json(HTTPStatus.UNAUTHORIZED, {"error": "Token invalido."})
                    return None
                return policy

            def _read_json_body(self) -> dict[str, object] | None:
                length_raw = self.headers.get("Content-Length")
                if not length_raw:
                    self._write_json(HTTPStatus.BAD_REQUEST, {"error": "Body JSON obrigatorio."})
                    return None

                try:
                    length = int(length_raw)
                except ValueError:
                    self._write_json(HTTPStatus.BAD_REQUEST, {"error": "Content-Length invalido."})
                    return None

                raw = self.rfile.read(length)
                try:
                    payload = json.loads(raw.decode("utf-8-sig"))
                except json.JSONDecodeError:
                    self._write_json(HTTPStatus.BAD_REQUEST, {"error": "JSON invalido."})
                    return None

                if not isinstance(payload, dict):
                    self._write_json(HTTPStatus.BAD_REQUEST, {"error": "Body deve ser objeto JSON."})
                    return None
                return payload

            def _write_json(self, status_code: HTTPStatus, payload: dict[str, object]) -> None:
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status_code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args) -> None:  # noqa: A003
                return

        return Handler

