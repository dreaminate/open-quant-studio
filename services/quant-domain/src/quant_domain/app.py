from __future__ import annotations

import asyncio
import json
import os
import re
import tempfile
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
from .data_import import DataImportValidationError
from .project_archive import ProjectArchiveError, export_project_archive
from .strategy_library import load_strategy_catalog, render_strategy_notebook


LAST_EVENT_ID = re.compile(r"^(0|[1-9][0-9]*)$")
UUID_ID = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-"
    r"[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
)


async def health(request: Request) -> JSONResponse:
    payload = {"status": "ok", "service": "quant-domain"}
    if request.app.state.instance_token is not None:
        payload["instance_token"] = request.app.state.instance_token
    return JSONResponse(payload)


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
    except DataImportValidationError as error:
        return JSONResponse(
            {"error": "data_import_invalid", "details": error.details},
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
    levels = request.query_params.getlist("levels")
    priorities = request.query_params.getlist("priorities")
    if any(value not in {"debug", "info", "warn", "error"} for value in levels):
        return JSONResponse({"error": "invalid_log_level"}, status_code=422)
    if any(value not in {"p1", "p2", "p3", "p4"} for value in priorities):
        return JSONResponse({"error": "invalid_log_priority"}, status_code=422)
    try:
        after_log_seq = int(request.query_params.get("after_log_seq", "0"))
        limit = int(request.query_params.get("limit", "1000"))
    except ValueError:
        return JSONResponse({"error": "invalid_log_cursor"}, status_code=422)
    if after_log_seq < 0 or limit < 1 or limit > 10000:
        return JSONResponse({"error": "invalid_log_cursor"}, status_code=422)
    domain: QuantDomain = request.app.state.domain
    page = domain.log_page(
        project_id=request.query_params.get("project_id"),
        level=level,
        priority=priority,
        activity_id=request.query_params.get("activity_id"),
        session_id=request.query_params.get("session_id"),
        run_id=request.query_params.get("run_id"),
        from_timestamp=request.query_params.get("from"),
        to_timestamp=request.query_params.get("to"),
        levels=levels or None,
        priorities=priorities or None,
        query=request.query_params.get("query"),
        after_log_seq=after_log_seq,
        limit=limit,
    )
    return JSONResponse(page)


async def get_projects(request: Request) -> JSONResponse:
    domain: QuantDomain = request.app.state.domain
    return JSONResponse({"projects": domain.projects()})


async def get_strategies(request: Request) -> JSONResponse:
    return JSONResponse(load_strategy_catalog())


async def post_strategy_notebook(request: Request) -> JSONResponse:
    payload = json.loads(await request.body())
    return JSONResponse(
        render_strategy_notebook(
            request.path_params["strategy_id"],
            payload["source"],
        )
    )


async def post_data_import_preview(request: Request) -> Response:
    project_id = request.path_params["project_id"]
    if UUID_ID.fullmatch(project_id) is None:
        return JSONResponse({"error": "invalid_project_id"}, status_code=422)
    file_name = request.query_params.get("file_name")
    source_format = request.query_params.get("source_format")
    if not file_name or not source_format:
        return JSONResponse(
            {"error": "data_import_parameters_required"}, status_code=422
        )
    domain: QuantDomain = request.app.state.domain
    try:
        preview = domain.preview_data_import(
            await request.body(), file_name, source_format
        )
    except DataImportValidationError as error:
        return JSONResponse(
            {"error": "data_import_invalid", "details": error.details},
            status_code=422,
        )
    return JSONResponse(preview)


async def get_local_data_imports(request: Request) -> Response:
    project_id = request.path_params["project_id"]
    if UUID_ID.fullmatch(project_id) is None:
        return JSONResponse({"error": "invalid_project_id"}, status_code=422)
    domain: QuantDomain = request.app.state.domain
    return JSONResponse({"files": domain.local_data_imports()})


async def post_local_data_import_preview(request: Request) -> Response:
    project_id = request.path_params["project_id"]
    if UUID_ID.fullmatch(project_id) is None:
        return JSONResponse({"error": "invalid_project_id"}, status_code=422)
    try:
        payload = json.loads(await request.body())
    except json.JSONDecodeError:
        return JSONResponse({"error": "invalid_json"}, status_code=400)
    if not isinstance(payload, dict) or set(payload) != {"file_name"} or not isinstance(
        payload["file_name"], str
    ):
        return JSONResponse({"error": "invalid_local_preview_request"}, status_code=422)
    domain: QuantDomain = request.app.state.domain
    try:
        preview = domain.preview_local_data_import(payload["file_name"])
    except DataImportValidationError as error:
        return JSONResponse(
            {"error": "data_import_invalid", "details": error.details},
            status_code=422,
        )
    return JSONResponse(preview)


async def get_data_snapshots(request: Request) -> Response:
    project_id = request.path_params["project_id"]
    if UUID_ID.fullmatch(project_id) is None:
        return JSONResponse({"error": "invalid_project_id"}, status_code=422)
    domain: QuantDomain = request.app.state.domain
    return JSONResponse({"snapshots": domain.data_snapshots(project_id)})


async def get_data_snapshot(request: Request) -> Response:
    project_id = request.path_params["project_id"]
    snapshot_id = request.path_params["snapshot_id"]
    if UUID_ID.fullmatch(project_id) is None:
        return JSONResponse({"error": "invalid_project_id"}, status_code=422)
    if UUID_ID.fullmatch(snapshot_id) is None:
        return JSONResponse({"error": "invalid_snapshot_id"}, status_code=422)
    domain: QuantDomain = request.app.state.domain
    snapshot = domain.data_snapshot(project_id, snapshot_id)
    if snapshot is None:
        return JSONResponse({"error": "data_snapshot_not_found"}, status_code=404)
    return JSONResponse(snapshot)


async def get_data_snapshot_market_input(request: Request) -> Response:
    project_id = request.path_params["project_id"]
    snapshot_id = request.path_params["snapshot_id"]
    if UUID_ID.fullmatch(project_id) is None:
        return JSONResponse({"error": "invalid_project_id"}, status_code=422)
    if UUID_ID.fullmatch(snapshot_id) is None:
        return JSONResponse({"error": "invalid_snapshot_id"}, status_code=422)
    domain: QuantDomain = request.app.state.domain
    try:
        content = domain.data_snapshot_market_input(project_id, snapshot_id)
    except (ArtifactBlobMissing, ArtifactIntegrityMismatch) as error:
        return JSONResponse({"error": error.code}, status_code=409)
    if content is None:
        return JSONResponse({"error": "data_snapshot_not_found"}, status_code=404)
    artifact, body = content
    return Response(body, media_type=artifact["media_type"])


async def get_activities(request: Request) -> Response:
    project_id = request.path_params["project_id"]
    if UUID_ID.fullmatch(project_id) is None:
        return JSONResponse({"error": "invalid_project_id"}, status_code=422)
    domain: QuantDomain = request.app.state.domain
    return JSONResponse({"activities": domain.activities(project_id)})


async def get_runs(request: Request) -> Response:
    project_id = request.path_params["project_id"]
    activity_id = request.query_params.get("activity_id")
    if UUID_ID.fullmatch(project_id) is None:
        return JSONResponse({"error": "invalid_project_id"}, status_code=422)
    if activity_id is not None and UUID_ID.fullmatch(activity_id) is None:
        return JSONResponse({"error": "invalid_activity_id"}, status_code=422)
    domain: QuantDomain = request.app.state.domain
    return JSONResponse(
        {"runs": domain.runs(project_id, activity_id=activity_id)}
    )


async def get_run(request: Request) -> Response:
    project_id = request.path_params["project_id"]
    run_id = request.path_params["run_id"]
    if UUID_ID.fullmatch(project_id) is None:
        return JSONResponse({"error": "invalid_project_id"}, status_code=422)
    if UUID_ID.fullmatch(run_id) is None:
        return JSONResponse({"error": "invalid_run_id"}, status_code=422)
    domain: QuantDomain = request.app.state.domain
    try:
        run = domain.run(project_id, run_id)
    except (ArtifactBlobMissing, ArtifactIntegrityMismatch) as error:
        return JSONResponse({"error": error.code}, status_code=409)
    if run is None:
        return JSONResponse({"error": "run_not_found"}, status_code=404)
    return JSONResponse(run)


async def get_run_report(request: Request) -> Response:
    project_id = request.path_params["project_id"]
    run_id = request.path_params["run_id"]
    if UUID_ID.fullmatch(project_id) is None:
        return JSONResponse({"error": "invalid_project_id"}, status_code=422)
    if UUID_ID.fullmatch(run_id) is None:
        return JSONResponse({"error": "invalid_run_id"}, status_code=422)
    domain: QuantDomain = request.app.state.domain
    try:
        report = domain.run_report(project_id, run_id)
    except (ArtifactBlobMissing, ArtifactIntegrityMismatch) as error:
        return JSONResponse({"error": error.code}, status_code=409)
    if report is None:
        return JSONResponse({"error": "run_report_not_found"}, status_code=404)
    return JSONResponse(report)


async def get_forward_test(request: Request) -> Response:
    project_id = request.path_params["project_id"]
    forward_test_id = request.path_params["forward_test_id"]
    if UUID_ID.fullmatch(project_id) is None:
        return JSONResponse({"error": "invalid_project_id"}, status_code=422)
    if UUID_ID.fullmatch(forward_test_id) is None:
        return JSONResponse({"error": "invalid_forward_test_id"}, status_code=422)
    domain: QuantDomain = request.app.state.domain
    result = domain.forward_test(project_id, forward_test_id)
    if result is None:
        return JSONResponse({"error": "forward_test_not_found"}, status_code=404)
    return JSONResponse(result)


async def get_project_archive(request: Request) -> Response:
    project_id = request.path_params["project_id"]
    if UUID_ID.fullmatch(project_id) is None:
        return JSONResponse({"error": "invalid_project_id"}, status_code=422)
    selected_logs = request.query_params.get("selected_logs", "full")
    if selected_logs not in {"full", "warn_error", "none"}:
        return JSONResponse({"error": "invalid_log_selection"}, status_code=422)
    domain: QuantDomain = request.app.state.domain
    exports_root = domain.data_root / "exports"
    exports_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=exports_root) as temporary_directory:
        archive_path = Path(temporary_directory) / f"{project_id}.oqs.zip"
        try:
            exported = export_project_archive(
                domain,
                project_id=project_id,
                archive_path=archive_path,
                selected_logs=selected_logs,
            )
        except ProjectArchiveError as error:
            return JSONResponse(
                {"error": "project_archive_unavailable", "message": str(error)},
                status_code=409,
            )
        archive_body = exported.archive_path.read_bytes()
    return Response(
        archive_body,
        media_type="application/vnd.open-quant-studio.project-archive+zip",
        headers={
            "Content-Disposition": f'attachment; filename="{project_id}.oqs.zip"',
            "Cache-Control": "no-store",
        },
    )


async def get_artifact(request: Request) -> Response:
    project_id = request.path_params["project_id"]
    artifact_id = request.path_params["artifact_id"]
    if UUID_ID.fullmatch(project_id) is None:
        return JSONResponse({"error": "invalid_project_id"}, status_code=422)
    if UUID_ID.fullmatch(artifact_id) is None:
        return JSONResponse({"error": "invalid_artifact_id"}, status_code=422)
    domain: QuantDomain = request.app.state.domain
    artifact = domain.artifact(project_id, artifact_id)
    if artifact is None:
        return JSONResponse({"error": "artifact_not_found"}, status_code=404)
    return JSONResponse(artifact)


async def get_artifact_content(request: Request) -> Response:
    project_id = request.path_params["project_id"]
    artifact_id = request.path_params["artifact_id"]
    if UUID_ID.fullmatch(project_id) is None:
        return JSONResponse({"error": "invalid_project_id"}, status_code=422)
    if UUID_ID.fullmatch(artifact_id) is None:
        return JSONResponse({"error": "invalid_artifact_id"}, status_code=422)
    domain: QuantDomain = request.app.state.domain
    try:
        content = domain.artifact_content(project_id, artifact_id)
    except (ArtifactBlobMissing, ArtifactIntegrityMismatch) as error:
        return JSONResponse({"error": error.code}, status_code=409)
    if content is None:
        return JSONResponse({"error": "artifact_not_found"}, status_code=404)
    artifact, body = content
    return Response(body, media_type=artifact["media_type"])


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


def create_app(data_root: Path, instance_token: str | None = None) -> Starlette:
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
            Route("/v1/projects", get_projects, methods=["GET"]),
            Route("/v1/strategies", get_strategies, methods=["GET"]),
            Route(
                "/v1/strategies/{strategy_id}/notebook",
                post_strategy_notebook,
                methods=["POST"],
            ),
            Route(
                "/v1/projects/{project_id}/data-imports/preview",
                post_data_import_preview,
                methods=["POST"],
            ),
            Route(
                "/v1/projects/{project_id}/data-imports/local-files",
                get_local_data_imports,
                methods=["GET"],
            ),
            Route(
                "/v1/projects/{project_id}/data-imports/local-preview",
                post_local_data_import_preview,
                methods=["POST"],
            ),
            Route(
                "/v1/projects/{project_id}/data-snapshots/{snapshot_id}/market-input",
                get_data_snapshot_market_input,
                methods=["GET"],
            ),
            Route(
                "/v1/projects/{project_id}/data-snapshots/{snapshot_id}",
                get_data_snapshot,
                methods=["GET"],
            ),
            Route(
                "/v1/projects/{project_id}/data-snapshots",
                get_data_snapshots,
                methods=["GET"],
            ),
            Route(
                "/v1/projects/{project_id}/activities",
                get_activities,
                methods=["GET"],
            ),
            Route(
                "/v1/projects/{project_id}/runs/{run_id}/report",
                get_run_report,
                methods=["GET"],
            ),
            Route(
                "/v1/projects/{project_id}/runs/{run_id}",
                get_run,
                methods=["GET"],
            ),
            Route(
                "/v1/projects/{project_id}/runs",
                get_runs,
                methods=["GET"],
            ),
            Route(
                "/v1/projects/{project_id}/forward-tests/{forward_test_id}",
                get_forward_test,
                methods=["GET"],
            ),
            Route(
                "/v1/projects/{project_id}/archive",
                get_project_archive,
                methods=["GET"],
            ),
            Route(
                "/v1/projects/{project_id}/artifacts/{artifact_id}/content",
                get_artifact_content,
                methods=["GET"],
            ),
            Route(
                "/v1/projects/{project_id}/artifacts/{artifact_id}",
                get_artifact,
                methods=["GET"],
            ),
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
    application.state.instance_token = instance_token
    return application


app = create_app(
    Path(os.environ.get("OQS_DATA_ROOT", "var")),
    os.environ.get("OQS_DOMAIN_INSTANCE_TOKEN"),
)
