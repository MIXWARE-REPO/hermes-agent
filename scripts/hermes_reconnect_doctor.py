#!/usr/bin/env python3
"""Hermes model rearme doctor — phase 1 diagnostics.

This script does not perform recovery. It inspects the local environment and
emits a JSON contract that can be used by later recovery phases.

Primary intent:
- inspect Codex auth status
- check CLI/tool availability
- inspect Hermes config and env paths
- detect whether Playwright is present for later browser-assisted phases
- suggest the next recovery step without inventing success
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from hermes_cli.auth import get_codex_auth_status
from hermes_cli.config import get_config_path, get_env_path, get_hermes_home, load_config

CONTRACT_VERSION = "2.0"
SCRIPT_NAME = "hermes_reconnect_doctor"


@dataclass
class ProbeResult:
    available: bool
    detail: str = ""
    version: str = ""
    command: str = ""


@dataclass
class FileProbe:
    path: str
    exists: bool
    size: Optional[int] = None
    modified_time: Optional[str] = None


@dataclass
class Report:
    tool: str
    contract_version: str
    phase: str
    status: str
    recommendation: str
    issues: List[str]
    next_step: str
    environment: Dict[str, Any]
    config: Dict[str, Any]
    probes: Dict[str, Any]
    standard_source: str


def mask_secret(value: str) -> str:
    if not value:
        return value
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}{'*' * (len(value) - 8)}{value[-4:]}"


def probe_command(command: str, args: Sequence[str] = ("--version",), runner: Optional[Callable[..., subprocess.CompletedProcess]] = None) -> ProbeResult:
    runner = runner or subprocess.run
    resolved = shutil.which(command)
    if not resolved:
        return ProbeResult(available=False, detail="command not found", command=command)

    try:
        completed = runner(
            [command, *args],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except Exception as exc:
        return ProbeResult(available=True, detail=str(exc), command=resolved)

    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()
    detail = stdout or stderr or "ok"
    return ProbeResult(
        available=completed.returncode == 0,
        detail=detail,
        version=stdout,
        command=resolved,
    )


def probe_playwright(runner: Optional[Callable[..., subprocess.CompletedProcess]] = None) -> ProbeResult:
    runner = runner or subprocess.run
    if importlib.util.find_spec("playwright") is None:
        return ProbeResult(available=False, detail="playwright module not installed")

    try:
        completed = runner(
            [sys.executable, "-m", "playwright", "--version"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except Exception as exc:
        return ProbeResult(available=True, detail=str(exc), command=f"{sys.executable} -m playwright")

    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()
    detail = stdout or stderr or "ok"
    return ProbeResult(
        available=completed.returncode == 0,
        detail=detail,
        version=stdout,
        command=f"{sys.executable} -m playwright",
    )


def file_probe(path: Path) -> FileProbe:
    exists = path.exists()
    if not exists:
        return FileProbe(path=str(path), exists=False)
    stat = path.stat()
    return FileProbe(
        path=str(path),
        exists=True,
        size=stat.st_size,
        modified_time=str(stat.st_mtime),
    )


def _load_config_safe(loader: Optional[Callable[[], Dict[str, Any]]] = None) -> Dict[str, Any]:
    loader = loader or load_config
    try:
        config = loader()
    except Exception:
        return {}
    return config if isinstance(config, dict) else {}


def collect_report(
    *,
    codex_status_fn: Optional[Callable[[], Dict[str, Any]]] = None,
    command_runner: Optional[Callable[..., subprocess.CompletedProcess]] = None,
    config_loader: Optional[Callable[[], Dict[str, Any]]] = None,
) -> Report:
    codex_status_fn = codex_status_fn or get_codex_auth_status
    command_runner = command_runner or subprocess.run
    config_loader = config_loader or load_config
    hermes_home = get_hermes_home()
    env_path = get_env_path()
    config_path = get_config_path()
    project_cli_config = PROJECT_ROOT / "cli-config.yaml"
    project_cli_config_example = PROJECT_ROOT / "cli-config.yaml.example"

    codex_cli = probe_command("codex", runner=command_runner)
    playwright = probe_playwright(runner=command_runner)
    codex_auth = codex_status_fn()
    config = _load_config_safe(config_loader)

    model_cfg = config.get("model")
    if isinstance(model_cfg, dict):
        configured_model = (model_cfg.get("default") or model_cfg.get("name") or "").strip()
    elif isinstance(model_cfg, str):
        configured_model = model_cfg.strip()
    else:
        configured_model = ""

    environment = {
        "project_root": str(PROJECT_ROOT),
        "hermes_home": str(hermes_home),
        "env_file": str(env_path),
        "config_file": str(config_path),
        "cli_config_file": str(project_cli_config),
        "cli_config_example": str(project_cli_config_example),
        "python": sys.version.split()[0],
        "python_executable": sys.executable,
    }

    probes = {
        "codex_cli": asdict(codex_cli),
        "playwright": asdict(playwright),
        "codex_auth": codex_auth,
        "files": [
            asdict(file_probe(env_path)),
            asdict(file_probe(config_path)),
            asdict(file_probe(project_cli_config)),
            asdict(file_probe(project_cli_config_example)),
        ],
    }

    issues: List[str] = []
    recommendations: List[str] = []

    if not codex_cli.available:
        issues.append("codex_cli_missing")
        recommendations.append("Install Codex CLI or fix PATH before trying recovery.")
    if not codex_auth.get("logged_in"):
        issues.append("codex_auth_missing")
        recommendations.append("Run hermes login (or equivalent authorized login flow) before phase 2.")
    if not playwright.available:
        issues.append("playwright_missing")
        recommendations.append("Install Playwright + Chromium before browser-assisted recovery.")
    if not config_path.exists() and not project_cli_config.exists():
        issues.append("config_missing")
        recommendations.append("Create ~/.hermes/config.yaml or a project cli-config.yaml before executing recovery.")
    if not configured_model:
        issues.append("model_not_configured")
        recommendations.append("Set the default model in config.yaml before attempting a handoff.")

    if not issues:
        status = "PHASE1_OK"
        recommendation = "Ready for phase 2: local recovery script and validation path."
        next_step = "Proceed to implement the recovery doctor and validation flow."
    elif {"codex_cli_missing", "codex_auth_missing"}.issubset(set(issues)):
        status = "PHASE1_BLOCKED"
        recommendation = "Core Codex prerequisites are missing; human intervention is required before recovery can proceed."
        next_step = "Restore Codex CLI and auth first, then rerun this diagnosis."
    else:
        status = "PHASE1_WARN"
        recommendation = "Environment is partially ready, but recovery should not be declared successful yet."
        next_step = "Fix the listed issues, then rerun this diagnosis before continuing."

    return Report(
        tool=SCRIPT_NAME,
        contract_version=CONTRACT_VERSION,
        phase="diagnose",
        status=status,
        recommendation=recommendation,
        issues=issues,
        next_step=next_step,
        environment=environment,
        config={
            "configured_model": configured_model,
            "raw_model_type": type(model_cfg).__name__ if model_cfg is not None else "none",
            "config_keys": sorted(config.keys()),
        },
        probes=probes,
        standard_source="estrategia_rearme_modelo_ia_hermes.txt",
    )


def emit_report(report: Report, output_path: Optional[Path] = None, pretty: bool = True) -> str:
    payload = asdict(report)
    text = json.dumps(payload, indent=2 if pretty else None, ensure_ascii=False)
    print(text)
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text + "\n", encoding="utf-8")
    return text


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Hermes model rearme doctor — phase 1 diagnostics")
    parser.add_argument("--json-output", default="", help="Optional path where the JSON report will be written")
    parser.add_argument("--compact", action="store_true", help="Emit minified JSON instead of pretty JSON")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_path = Path(args.json_output).expanduser() if args.json_output else None
    report = collect_report()
    emit_report(report, output_path=output_path, pretty=not args.compact)
    return 0 if report.status == "PHASE1_OK" else 2 if report.status == "PHASE1_BLOCKED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
