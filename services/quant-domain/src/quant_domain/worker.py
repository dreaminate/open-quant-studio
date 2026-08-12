from __future__ import annotations

import argparse
import os
import signal
from pathlib import Path
from threading import Event

from .domain import QuantDomain


def run_worker(
    domain: QuantDomain,
    *,
    stop_event: Event,
    poll_interval: float,
) -> None:
    while not stop_event.is_set():
        job = domain.run_next_job()
        if job is None:
            stop_event.wait(poll_interval)


def main() -> int:
    parser = argparse.ArgumentParser(description="Open Quant Studio domain job worker")
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path(os.environ.get("OQS_DATA_ROOT", "var")),
    )
    parser.add_argument("--poll-interval", type=float, default=0.1)
    arguments = parser.parse_args()

    stop_event = Event()

    def request_stop(_: int, __: object) -> None:
        stop_event.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    run_worker(
        QuantDomain(arguments.data_root),
        stop_event=stop_event,
        poll_interval=arguments.poll_interval,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
