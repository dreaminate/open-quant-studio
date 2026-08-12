#!/usr/bin/env python3
"""Generate deterministic, read-only companion notebooks for OQS strategy sources."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "services" / "quant-domain" / "src"))

from quant_domain.strategy_library import finalize_strategy_notebooks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--catalog",
        type=Path,
        default=Path("strategies/catalog.json"),
    )
    parser.add_argument("--output-dir", type=Path)
    arguments = parser.parse_args()
    catalog_path = arguments.catalog.resolve()
    output_directory = (
        arguments.output_dir.resolve()
        if arguments.output_dir is not None
        else catalog_path.parent.parent
    )
    finalize_strategy_notebooks(catalog_path, output_directory)


if __name__ == "__main__":
    main()
