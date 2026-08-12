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
    "diagnostic_command": Draft202012Validator(
        schemas["diagnostic-command"],
        registry=registry,
        format_checker=FormatChecker(),
    ),
    "diagnostic_event": Draft202012Validator(
        schemas["diagnostic-event"],
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
    "formal_run_command": Draft202012Validator(
        schemas["formal-run-command"],
        registry=registry,
        format_checker=FormatChecker(),
    ),
    "formal_run_event": Draft202012Validator(
        schemas["formal-run-event"],
        registry=registry,
        format_checker=FormatChecker(),
    ),
    "formal_run_manifest": Draft202012Validator(
        schemas["formal-run-manifest"],
        registry=registry,
        format_checker=FormatChecker(),
    ),
    "forward_test_command": Draft202012Validator(
        schemas["forward-test-command"],
        registry=registry,
        format_checker=FormatChecker(),
    ),
    "forward_test_event": Draft202012Validator(
        schemas["forward-test-event"],
        registry=registry,
        format_checker=FormatChecker(),
    ),
    "forward_test_read_model": Draft202012Validator(
        schemas["forward-test-read-model"],
        registry=registry,
        format_checker=FormatChecker(),
    ),
    "project_archive_command": Draft202012Validator(
        schemas["project-archive-command"],
        registry=registry,
        format_checker=FormatChecker(),
    ),
    "project_archive_event": Draft202012Validator(
        schemas["project-archive-event"],
        registry=registry,
        format_checker=FormatChecker(),
    ),
    "project_archive_manifest": Draft202012Validator(
        schemas["project-archive-manifest"],
        registry=registry,
        format_checker=FormatChecker(),
    ),
    "data_snapshot_command": Draft202012Validator(
        schemas["data-snapshot-command"],
        registry=registry,
        format_checker=FormatChecker(),
    ),
    "data_snapshot_event": Draft202012Validator(
        schemas["data-snapshot-event"],
        registry=registry,
        format_checker=FormatChecker(),
    ),
    "data_snapshot_read_model": Draft202012Validator(
        schemas["data-snapshot-read-model"],
        registry=registry,
        format_checker=FormatChecker(),
    ),
    "data_snapshot_import_preview_read_model": Draft202012Validator(
        schemas["data-snapshot-read-model"],
        registry=registry,
        format_checker=FormatChecker(),
    ),
    "data_snapshot_list_read_model": Draft202012Validator(
        schemas["data-snapshot-read-model"],
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
        if command_type in {"workspace.revision_create", "workspace.merge_create"}:
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
            if command_type == "workspace.revision_create":
                removed_paths = payload.get("removed_paths", [])
                valid = valid and (
                    fixture["expected_revision_id"] is not None
                    or not removed_paths
                )
                valid = valid and not set(removed_paths).intersection(paths)
            if (
                command_type == "workspace.revision_create"
                and fixture["expected_revision_id"] is not None
            ):
                valid = valid and fixture["expected_revision_id"] == fixture["base_revision_id"]
            if command_type == "workspace.merge_create":
                valid = valid and fixture["expected_revision_id"] != fixture["base_revision_id"]
        elif command_type == "strategy.variant_create":
            valid = (
                payload["variant_id"] == fixture["variant_id"]
                and payload["base_revision_id"] == fixture["base_revision_id"]
            )
        elif command_type == "workspace.revision_promote":
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
        elif event_type == "workspace.merge_candidate_created":
            valid = (
                payload["variant_parent_revision_id"] == fixture["base_revision_id"]
                and payload["project_parent_revision_id"]
                != payload["variant_parent_revision_id"]
            )
        else:
            valid = (
                payload["variant_id"] == fixture["variant_id"]
                and payload["previous_revision_id"] == fixture["base_revision_id"]
            )
    if valid and contract_case["kind"] == "formal_run_command":
        payload = fixture["payload"]
        valid = fixture["expected_revision_id"] == fixture["base_revision_id"]
        if fixture["command_type"] == "formal.run_request":
            artifact = payload["market_input"]
            valid = (
                valid
                and artifact["storage_uri"] == f"cas://sha256/{artifact['sha256']}"
                and payload["candidate_revision_id"] == fixture["base_revision_id"]
            )
        elif fixture["command_type"] == "formal.run_retry":
            valid = valid and payload["source_run_id"] != payload["run_id"]
    if valid and contract_case["kind"] == "formal_run_event":
        payload = fixture["payload"]
        valid = payload["candidate_revision_id"] == fixture["base_revision_id"]
        if valid and fixture["event_type"] == "formal.run_retried":
            valid = payload["source_run_id"] != payload["run_id"]
        if (
            valid
            and fixture["event_type"] == "formal.run_completed"
            and payload["status"] == "succeeded"
        ):
            valid = payload["calculation_hash"] == payload["engine_result_sha256"]
    if valid and contract_case["kind"] == "formal_run_manifest":
        manifest_version = fixture["manifest_version"]
        source_name = "engine_input" if manifest_version == "m3-v1" else "market_input"
        source = fixture[source_name]
        intent_tape = fixture["strategy_execution"]
        result = fixture["engine_result"]
        valid = (
            source["storage_uri"] == f"cas://sha256/{source['sha256']}"
            and intent_tape["intent_tape_storage_uri"]
            == f"cas://sha256/{intent_tape['intent_tape_sha256']}"
            and result["storage_uri"] == f"cas://sha256/{result['sha256']}"
        )
        if valid and manifest_version != "m3-v1":
            resolved = fixture["resolved_engine_input"]
            valid = (
                resolved["storage_uri"] == f"cas://sha256/{resolved['sha256']}"
                and source["artifact_id"]
                == fixture["run_spec"]["market_input_artifact_id"]
                and fixture["checkpoint"]["checkpoint_batch_size"]
                == fixture["run_spec"]["checkpoint_batch_size"]
                and fixture["checkpoint"]["engine_checkpoint_abi"]
                == fixture["run_spec"]["engine_checkpoint_abi"]
            )
    if valid and contract_case["kind"] == "project_archive_command":
        payload = fixture["payload"]
        archive = payload["archive"]
        valid = (
            payload["expected_project_id"] == fixture["project_id"]
            and archive["storage_uri"] == f"cas://sha256/{archive['sha256']}"
        )
    if valid and contract_case["kind"] == "project_archive_event":
        valid = fixture["payload"]["restored_project_id"] == fixture["project_id"]
    if valid and contract_case["kind"] == "forward_test_command":
        valid = fixture["expected_revision_id"] == fixture["base_revision_id"]
    if valid and contract_case["kind"] == "forward_test_event":
        valid = fixture["payload"]["source_revision_id"] == fixture["base_revision_id"]
    if valid and contract_case["kind"] == "project_archive_manifest":
        paths = [entry["path"] for entry in fixture["cas_objects"]]
        hashes = [entry["sha256"] for entry in fixture["cas_objects"]]
        valid = (
            paths == sorted(paths)
            and len(paths) == len(set(paths))
            and len(hashes) == len(set(hashes))
            and all(
                entry["path"]
                == f"cas/sha256/{entry['sha256'][:2]}/{entry['sha256']}"
                for entry in fixture["cas_objects"]
            )
        )
    if valid and contract_case["kind"] == "data_snapshot_command":
        payload = fixture["payload"]
        source = payload["source"]
        expected_media_type = (
            "text/csv"
            if payload["source_format"] == "csv"
            else "application/vnd.apache.parquet"
        )
        valid = (
            source["storage_uri"] == f"cas://sha256/{source['sha256']}"
            and source["media_type"] == expected_media_type
        )
    if (
        valid
        and contract_case["kind"] == "data_snapshot_import_preview_read_model"
        and "source" in fixture
    ):
        source = fixture["source"]
        expected_media_type = (
            "text/csv"
            if fixture["source_format"] == "csv"
            else "application/vnd.apache.parquet"
        )
        valid = (
            source["storage_uri"] == f"cas://sha256/{source['sha256']}"
            and source["media_type"] == expected_media_type
        )
    results[contract_case["name"]] = valid

sys.stdout.write(json.dumps(results, sort_keys=True))
