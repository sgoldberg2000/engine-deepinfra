"""The asynchronous job surface: submit, poll, collect.

Replicate-shaped::

    POST /predictions            -> {"id": "...", "status": "starting"}
    GET  /predictions/<id>       -> {"id", "status", "output", "error"}

Kept apart from ``engine.py`` so the batch loop stays about control flow. The
caller passes its retrying request function, its emit hook and its timing.

Terminal is tested as "the status is not one a job can still leave on its own",
not by listing the ones we expect: a provider that invents a new end state
cannot make the poll run forever.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from .transport import ProviderError

RequestFn = Callable[..., dict]
EmitFn = Callable[[str], None]

#: Statuses a job can still leave on its own.
LIVE_STATUSES = frozenset({"starting", "queued", "pending", "processing", "running", "in_progress"})
SUCCESS_STATUSES = frozenset({"succeeded", "success", "completed", "complete", "done"})


def is_terminal(status: object) -> bool:
    return str(status or "") not in LIVE_STATUSES


def is_success(status: object) -> bool:
    return str(status or "").lower() in SUCCESS_STATUSES


def submit(
    request: RequestFn,
    path: str,
    body: dict,
    *,
    headers: dict[str, str] | None = None,
    emit: EmitFn = lambda _msg: None,
    prefix: str = "",
) -> dict:
    """Submit one job and return its acceptance record."""
    record = request("POST", path, body, headers=headers)
    if not isinstance(record, dict) or not record.get("id"):
        raise ProviderError(200, "The provider accepted the request but returned no job id")
    emit(f"{prefix} 🧾 Job {record['id']} accepted ({record.get('status') or 'queued'})")
    return record


def await_job(
    request: RequestFn,
    job: dict,
    *,
    status_path: str,
    poll_interval: float,
    timeout: float,
    emit: EmitFn = lambda _msg: None,
    prefix: str = "",
) -> dict:
    """Poll until the job reaches a terminal status; return the final record."""
    job_id = str(job.get("id") or "")
    if not job_id:
        raise ProviderError(200, "No job id in the provider's response")

    started = time.monotonic()
    last_status = str(job.get("status") or "")
    path = status_path.format(id=job_id)
    while True:
        if timeout and time.monotonic() - started > timeout:
            raise ProviderError(
                0,
                f"Job {job_id} did not finish within {timeout:.0f}s — it keeps "
                f"running at the provider; collect it later",
            )
        if poll_interval:
            time.sleep(poll_interval)
        record = request("GET", path)
        if not isinstance(record, dict):
            raise ProviderError(200, f"The provider returned no record for job {job_id}")
        status = str(record.get("status") or "")
        if status != last_status:
            last_status = status
            emit(f"{prefix} ⏳ Job {status}")
        if not is_terminal(status):
            continue
        if not is_success(status):
            raise ProviderError(200, _failure_message(record))
        emit(f"{prefix} ✅ Job succeeded")
        return record


def output_urls(record: dict) -> list[str]:
    """Result URLs from a finished job, in the order the provider gave them.

    The output may be a URL, a list of URLs, or a mapping that carries URLs in
    named fields — providers differ, and guessing wrong means saving nothing.
    """
    output = record.get("output")
    if output is None:
        return []
    if isinstance(output, str):
        return [output] if output.strip() else []
    if isinstance(output, list):
        return [str(item) for item in output if isinstance(item, str) and item.strip()]
    if isinstance(output, dict):
        urls: list[str] = []
        for value in output.values():
            if isinstance(value, str) and value.startswith(("http://", "https://")):
                urls.append(value)
            elif isinstance(value, list):
                urls.extend(str(item) for item in value if isinstance(item, str) and item.strip())
        return urls
    return []


def _failure_message(record: dict) -> str:
    status = record.get("status") or "failed"
    detail = record.get("error") or record.get("detail") or ""
    job_id = record.get("id") or ""
    text = f"Job {job_id} ended as {status}"
    if detail:
        text += f" — {detail}"
    return text
