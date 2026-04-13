from __future__ import annotations

import json
import sys
from typing import Iterable


def print_json(data: object) -> None:
    print(json.dumps(data, indent=2, sort_keys=True))


def print_report_line(label: str, status: str, detail: str) -> None:
    print(f"[{status}] {label}: {detail}")


def manual_step_required(explanation: str, steps: Iterable[str], needed_after: Iterable[str]) -> None:
    print("MANUAL STEP REQUIRED")
    print(explanation)
    print("Actions:")
    for step in steps:
        print(f"- {step}")
    print("Needed after this step:")
    for item in needed_after:
        print(f"- {item}")
    raise SystemExit(0)


def live_action_ready(summary: str, hardware: Iterable[str]) -> None:
    print("LIVE ACTION READY")
    print(summary)
    print("Expected hardware / resources:")
    for item in hardware:
        print(f"- {item}")
    raise SystemExit(0)


def fail(message: str, exit_code: int = 1) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(exit_code)

