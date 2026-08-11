from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource


cases_path = Path(sys.argv[1])
schema_dir = Path(sys.argv[2])
case_document = json.loads(cases_path.read_text())
schemas = {
    schema_path.name.removesuffix(".schema.json"): json.loads(schema_path.read_text())
    for schema_path in schema_dir.glob("*.schema.json")
}
registry = Registry().with_resources(
    (
        schema["$id"],
        Resource.from_contents(schema),
    )
    for schema in schemas.values()
)

validators = {
    "artifact_verification_event": Draft202012Validator(
        schemas["artifact-verification-event"],
        registry=registry,
        format_checker=FormatChecker(),
    ),
    "command": Draft202012Validator(
        schemas["command-envelope"],
        registry=registry,
        format_checker=FormatChecker(),
    ),
    "event": Draft202012Validator(
        schemas["event-envelope"],
        registry=registry,
        format_checker=FormatChecker(),
    ),
    "artifact": Draft202012Validator(
        schemas["artifact-ref"],
        registry=registry,
        format_checker=FormatChecker(),
    ),
    "context_capture_command": Draft202012Validator(
        schemas["context-capture-command"],
        registry=registry,
        format_checker=FormatChecker(),
    ),
    "context_captured_event": Draft202012Validator(
        schemas["context-captured-event"],
        registry=registry,
        format_checker=FormatChecker(),
    ),
    "diagnostic_log": Draft202012Validator(
        schemas["diagnostic-log"],
        registry=registry,
        format_checker=FormatChecker(),
    ),
    "session_command": Draft202012Validator(
        schemas["session-command"],
        registry=registry,
        format_checker=FormatChecker(),
    ),
    "session_event": Draft202012Validator(
        schemas["session-event"],
        registry=registry,
        format_checker=FormatChecker(),
    ),
    "revision_command": Draft202012Validator(
        schemas["revision-command"],
        registry=registry,
        format_checker=FormatChecker(),
    ),
    "revision_event": Draft202012Validator(
        schemas["revision-event"],
        registry=registry,
        format_checker=FormatChecker(),
    ),
}

results = {}
for contract_case in case_document["cases"]:
    fixture = json.loads((cases_path.parent / contract_case["fixture"]).read_text())
    valid = not any(
        validators[contract_case["kind"]].iter_errors(fixture)
    )
    if valid and contract_case["kind"] in {
        "artifact",
        "context_capture_command",
        "context_captured_event",
        "session_command",
    }:
        artifact = fixture if contract_case["kind"] == "artifact" else fixture.get("payload", {}).get("artifact")
        if artifact is not None:
            valid = artifact["storage_uri"] == f"cas://sha256/{artifact['sha256']}"
        if valid and contract_case["kind"] == "session_command":
            command_type = fixture["command_type"]
            if command_type == "session.register":
                payload = fixture["payload"]
                valid = payload["session_uri"] == f"pi-jsonl://session/{payload['pi_session_id']}"
            elif command_type == "session.workbench_bind":
                valid = fixture["payload"]["workbench_id"] == fixture["workbench_id"]
            elif command_type in {"session.message_send", "session.message_reply"}:
                artifact = fixture["payload"]["artifact"]
                valid = (
                    artifact["media_type"] == "text/plain"
                    and artifact["byte_size"] <= 64 * 1024
                )
    if valid and contract_case["kind"] == "revision_command":
        command_type = fixture["command_type"]
        payload = fixture["payload"]
        if command_type == "workspace.revision_create":
            paths = [file["path"] for file in payload["files"]]
            valid = len(paths) == len(set(paths))
            valid = valid and all(
                all(component.lower() != ".git" for component in path.split("/"))
                for path in paths
            )
            valid = valid and not any(
                left != right
                and (left.startswith(f"{right}/") or right.startswith(f"{left}/"))
                for left in paths
                for right in paths
            )
            for file in payload["files"]:
                artifact = file["artifact"]
                valid = valid and artifact["storage_uri"] == (
                    f"cas://sha256/{artifact['sha256']}"
                )
            if fixture["expected_revision_id"] is not None:
                valid = valid and fixture["expected_revision_id"] == fixture["base_revision_id"]
        elif command_type == "strategy.variant_create":
            valid = (
                payload["variant_id"] == fixture["variant_id"]
                and payload["base_revision_id"] == fixture["base_revision_id"]
            )
        else:
            valid = (
                fixture["expected_revision_id"] == fixture["base_revision_id"]
                and payload["variant_id"] == fixture["variant_id"]
            )
    if valid and contract_case["kind"] == "revision_event":
        event_type = fixture["event_type"]
        payload = fixture["payload"]
        if event_type == "workspace.revision_created":
            if fixture["variant_id"] is None and fixture["base_revision_id"] is None:
                valid = payload["parent_revision_id"] is None
            else:
                valid = payload["parent_revision_id"] == fixture["base_revision_id"]
        elif event_type == "strategy.variant_created":
            valid = (
                payload["variant_id"] == fixture["variant_id"]
                and payload["revision_id"] == fixture["base_revision_id"]
            )
        else:
            valid = (
                payload["variant_id"] == fixture["variant_id"]
                and payload["previous_revision_id"] == fixture["base_revision_id"]
            )
    results[contract_case["name"]] = valid

sys.stdout.write(json.dumps(results, sort_keys=True))
