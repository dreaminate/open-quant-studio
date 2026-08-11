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
    }:
        artifact = (
            fixture
            if contract_case["kind"] == "artifact"
            else fixture["payload"]["artifact"]
        )
        valid = artifact["storage_uri"] == f"cas://sha256/{artifact['sha256']}"
    results[contract_case["name"]] = valid

sys.stdout.write(json.dumps(results, sort_keys=True))
