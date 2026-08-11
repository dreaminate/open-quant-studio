from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource


SCHEMA_DIR = (
    Path(__file__).resolve().parents[4] / "packages" / "contracts" / "schemas" / "v1"
)
SCHEMAS = {
    schema_path.name.removesuffix(".schema.json"): json.loads(schema_path.read_text())
    for schema_path in SCHEMA_DIR.glob("*.schema.json")
}
REGISTRY = Registry().with_resources(
    (schema["$id"], Resource.from_contents(schema)) for schema in SCHEMAS.values()
)
CONTEXT_CAPTURE_VALIDATOR = Draft202012Validator(
    SCHEMAS["context-capture-command"],
    registry=REGISTRY,
    format_checker=FormatChecker(),
)
COMMAND_ENVELOPE_VALIDATOR = Draft202012Validator(
    SCHEMAS["command-envelope"],
    registry=REGISTRY,
    format_checker=FormatChecker(),
)
SESSION_COMMAND_VALIDATOR = Draft202012Validator(
    SCHEMAS["session-command"],
    registry=REGISTRY,
    format_checker=FormatChecker(),
)
REVISION_COMMAND_VALIDATOR = Draft202012Validator(
    SCHEMAS["revision-command"],
    registry=REGISTRY,
    format_checker=FormatChecker(),
)
FORMAL_RUN_COMMAND_VALIDATOR = Draft202012Validator(
    SCHEMAS["formal-run-command"],
    registry=REGISTRY,
    format_checker=FormatChecker(),
)
EVENT_ENVELOPE_VALIDATOR = Draft202012Validator(
    SCHEMAS["event-envelope"],
    registry=REGISTRY,
    format_checker=FormatChecker(),
)
SESSION_EVENT_VALIDATOR = Draft202012Validator(
    SCHEMAS["session-event"],
    registry=REGISTRY,
    format_checker=FormatChecker(),
)
REVISION_EVENT_VALIDATOR = Draft202012Validator(
    SCHEMAS["revision-event"],
    registry=REGISTRY,
    format_checker=FormatChecker(),
)
FORMAL_RUN_EVENT_VALIDATOR = Draft202012Validator(
    SCHEMAS["formal-run-event"],
    registry=REGISTRY,
    format_checker=FormatChecker(),
)
COMMAND_VALIDATORS = {
    "context.capture": CONTEXT_CAPTURE_VALIDATOR,
    "session.register": SESSION_COMMAND_VALIDATOR,
    "session.workbench_bind": SESSION_COMMAND_VALIDATOR,
    "session.message_send": SESSION_COMMAND_VALIDATOR,
    "session.message_reply": SESSION_COMMAND_VALIDATOR,
    "session.message_receive": SESSION_COMMAND_VALIDATOR,
    "session.message_mark_injected": SESSION_COMMAND_VALIDATOR,
    "session.message_acknowledge": SESSION_COMMAND_VALIDATOR,
    "workspace.revision_create": REVISION_COMMAND_VALIDATOR,
    "strategy.variant_create": REVISION_COMMAND_VALIDATOR,
    "workspace.merge_create": REVISION_COMMAND_VALIDATOR,
    "workspace.revision_promote": REVISION_COMMAND_VALIDATOR,
    "formal.run_request": FORMAL_RUN_COMMAND_VALIDATOR,
}
DOMAIN_EVENT_VALIDATORS = {
    "context.captured": Draft202012Validator(
        SCHEMAS["context-captured-event"],
        registry=REGISTRY,
        format_checker=FormatChecker(),
    ),
    "artifact.verification_succeeded": Draft202012Validator(
        SCHEMAS["artifact-verification-event"],
        registry=REGISTRY,
        format_checker=FormatChecker(),
    ),
    "artifact.verification_failed": Draft202012Validator(
        SCHEMAS["artifact-verification-event"],
        registry=REGISTRY,
        format_checker=FormatChecker(),
    ),
    "artifact.verification_started": Draft202012Validator(
        SCHEMAS["artifact-verification-event"],
        registry=REGISTRY,
        format_checker=FormatChecker(),
    ),
    "session.registered": SESSION_EVENT_VALIDATOR,
    "session.workbench_bound": SESSION_EVENT_VALIDATOR,
    "session.message_queued": SESSION_EVENT_VALIDATOR,
    "session.message_receiver_received": SESSION_EVENT_VALIDATOR,
    "session.message_injected": SESSION_EVENT_VALIDATOR,
    "session.message_acknowledged": SESSION_EVENT_VALIDATOR,
    "workspace.revision_created": REVISION_EVENT_VALIDATOR,
    "strategy.variant_created": REVISION_EVENT_VALIDATOR,
    "workspace.merge_candidate_created": REVISION_EVENT_VALIDATOR,
    "workspace.revision_promoted": REVISION_EVENT_VALIDATOR,
    "formal.run_queued": FORMAL_RUN_EVENT_VALIDATOR,
    "formal.run_started": FORMAL_RUN_EVENT_VALIDATOR,
    "formal.run_completed": FORMAL_RUN_EVENT_VALIDATOR,
}


def context_capture_errors(command: Any) -> list[str]:
    errors = sorted(
        CONTEXT_CAPTURE_VALIDATOR.iter_errors(command),
        key=lambda error: list(error.absolute_path),
    )
    messages = [
        f"/{'/'.join(str(part) for part in error.absolute_path)} violates {error.validator}"
        for error in errors
    ]
    if not messages:
        artifact = command["payload"]["artifact"]
        expected_uri = f"cas://sha256/{artifact['sha256']}"
        if artifact["storage_uri"] != expected_uri:
            messages.append("/payload/artifact/storage_uri must match artifact sha256")
    return messages


def session_command_errors(command: Any) -> list[str]:
    errors = sorted(
        SESSION_COMMAND_VALIDATOR.iter_errors(command),
        key=lambda error: list(error.absolute_path),
    )
    messages = [
        f"/{'/'.join(str(part) for part in error.absolute_path)} violates {error.validator}"
        for error in errors
    ]
    if not messages and command["command_type"] in {
        "session.message_send",
        "session.message_reply",
    }:
        artifact = command["payload"]["artifact"]
        expected_uri = f"cas://sha256/{artifact['sha256']}"
        if artifact["storage_uri"] != expected_uri:
            messages.append("/payload/artifact/storage_uri must match artifact sha256")
        if artifact["media_type"] != "text/plain":
            messages.append("/payload/artifact/media_type must be text/plain")
        if artifact["byte_size"] > 64 * 1024:
            messages.append("/payload/artifact/byte_size exceeds 65536")
    if (
        not messages
        and command["command_type"] == "session.register"
        and command["payload"]["session_uri"]
        != f"pi-jsonl://session/{command['payload']['pi_session_id']}"
    ):
        messages.append("/payload/session_uri must match pi_session_id")
    if (
        not messages
        and command["command_type"] == "session.workbench_bind"
        and command["payload"]["workbench_id"] != command["workbench_id"]
    ):
        messages.append("/payload/workbench_id must match /workbench_id")
    return messages


def revision_command_errors(command: Any) -> list[str]:
    errors = sorted(
        REVISION_COMMAND_VALIDATOR.iter_errors(command),
        key=lambda error: list(error.absolute_path),
    )
    messages = [
        f"/{'/'.join(str(part) for part in error.absolute_path)} violates {error.validator}"
        for error in errors
    ]
    if messages:
        return messages

    command_type = command["command_type"]
    if command_type in {"workspace.revision_create", "workspace.merge_create"}:
        paths: set[str] = set()
        for index, file in enumerate(command["payload"]["files"]):
            if file["path"] in paths:
                messages.append(
                    f"/payload/files/{index}/path must be unique within the command"
                )
            if any(
                component.lower() == ".git"
                for component in file["path"].split("/")
            ):
                messages.append(
                    f"/payload/files/{index}/path must not contain a .git component"
                )
            if any(
                path.startswith(f"{file['path']}/")
                or file["path"].startswith(f"{path}/")
                for path in paths
            ):
                messages.append(
                    f"/payload/files/{index}/path must not collide with a file/directory ancestor"
                )
            paths.add(file["path"])
            artifact = file["artifact"]
            if artifact["storage_uri"] != f"cas://sha256/{artifact['sha256']}":
                messages.append(
                    f"/payload/files/{index}/artifact/storage_uri must match artifact sha256"
                )
        if (
            command_type == "workspace.revision_create"
            and
            command["expected_revision_id"] is not None
            and command["expected_revision_id"] != command["base_revision_id"]
        ):
            messages.append("/expected_revision_id must match /base_revision_id")
        if (
            command_type == "workspace.merge_create"
            and command["expected_revision_id"] == command["base_revision_id"]
        ):
            messages.append("merge project and variant parents must be distinct revisions")
        return messages

    payload = command["payload"]
    if command_type == "strategy.variant_create":
        if payload["variant_id"] != command["variant_id"]:
            messages.append("/payload/variant_id must match /variant_id")
        if payload["base_revision_id"] != command["base_revision_id"]:
            messages.append("/payload/base_revision_id must match /base_revision_id")
        return messages

    if command["expected_revision_id"] != command["base_revision_id"]:
        messages.append("/expected_revision_id must match /base_revision_id")
    if payload["variant_id"] != command["variant_id"]:
        messages.append("/payload/variant_id must match /variant_id")
    return messages


def formal_run_command_errors(command: Any) -> list[str]:
    errors = sorted(
        FORMAL_RUN_COMMAND_VALIDATOR.iter_errors(command),
        key=lambda error: list(error.absolute_path),
    )
    messages = [
        f"/{'/'.join(str(part) for part in error.absolute_path)} violates {error.validator}"
        for error in errors
    ]
    if messages:
        return messages
    payload = command["payload"]
    artifact = payload["engine_input"]
    if artifact["storage_uri"] != f"cas://sha256/{artifact['sha256']}":
        messages.append("/payload/engine_input/storage_uri must match artifact sha256")
    if command["expected_revision_id"] != command["base_revision_id"]:
        messages.append("/expected_revision_id must match /base_revision_id")
    if payload["candidate_revision_id"] != command["base_revision_id"]:
        messages.append("/payload/candidate_revision_id must match /base_revision_id")
    return messages


def command_errors(command: Any) -> list[str]:
    if not isinstance(command, dict):
        return ["/ violates type"]
    command_type = command.get("command_type")
    if command_type not in COMMAND_VALIDATORS:
        return [f"unsupported command type {command_type}"]
    if command_type == "context.capture":
        return context_capture_errors(command)
    if command_type in {
        "workspace.revision_create",
        "strategy.variant_create",
        "workspace.merge_create",
        "workspace.revision_promote",
    }:
        return revision_command_errors(command)
    if command_type == "formal.run_request":
        return formal_run_command_errors(command)
    validator = COMMAND_VALIDATORS[command_type]
    errors = sorted(
        validator.iter_errors(command), key=lambda error: list(error.absolute_path)
    )
    messages = [
        f"/{'/'.join(str(part) for part in error.absolute_path)} violates {error.validator}"
        for error in errors
    ]
    if command_type.startswith("session.") and not messages:
        messages = session_command_errors(command)
    return messages


def domain_event_errors(event: dict[str, Any]) -> list[str]:
    event_type = event.get("event_type")
    validator = DOMAIN_EVENT_VALIDATORS.get(event_type)
    if validator is None:
        return [f"unsupported domain event type {event_type}"]
    errors = [
        f"/{'/'.join(str(part) for part in error.absolute_path)} violates {error.validator}"
        for error in sorted(
            validator.iter_errors(event),
            key=lambda error: list(error.absolute_path),
        )
    ]
    if not errors and event["event_type"] == "context.captured":
        artifact = event["payload"]["artifact"]
        if artifact["storage_uri"] != f"cas://sha256/{artifact['sha256']}":
            errors.append("/payload/artifact/storage_uri must match artifact sha256")
    if not errors and event_type == "workspace.revision_created":
        parent_revision_id = event["payload"]["parent_revision_id"]
        if event["variant_id"] is None and event["base_revision_id"] is None:
            if parent_revision_id is not None:
                errors.append(
                    "/payload/parent_revision_id must be null for a root revision"
                )
        elif parent_revision_id != event["base_revision_id"]:
            errors.append("/payload/parent_revision_id must match /base_revision_id")
    if not errors and event_type == "strategy.variant_created":
        if event["payload"]["variant_id"] != event["variant_id"]:
            errors.append("/payload/variant_id must match /variant_id")
        if event["payload"]["revision_id"] != event["base_revision_id"]:
            errors.append("/payload/revision_id must match /base_revision_id")
    if not errors and event_type == "workspace.merge_candidate_created":
        payload = event["payload"]
        if payload["variant_parent_revision_id"] != event["base_revision_id"]:
            errors.append(
                "/payload/variant_parent_revision_id must match /base_revision_id"
            )
        if payload["project_parent_revision_id"] == payload["variant_parent_revision_id"]:
            errors.append("merge parent revisions must be distinct")
    if not errors and event_type == "workspace.revision_promoted":
        if event["payload"]["variant_id"] != event["variant_id"]:
            errors.append("/payload/variant_id must match /variant_id")
        if event["payload"]["previous_revision_id"] != event["base_revision_id"]:
            errors.append(
                "/payload/previous_revision_id must match /base_revision_id"
            )
    if not errors and event_type.startswith("formal.run_"):
        if event["payload"]["candidate_revision_id"] != event["base_revision_id"]:
            errors.append("/payload/candidate_revision_id must match /base_revision_id")
    if (
        not errors
        and event_type == "formal.run_completed"
        and event["payload"]["status"] == "succeeded"
        and event["payload"]["calculation_hash"]
        != event["payload"]["engine_result_sha256"]
    ):
        errors.append(
            "/payload/calculation_hash must match /payload/engine_result_sha256"
        )
    return errors
