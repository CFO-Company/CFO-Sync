from __future__ import annotations

import json
import time
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin
from urllib.request import Request, urlopen


class RemoteApiError(RuntimeError):
    pass


@dataclass(frozen=True)
class RemoteJobResult:
    job_id: str
    status: str
    result: dict[str, object] | None
    error: str | None


class RemoteCFOClient:
    def __init__(self, base_url: str, token: str, timeout_seconds: float = 30.0) -> None:
        self.base_url = _normalize_base_url(base_url)
        self.token = str(token or "").strip()
        self.timeout_seconds = timeout_seconds
        if not self.token:
            raise ValueError("Token do servidor nao pode ser vazio.")

    def health(self) -> dict[str, object]:
        return self._request_json("GET", "/v1/health")

    def fetch_catalog(self) -> dict[str, object]:
        return self._request_json("GET", "/v1/catalog")

    def create_job(self, payload: dict[str, object]) -> str:
        response = self._request_json("POST", "/v1/jobs", payload=payload)
        job_id = str(response.get("job_id") or "").strip()
        if not job_id:
            raise RemoteApiError("Resposta invalida ao criar job: sem job_id.")
        return job_id

    def register_client(self, payload: dict[str, object]) -> dict[str, object]:
        return self._request_json("POST", "/v1/clients", payload=payload)

    def generate_generator_link(self, payload: dict[str, object]) -> dict[str, object]:
        return self._request_json("POST", "/v1/generators/link", payload=payload)

    def list_secret_files(self) -> dict[str, object]:
        return self._request_json("GET", "/v1/secrets/files")

    def read_secret_file(self, path: str) -> dict[str, object]:
        encoded_path = quote(str(path or "").strip(), safe="")
        return self._request_json("GET", f"/v1/secrets/file?path={encoded_path}")

    def update_secret_file(self, path: str, content: str) -> dict[str, object]:
        return self._request_json(
            "POST",
            "/v1/secrets/file",
            payload={
                "path": path,
                "content": content,
            },
        )

    def get_job(self, job_id: str) -> dict[str, object]:
        return self._request_json("GET", f"/v1/jobs/{job_id}")

    def get_job_logs(self, job_id: str) -> list[str]:
        payload = self._request_json("GET", f"/v1/jobs/{job_id}/logs")
        logs = payload.get("logs")
        if not isinstance(logs, list):
            return []
        return [str(item) for item in logs]

    def wait_for_job(
        self,
        job_id: str,
        *,
        poll_interval_seconds: float = 1.2,
        timeout_seconds: float = 900.0,
    ) -> RemoteJobResult:
        started = time.monotonic()
        while True:
            payload = self.get_job(job_id)
            status = str(payload.get("status") or "").strip().lower()
            if status in {"completed", "failed"}:
                return RemoteJobResult(
                    job_id=job_id,
                    status=status,
                    result=payload.get("result") if isinstance(payload.get("result"), dict) else None,
                    error=str(payload.get("error") or "").strip() or None,
                )
            if time.monotonic() - started > timeout_seconds:
                raise RemoteApiError(f"Timeout aguardando job {job_id}.")
            time.sleep(max(0.2, poll_interval_seconds))

    def _request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, object] | None = None,
    ) -> dict[str, object]:
        body: bytes | None = None
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.token}",
        }
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"

        request = Request(
            url=urljoin(self.base_url, path.lstrip("/")),
            data=body,
            headers=headers,
            method=method.upper(),
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read()
        except HTTPError as error:
            message = _read_http_error_message(error)
            raise RemoteApiError(f"Falha HTTP {error.code}: {message}") from error
        except URLError as error:
            raise RemoteApiError(f"Falha de conexao com servidor: {error}") from error
        except Exception as error:  # noqa: BLE001
            raise RemoteApiError(f"Falha inesperada na API remota: {error}") from error

        if not raw:
            return {}
        try:
            decoded = json.loads(raw.decode("utf-8-sig"))
        except json.JSONDecodeError as error:
            raise RemoteApiError(f"Resposta nao JSON da API remota: {error}") from error
        if not isinstance(decoded, dict):
            raise RemoteApiError("Resposta invalida da API remota: esperado objeto JSON.")
        return decoded


def _normalize_base_url(raw: str) -> str:
    cleaned = str(raw or "").strip()
    if not cleaned:
        raise ValueError("URL do servidor nao pode ser vazia.")
    if not cleaned.endswith("/"):
        cleaned += "/"
    return cleaned


def _read_http_error_message(error: HTTPError) -> str:
    try:
        raw = error.read()
    except Exception:  # noqa: BLE001
        raw = b""

    if not raw:
        return str(error.reason)
    try:
        payload = json.loads(raw.decode("utf-8-sig"))
        if isinstance(payload, dict):
            return str(payload.get("error") or error.reason)
    except Exception:  # noqa: BLE001
        pass
    return str(error.reason)

