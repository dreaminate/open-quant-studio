from __future__ import annotations

import asyncio
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
    ArtifactBlobMissing,
    ArtifactIntegrityMismatch,
    BlobHashMismatch,
    ContractViolation,
    DomainConflict,
    MessageAccessDenied,
    MessageBodyTooLarge,
    QuantDomain,
)


LAST_EVENT_ID = re.compile(r"^(0|[1-9][0-9]*)$")
UUID_ID = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-"
    r"[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
)


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
    raw_wait = request.query_params.get("wait")
    if raw_wait is not None and raw_wait not in {"0", "1"}:
        return JSONResponse({"error": "invalid_wait"}, status_code=422)
    wait = raw_wait == "1"

    domain: QuantDomain = request.app.state.domain

    async def frames() -> AsyncIterator[str]:
        next_cursor = cursor
        while True:
            events = domain.events(project_id, after_stream_seq=next_cursor)
            for event in events:
                data = json.dumps(event, separators=(",", ":"))
                yield (
                    f"id: {event['stream_seq']}\n"
                    "event: domain.event\n"
                    f"data: {data}\n\n"
                )
                next_cursor = event["stream_seq"]
            if events or not wait:
                return
            if await request.is_disconnected():
                return
            await asyncio.sleep(0.05)

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


async def get_sessions(request: Request) -> JSONResponse:
    project_id = request.query_params.get("project_id")
    if project_id is None:
        return JSONResponse({"error": "project_id_required"}, status_code=422)
    domain: QuantDomain = request.app.state.domain
    return JSONResponse({"sessions": domain.sessions(project_id)})


async def get_inbox(request: Request) -> JSONResponse:
    project_id = request.query_params.get("project_id")
    session_id = request.query_params.get("session_id")
    if project_id is None:
        return JSONResponse({"error": "project_id_required"}, status_code=422)
    if session_id is None:
        return JSONResponse({"error": "session_id_required"}, status_code=422)
    raw_after = request.query_params.get("after", "0")
    raw_limit = request.query_params.get("limit", "100")
    if re.fullmatch(r"(?:0|[1-9][0-9]*)", raw_after) is None:
        return JSONResponse({"error": "invalid_inbox_after"}, status_code=422)
    if re.fullmatch(r"(?:[1-9]|[1-9][0-9]|100)", raw_limit) is None:
        return JSONResponse({"error": "invalid_inbox_limit"}, status_code=422)
    domain: QuantDomain = request.app.state.domain
    return JSONResponse(
        {
            "messages": domain.inbox(
                project_id,
                session_id,
                after=int(raw_after),
                limit=int(raw_limit),
            )
        }
    )


async def get_message(request: Request) -> Response:
    project_id = request.query_params.get("project_id")
    recipient_session_id = request.query_params.get("recipient_session_id")
    if project_id is None:
        return JSONResponse({"error": "project_id_required"}, status_code=422)
    if recipient_session_id is None:
        return JSONResponse(
            {"error": "recipient_session_id_required"}, status_code=422
        )
    domain: QuantDomain = request.app.state.domain
    try:
        message = domain.message(
            request.path_params["message_id"],
            project_id=project_id,
            recipient_session_id=recipient_session_id,
        )
    except MessageAccessDenied as error:
        return JSONResponse({"error": error.code}, status_code=403)
    except MessageBodyTooLarge as error:
        return JSONResponse({"error": error.code}, status_code=413)
    except (ArtifactBlobMissing, ArtifactIntegrityMismatch, DomainConflict) as error:
        return JSONResponse({"error": getattr(error, "code", "message_unavailable")}, status_code=409)
    if message is None:
        return JSONResponse({"error": "message_not_found"}, status_code=404)
    return JSONResponse(message)


async def get_revision(request: Request) -> Response:
    project_id = request.query_params.get("project_id")
    if project_id is None:
        return JSONResponse({"error": "project_id_required"}, status_code=422)
    if UUID_ID.fullmatch(project_id) is None:
        return JSONResponse({"error": "invalid_project_id"}, status_code=422)
    if UUID_ID.fullmatch(request.path_params["revision_id"]) is None:
        return JSONResponse({"error": "invalid_revision_id"}, status_code=422)
    domain: QuantDomain = request.app.state.domain
    revision = domain.revision(project_id, request.path_params["revision_id"])
    if revision is None:
        return JSONResponse({"error": "revision_not_found"}, status_code=404)
    return JSONResponse(revision)


async def get_variants(request: Request) -> JSONResponse:
    project_id = request.query_params.get("project_id")
    if project_id is None:
        return JSONResponse({"error": "project_id_required"}, status_code=422)
    if UUID_ID.fullmatch(project_id) is None:
        return JSONResponse({"error": "invalid_project_id"}, status_code=422)
    domain: QuantDomain = request.app.state.domain
    return JSONResponse({"variants": domain.variants(project_id)})


async def compare_revisions(request: Request) -> Response:
    project_id = request.query_params.get("project_id")
    left_revision_id = request.query_params.get("left_revision_id")
    right_revision_id = request.query_params.get("right_revision_id")
    if project_id is None:
        return JSONResponse({"error": "project_id_required"}, status_code=422)
    if left_revision_id is None:
        return JSONResponse({"error": "left_revision_id_required"}, status_code=422)
    if right_revision_id is None:
        return JSONResponse({"error": "right_revision_id_required"}, status_code=422)
    if UUID_ID.fullmatch(project_id) is None:
        return JSONResponse({"error": "invalid_project_id"}, status_code=422)
    if UUID_ID.fullmatch(left_revision_id) is None:
        return JSONResponse({"error": "invalid_left_revision_id"}, status_code=422)
    if UUID_ID.fullmatch(right_revision_id) is None:
        return JSONResponse({"error": "invalid_right_revision_id"}, status_code=422)
    domain: QuantDomain = request.app.state.domain
    try:
        comparison = domain.compare_revisions(
            project_id, left_revision_id, right_revision_id
        )
    except DomainConflict as error:
        return JSONResponse(
            {"error": error.code, "message": str(error)}, status_code=409
        )
    return JSONResponse(comparison)


async def get_project_revision_head(request: Request) -> Response:
    project_id = request.path_params["project_id"]
    if UUID_ID.fullmatch(project_id) is None:
        return JSONResponse({"error": "invalid_project_id"}, status_code=422)
    domain: QuantDomain = request.app.state.domain
    head_revision_id = domain.project_head(project_id)
    if head_revision_id is None:
        return JSONResponse({"error": "project_head_not_found"}, status_code=404)
    return JSONResponse(
        {"project_id": project_id, "head_revision_id": head_revision_id}
    )


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
            Route("/v1/sessions", get_sessions, methods=["GET"]),
            Route("/v1/inbox", get_inbox, methods=["GET"]),
            Route("/v1/messages/{message_id}", get_message, methods=["GET"]),
            Route(
                "/v1/revisions/compare", compare_revisions, methods=["GET"]
            ),
            Route("/v1/revisions/{revision_id}", get_revision, methods=["GET"]),
            Route("/v1/variants", get_variants, methods=["GET"]),
            Route(
                "/v1/projects/{project_id}/revision-head",
                get_project_revision_head,
                methods=["GET"],
            ),
        ]
    )
    application.state.domain = QuantDomain(data_root)
    return application


app = create_app(Path(os.environ.get("OQS_DATA_ROOT", "var")))
