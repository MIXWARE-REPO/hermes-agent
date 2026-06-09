#!/usr/bin/env python3
"""Hermes model rearme recovery — phase 2.

This script attempts the non-browser recovery path:
- refresh Hermes-owned Codex credentials when possible
- validate the model with a real Codex invocation
- optionally restart the Hermes service after validation
- emit a JSON report that distinguishes recovery success from fallback/manual escalation

It intentionally does not invent success. A real model call is required.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from hermes_cli.auth import (
    AuthError,
    DEFAULT_CODEX_BASE_URL,
    _codex_device_code_login,
    _save_codex_tokens,
    _update_config_for_provider,
    get_codex_auth_status,
    resolve_codex_runtime_credentials,
)
from hermes_cli.config import get_config_path, get_env_path, get_hermes_home, load_config

CONTRACT_VERSION = "2.0"
SCRIPT_NAME = "hermes_reconnect_recovery"
RECOVERY_PROMPT = "Responde solamente OK"


@dataclass
class RecoveryReport:
    tool: str
    contract_version: str
    phase: str
    status: str
    recommendation: str
    issues: List[str]
    next_step: str
    environment: Dict[str, Any]
    auth_before: Dict[str, Any]
    auth_after: Dict[str, Any]
    validation: Dict[str, Any]
    service: Dict[str, Any]
    config: Dict[str, Any]
    standard_source: str
    actions: List[str]


def _mask_secret(value: str) -> str:
    if not value:
        return value
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}{'*' * (len(value) - 8)}{value[-4:]}"


def _load_config_safe(loader: Optional[Callable[[], Dict[str, Any]]] = None) -> Dict[str, Any]:
    loader = loader or load_config
    try:
        data = loader()
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _config_model_label(config: Dict[str, Any]) -> str:
    model_cfg = config.get("model")
    if isinstance(model_cfg, dict):
        return (model_cfg.get("default") or model_cfg.get("name") or "").strip()
    if isinstance(model_cfg, str):
        return model_cfg.strip()
    return ""


def _run_cmd(
    cmd: Sequence[str],
    *,
    cwd: Optional[Path] = None,
    timeout: int = 120,
    runner: Optional[Callable[..., subprocess.CompletedProcess]] = None,
    input_text: Optional[str] = None,
) -> subprocess.CompletedProcess:
    runner = runner or subprocess.run
    return runner(
        list(cmd),
        cwd=str(cwd) if cwd else None,
        input=input_text,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def _probe_codex_command(runner: Optional[Callable[..., subprocess.CompletedProcess]] = None) -> Dict[str, Any]:
    resolved = shutil.which("codex")
    if not resolved:
        return {"available": False, "command": "codex", "detail": "command not found"}
    try:
        completed = _run_cmd(["codex", "--version"], timeout=15, runner=runner)
    except Exception as exc:
        return {"available": True, "command": resolved, "detail": str(exc)}
    return {
        "available": completed.returncode == 0,
        "command": resolved,
        "detail": (completed.stdout or completed.stderr or "ok").strip(),
    }


def _validate_primary_model(runner: Optional[Callable[..., subprocess.CompletedProcess]] = None) -> Dict[str, Any]:
    completed = _run_cmd(["codex", "exec", RECOVERY_PROMPT], cwd=PROJECT_ROOT, timeout=180, runner=runner)
    combined = ((completed.stdout or "") + "\n" + (completed.stderr or "")).strip()
    success = completed.returncode == 0 and "OK" in combined.upper()
    detail = combined or f"exit={completed.returncode}"
    status = "ok" if success else _classify_validation_failure(detail)
    return {
        "command": ["codex", "exec", RECOVERY_PROMPT],
        "returncode": completed.returncode,
        "success": success,
        "status": status,
        "detail": _mask_secret(detail),
    }


def _classify_validation_failure(detail: str) -> str:
    lowered = detail.lower()
    if any(token in lowered for token in ["model_not_available", "model_not_found", "provider_unavailable"]):
        return "CONFIG_REPAIR_REQUIRED"
    if any(token in lowered for token in ["401", "403", "expired_token", "invalid_grant", "not_logged_in"]):
        return "HUMAN_REQUIRED"
    if any(token in lowered for token in ["timeout", "no response", "gateway", "connection refused"]):
        return "FALLBACK_ACTIVE"
    return "FALLBACK_ACTIVE"


def _refresh_codex_credentials() -> Tuple[bool, Dict[str, Any], List[str]]:
    issues: List[str] = []
    try:
        creds = resolve_codex_runtime_credentials(force_refresh=True, refresh_if_expiring=True)
        return True, creds, issues
    except AuthError as exc:
        issues.append(str(exc))
        return False, {}, issues


def _maybe_interactive_login(allow_interactive_login: bool) -> Tuple[bool, Dict[str, Any], List[str]]:
    if not allow_interactive_login:
        return False, {}, ["interactive_login_disabled"]
    try:
        creds = _codex_device_code_login()
        _save_codex_tokens(creds["tokens"], creds.get("last_refresh"))
        _update_config_for_provider("openai-codex", creds.get("base_url", DEFAULT_CODEX_BASE_URL))
        return True, creds, []
    except Exception as exc:
        return False, {}, [str(exc)]


def _service_restart(service_name: str, runner: Optional[Callable[..., subprocess.CompletedProcess]] = None) -> Dict[str, Any]:
    result: Dict[str, Any] = {"requested": True, "service_name": service_name, "restarted": False, "method": "none", "detail": ""}
    runner = runner or subprocess.run
    if not service_name:
        result["detail"] = "service name not configured"
        return result

    systemctl = shutil.which("systemctl")
    if systemctl:
        completed = _run_cmd(["systemctl", "--user", "restart", service_name], timeout=60, runner=runner)
        result["method"] = "systemd"
        result["detail"] = _mask_secret((completed.stdout or completed.stderr or "").strip())
        result["restarted"] = completed.returncode == 0
        if result["restarted"]:
            return result

    if shutil.which("docker") and (PROJECT_ROOT / "docker-compose.yml").exists():
        completed = _run_cmd(["docker", "compose", "restart", service_name], cwd=PROJECT_ROOT, timeout=120, runner=runner)
        result["method"] = "docker-compose"
        result["detail"] = _mask_secret((completed.stdout or completed.stderr or "").strip())
        result["restarted"] = completed.returncode == 0
        return result

    result["detail"] = "no supported restart path found"
    return result


def collect_recovery_report(
    *,
    allow_interactive_login: bool = False,
    restart_service: bool = False,
    service_name: str = "hermes-agent",
    command_runner: Optional[Callable[..., subprocess.CompletedProcess]] = None,
    auth_status_fn: Optional[Callable[[], Dict[str, Any]]] = None,
    config_loader: Optional[Callable[[], Dict[str, Any]]] = None,
) -> RecoveryReport:
    command_runner = command_runner or subprocess.run
    auth_status_fn = auth_status_fn or get_codex_auth_status
    config_loader = config_loader or load_config

    hermes_home = get_hermes_home()
    config = _load_config_safe(config_loader)
    model_label = _config_model_label(config)

    environment = {
        "project_root": str(PROJECT_ROOT),
        "hermes_home": str(hermes_home),
        "env_file": str(get_env_path()),
        "config_file": str(get_config_path()),
        "python": sys.version.split()[0],
        "python_executable": sys.executable,
        "codex_present": bool(shutil.which("codex")),
    }

    auth_before = auth_status_fn()
    actions: List[str] = ["inspect_auth_status"]
    issues: List[str] = []
    auth_after = dict(auth_before)
    validation: Dict[str, Any] = {"attempted": False, "prompt": RECOVERY_PROMPT}
    service: Dict[str, Any] = {"requested": restart_service, "service_name": service_name, "restarted": False, "method": "none"}

    codex_probe = _probe_codex_command(command_runner)
    if not codex_probe.get("available"):
        issues.append("codex_cli_missing")
        return RecoveryReport(
            tool=SCRIPT_NAME,
            contract_version=CONTRACT_VERSION,
            phase="recover",
            status="PHASE2_BLOCKED",
            recommendation="Codex CLI is missing or unavailable; recovery cannot continue.",
            issues=issues,
            next_step="Install Codex CLI and rerun recovery.",
            environment=environment,
            auth_before=auth_before,
            auth_after=auth_after,
            validation=validation,
            service=service,
            config={"configured_model": model_label, "config_keys": sorted(config.keys())},
            standard_source="estrategia_rearme_modelo_ia_hermes.txt",
            actions=actions,
        )

    actions.append("refresh_codex_credentials")
    refreshed_ok, refreshed_creds, refresh_issues = _refresh_codex_credentials()
    if refreshed_ok:
        auth_after = {
            **auth_after,
            "logged_in": True,
            "source": refreshed_creds.get("source", auth_after.get("source")),
            "last_refresh": refreshed_creds.get("last_refresh", auth_after.get("last_refresh")),
            "auth_mode": refreshed_creds.get("auth_mode", auth_after.get("auth_mode")),
        }
    else:
        issues.extend(refresh_issues)
        actions.append("refresh_failed")
        if "codex_auth_missing" in " ".join(refresh_issues).lower() or not auth_before.get("logged_in"):
            actions.append("interactive_login_check")
            interactive_ok, interactive_creds, interactive_issues = _maybe_interactive_login(allow_interactive_login)
            if interactive_ok:
                auth_after = {
                    **auth_after,
                    "logged_in": True,
                    "source": interactive_creds.get("source", auth_after.get("source")),
                    "last_refresh": interactive_creds.get("last_refresh", auth_after.get("last_refresh")),
                    "auth_mode": interactive_creds.get("auth_mode", auth_after.get("auth_mode")),
                }
                actions.append("interactive_login_success")
            else:
                issues.extend(interactive_issues)
                return RecoveryReport(
                    tool=SCRIPT_NAME,
                    contract_version=CONTRACT_VERSION,
                    phase="recover",
                    status="HUMAN_REQUIRED",
                    recommendation="Codex credentials need a legitimate interactive login path before recovery can continue.",
                    issues=issues,
                    next_step="Run the interactive login flow with browser assistance, then rerun recovery.",
                    environment=environment,
                    auth_before=auth_before,
                    auth_after=auth_after,
                    validation=validation,
                    service=service,
                    config={"configured_model": model_label, "config_keys": sorted(config.keys())},
                    standard_source="estrategia_rearme_modelo_ia_hermes.txt",
                    actions=actions,
                )

    actions.append("validate_primary_model")
    validation = _validate_primary_model(command_runner)
    if not validation["success"]:
        status = validation["status"]
        recommendation = {
            "CONFIG_REPAIR_REQUIRED": "The configured model/provider looks wrong; adjust config and rerun.",
            "HUMAN_REQUIRED": "The auth path still needs human intervention.",
            "FALLBACK_ACTIVE": "Primary call failed; keep fallback active and retry later.",
        }.get(status, "Primary validation failed; keep fallback active.")
        return RecoveryReport(
            tool=SCRIPT_NAME,
            contract_version=CONTRACT_VERSION,
            phase="recover",
            status=status,
            recommendation=recommendation,
            issues=issues + [validation["detail"]],
            next_step="Fix the issue or keep fallback active, then rerun recovery.",
            environment=environment,
            auth_before=auth_before,
            auth_after=auth_after,
            validation=validation,
            service=service,
            config={"configured_model": model_label, "config_keys": sorted(config.keys())},
            standard_source="estrategia_rearme_modelo_ia_hermes.txt",
            actions=actions,
        )

    if restart_service:
        actions.append("restart_service")
        service = _service_restart(service_name, command_runner)
        if not service.get("restarted"):
            issues.append(service.get("detail") or "service_restart_failed")

    status = "PRIMARY_RESTORED"
    recommendation = "Primary model answered OK; the non-browser recovery path succeeded."
    next_step = "Hand traffic back to the primary model and keep the fallback as standby."
    return RecoveryReport(
        tool=SCRIPT_NAME,
        contract_version=CONTRACT_VERSION,
        phase="recover",
        status=status,
        recommendation=recommendation,
        issues=issues,
        next_step=next_step,
        environment=environment,
        auth_before=auth_before,
        auth_after=auth_after,
        validation=validation,
        service=service,
        config={"configured_model": model_label, "config_keys": sorted(config.keys())},
        standard_source="estrategia_rearme_modelo_ia_hermes.txt",
        actions=actions,
    )


def emit_report(report: RecoveryReport, output_path: Optional[Path] = None, pretty: bool = True) -> str:
    payload = asdict(report)
    text = json.dumps(payload, indent=2 if pretty else None, ensure_ascii=False)
    print(text)
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text + "\n", encoding="utf-8")
    return text


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Hermes model rearme recovery — phase 2")
    parser.add_argument("--json-output", default="", help="Optional path for the JSON report")
    parser.add_argument("--compact", action="store_true", help="Emit minified JSON")
    parser.add_argument("--allow-interactive-login", action="store_true", help="Allow the device-code login helper if auth is missing")
    parser.add_argument("--restart-service", action="store_true", help="Restart the Hermes service after a successful validation")
    parser.add_argument("--service-name", default="hermes-agent", help="Systemd/Docker service name to restart when enabled")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_path = Path(args.json_output).expanduser() if args.json_output else None
    report = collect_recovery_report(
        allow_interactive_login=args.allow_interactive_login,
        restart_service=args.restart_service,
        service_name=args.service_name,
    )
    emit_report(report, output_path=output_path, pretty=not args.compact)
    exit_map = {
        "PRIMARY_RESTORED": 0,
        "PHASE2_BLOCKED": 2,
        "HUMAN_REQUIRED": 20,
        "CONFIG_REPAIR_REQUIRED": 30,
        "FALLBACK_ACTIVE": 10,
    }
    return exit_map.get(report.status, 1)


if __name__ == "__main__":
    raise SystemExit(main())
