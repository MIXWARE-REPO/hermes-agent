#!/usr/bin/env python3
"""Hermes rearme standby orchestrator.

This is the one-command entrypoint to leave the system ready before a drop:
- run phase 1 diagnostics
- run phase 2 local recovery
- if recovery still needs human/browser auth, emit a browser handoff contract

The goal is not to invent success. It prepares the exact next action so that
when the failure happens, the operator has a deterministic path.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import importlib.util


def _load_helper(module_name: str, filename: str):
    path = PROJECT_ROOT / "scripts" / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_doctor_mod = _load_helper("hermes_reconnect_doctor", "hermes_reconnect_doctor.py")
_recovery_mod = _load_helper("hermes_reconnect_recovery", "hermes_reconnect_recovery.py")
collect_doctor_report = _doctor_mod.collect_report
collect_recovery_report = _recovery_mod.collect_recovery_report

DEFAULT_OUTPUT = Path("/tmp/hermes_reconnect_standby.json")
DEFAULT_BROWSER_HANDOFF = Path("/tmp/hermes_reconnect_browser_handoff.json")


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _serialize(obj: Any) -> Any:
    if hasattr(obj, "__dataclass_fields__"):
        return asdict(obj)
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "__dict__"):
        return dict(obj.__dict__)
    return obj


def build_standby_report(*, allow_browser_login: bool, restart_service: bool, service_name: str) -> Dict[str, Any]:
    doctor = collect_doctor_report()
    recovery = collect_recovery_report(
        allow_interactive_login=allow_browser_login,
        restart_service=restart_service,
        service_name=service_name,
    )

    browser_handoff = None
    ready = recovery.status == "PRIMARY_RESTORED"
    if recovery.status == "HUMAN_REQUIRED":
        browser_handoff = {
            "status": "ready_for_browser_handoff",
            "next_step": recovery.next_step,
            "standard_source": recovery.standard_source,
            "recommended_action": "Run the legitimate browser-assisted login path, then rerun standby.",
            "notes": [
                "Do not mark success until a real validation call passes.",
                "If auth requires manual approval or CAPTCHA, keep the human in the loop.",
            ],
        }
        _write_json(DEFAULT_BROWSER_HANDOFF, browser_handoff)

    summary = {
        "tool": "hermes_reconnect_standby",
        "ready_for_failure": ready,
        "doctor": _serialize(doctor),
        "recovery": _serialize(recovery),
        "browser_handoff_path": str(DEFAULT_BROWSER_HANDOFF) if browser_handoff else "",
        "browser_handoff": browser_handoff,
        "standby_guidance": (
            "System is ready to react to a future failure with the staged recovery path."
            if ready
            else "System is staged, but the primary is not yet restored; complete the indicated next step."
        ),
    }
    _write_json(DEFAULT_OUTPUT, summary)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Hermes rearme standby orchestrator")
    parser.add_argument("--allow-browser-login", action="store_true", help="Allow legitimate interactive login during recovery")
    parser.add_argument("--restart-service", action="store_true", help="Attempt service restart during recovery")
    parser.add_argument("--service-name", default="hermes-agent", help="Service name to restart if enabled")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="JSON output path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_standby_report(
        allow_browser_login=args.allow_browser_login,
        restart_service=args.restart_service,
        service_name=args.service_name,
    )
    output_path = Path(args.output).expanduser()
    _write_json(output_path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ready_for_failure"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
