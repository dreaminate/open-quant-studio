from __future__ import annotations

import json
import os
import re
from collections.abc import AsyncIterator
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

from .domain import (
    BlobHashMismatch,
    ContractViolation,
    DomainConflict,
    QuantDomain,
)


LAST_EVENT_ID = re.compile(r"^(0|[1-9][0-9]*)$")


async def health(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "quant-domain"})


async def put_artifact_blob(request: Request) -> JSONResponse:
    body = await request.body()
    domain: QuantDomain = request.app.state.domain
    try:
        blob = domain.store_blob(request.path_params["sha256"], body)
    except BlobHashMismatch as error:
        return JSONResponse(
            {"error": "artifact_hash_mismatch", "message": str(error)},
            status_code=422,
        )
    return JSONResponse(blob, status_code=201)


async def post_command(request: Request) -> JSONResponse:
    try:
        command = json.loads(await request.body())
    except json.JSONDecodeError:
        return JSONResponse({"error": "invalid_json"}, status_code=400)
    domain: QuantDomain = request.app.state.domain
    try:
        receipt = domain.submit_command(command)
    except ContractViolation as error:
        return JSONResponse(
            {"error": "contract_violation", "details": error.errors},
            status_code=422,
        )
    except DomainConflict as error:
        return JSONResponse(
            {"error": error.code, "message": str(error)}, status_code=409
        )
    status_code = 201 if receipt["disposition"] == "accepted" else 200
    return JSONResponse(receipt, status_code=status_code)


async def get_events(request: Request) -> Response:
    project_id = request.query_params.get("project_id")
    if project_id is None:
        return JSONResponse({"error": "project_id_required"}, status_code=422)
    last_event_id = request.headers.get("last-event-id")
    if last_event_id is None:
        cursor = 0
    elif LAST_EVENT_ID.fullmatch(last_event_id) is None:
        return JSONResponse({"error": "invalid_last_event_id"}, status_code=400)
    else:
        cursor = int(last_event_id)

    domain: QuantDomain = request.app.state.domain
    events = domain.events(project_id, after_stream_seq=cursor)

    async def frames() -> AsyncIterator[str]:
        for event in events:
            data = json.dumps(event, separators=(",", ":"))
            yield (
                f"id: {event['stream_seq']}\n"
                "event: domain.event\n"
                f"data: {data}\n\n"
            )

    return StreamingResponse(
        frames(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def run_next_job(request: Request) -> Response:
    domain: QuantDomain = request.app.state.domain
    job = domain.run_next_job()
    if job is None:
        return Response(status_code=204)
    return JSONResponse(job)


async def get_job(request: Request) -> Response:
    domain: QuantDomain = request.app.state.domain
    job = domain.job(request.path_params["job_id"])
    if job is None:
        return JSONResponse({"error": "job_not_found"}, status_code=404)
    return JSONResponse(job)


async def get_logs(request: Request) -> JSONResponse:
    level = request.query_params.get("level")
    priority = request.query_params.get("priority")
    if level is not None and level not in {"debug", "info", "warn", "error"}:
        return JSONResponse({"error": "invalid_log_level"}, status_code=422)
    if priority is not None and priority not in {"p1", "p2", "p3", "p4"}:
        return JSONResponse({"error": "invalid_log_priority"}, status_code=422)
    domain: QuantDomain = request.app.state.domain
    logs = domain.logs(
        project_id=request.query_params.get("project_id"),
        level=level,
        priority=priority,
    )
    return JSONResponse({"logs": logs})


def create_app(data_root: Path) -> Starlette:
    application = Starlette(
        routes=[
            Route("/health", health, methods=["GET"]),
            Route(
                "/v1/artifact-blobs/{sha256}",
                put_artifact_blob,
                methods=["PUT"],
            ),
            Route("/v1/commands", post_command, methods=["POST"]),
            Route("/v1/events", get_events, methods=["GET"]),
            Route("/v1/jobs/run-next", run_next_job, methods=["POST"]),
            Route("/v1/jobs/{job_id}", get_job, methods=["GET"]),
            Route("/v1/logs", get_logs, methods=["GET"]),
        ]
    )
    application.state.domain = QuantDomain(data_root)
    return application


app = create_app(Path(os.environ.get("OQS_DATA_ROOT", "var")))
