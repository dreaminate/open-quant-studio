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


def domain_event_errors(event: dict[str, Any]) -> list[str]:
    validator = DOMAIN_EVENT_VALIDATORS[event["event_type"]]
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
    return errors
