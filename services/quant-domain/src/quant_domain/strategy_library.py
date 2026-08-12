from __future__ import annotations

import hashlib
import json
from pathlib import Path


GENERATOR = "oqs-finalize-strategy-notebooks/v1"
REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
CATALOG_PATH = REPOSITORY_ROOT / "strategies" / "catalog.json"


def load_strategy_catalog(catalog_path: Path = CATALOG_PATH) -> dict[str, object]:
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    repository_root = catalog_path.parent.parent
    strategies = []
    for record in catalog["strategies"]:
        source_body = (repository_root / record["source"]).read_text(encoding="utf-8")
        strategies.append(
            {
                **record,
                "source_body": source_body,
                "source_sha256": hashlib.sha256(source_body.encode()).hexdigest(),
            }
        )
    return {"schema_version": catalog["schema_version"], "strategies": strategies}


def markdown_cell(source: str) -> dict[str, object]:
    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": source,
    }


def code_cell(source: str, role: str) -> dict[str, object]:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {"oqs": {"role": role}},
        "outputs": [],
        "source": source,
    }


def parameter_markdown(parameters: list[dict[str, object]]) -> str:
    rows = ["## Parameters", "", "| Name | Value | Meaning |", "| --- | --- | --- |"]
    rows.extend(
        f"| `{item['name']}` | `{item['value']}` | {item['meaning']} |"
        for item in parameters
    )
    return "\n".join(rows) + "\n"


def notebook_for(record: dict[str, object], source: str) -> dict[str, object]:
    assumptions = "\n".join(f"- {item}" for item in record["assumptions"])
    purpose = "\n".join(
        [
            f"# {record['title']}",
            "",
            record["summary"],
            "",
            "## Assumptions",
            assumptions,
            "",
            "The Python source cell below is authoritative. This notebook is a read/share companion and is not a second editable strategy surface.",
            "",
        ]
    )
    example = "\n".join(
        [
            "# Example only: do not execute this notebook as a strategy host.",
            "# OQS calls on_start() once, then on_bar(bar) once for each released bar.",
            "example_bar = {'session_seq': 1, 'symbol': 'SYMBOL', 'close_atoms': '100'}",
            "# on_start(); on_bar(example_bar)",
            "",
        ]
    )
    return {
        "cells": [
            markdown_cell(purpose),
            markdown_cell(parameter_markdown(record["parameters"])),
            code_cell(source, "authoritative_source"),
            code_cell(example, "example_not_executed"),
        ],
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python", "version": "3"},
            "oqs": {
                "generator": GENERATOR,
                "source": record["source"],
                "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
                "strategy_id": record["strategy_id"],
            },
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def notebook_body(record: dict[str, object], source: str) -> str:
    return json.dumps(notebook_for(record, source), indent=2, sort_keys=True) + "\n"


def render_strategy_notebook(
    strategy_id: str,
    source: str,
    catalog_path: Path = CATALOG_PATH,
) -> dict[str, object]:
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    record = next(
        strategy
        for strategy in catalog["strategies"]
        if strategy["strategy_id"] == strategy_id
    )
    body = notebook_body(record, source)
    return {
        "strategy_id": strategy_id,
        "file_name": "strategy.ipynb",
        "body": body,
        "sha256": hashlib.sha256(body.encode()).hexdigest(),
    }


def finalize_strategy_notebooks(
    catalog_path: Path,
    output_directory: Path,
) -> None:
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    repository_root = catalog_path.parent.parent
    for record in catalog["strategies"]:
        source = (repository_root / record["source"]).read_text(encoding="utf-8")
        destination = output_directory / record["notebook"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            notebook_body(record, source),
            encoding="utf-8",
        )
