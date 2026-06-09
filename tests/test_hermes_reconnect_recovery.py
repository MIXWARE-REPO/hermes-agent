from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace


class DummyCompletedProcess:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def load_recovery_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "hermes_reconnect_recovery.py"
    spec = importlib.util.spec_from_file_location("hermes_reconnect_recovery", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    import sys
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_collect_recovery_report_succeeds_on_refresh_and_validation(monkeypatch, tmp_path):
    recovery = load_recovery_module()

    project_root = tmp_path / "project"
    hermes_home = tmp_path / ".hermes"
    project_root.mkdir()
    hermes_home.mkdir()
    (hermes_home / "config.yaml").write_text("model: gpt-5.4-mini\n", encoding="utf-8")

    monkeypatch.setattr(recovery, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(recovery, "get_hermes_home", lambda: hermes_home)
    monkeypatch.setattr(recovery, "get_env_path", lambda: hermes_home / ".env")
    monkeypatch.setattr(recovery, "get_config_path", lambda: hermes_home / "config.yaml")
    monkeypatch.setattr(recovery, "shutil", SimpleNamespace(which=lambda cmd: f"/usr/bin/{cmd}" if cmd == "codex" else None))
    monkeypatch.setattr(
        recovery,
        "load_config",
        lambda: {"model": "gpt-5.4-mini"},
    )
    monkeypatch.setattr(
        recovery,
        "get_codex_auth_status",
        lambda: {"logged_in": True, "last_refresh": "2026-06-06T09:00:00Z", "source": "hermes-auth-store"},
    )
    monkeypatch.setattr(
        recovery,
        "resolve_codex_runtime_credentials",
        lambda **kwargs: {"source": "hermes-auth-store", "last_refresh": "2026-06-06T10:00:00Z", "auth_mode": "chatgpt"},
    )
    monkeypatch.setattr(
        recovery,
        "_run_cmd",
        lambda cmd, **kwargs: DummyCompletedProcess(stdout="OK" if cmd[:2] == ["codex", "exec"] else "codex-cli 0.136.0"),
    )

    report = recovery.collect_recovery_report()

    assert report.status == "PRIMARY_RESTORED"
    assert report.validation["success"] is True
    assert report.auth_after["logged_in"] is True
    assert "validate_primary_model" in report.actions


def test_collect_recovery_report_returns_human_required_when_refresh_needs_login(monkeypatch, tmp_path):
    recovery = load_recovery_module()

    project_root = tmp_path / "project"
    hermes_home = tmp_path / ".hermes"
    project_root.mkdir()
    hermes_home.mkdir()

    monkeypatch.setattr(recovery, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(recovery, "get_hermes_home", lambda: hermes_home)
    monkeypatch.setattr(recovery, "get_env_path", lambda: hermes_home / ".env")
    monkeypatch.setattr(recovery, "get_config_path", lambda: hermes_home / "config.yaml")
    monkeypatch.setattr(recovery, "shutil", SimpleNamespace(which=lambda cmd: f"/usr/bin/{cmd}" if cmd == "codex" else None))
    monkeypatch.setattr(recovery, "load_config", lambda: {})
    monkeypatch.setattr(recovery, "get_codex_auth_status", lambda: {"logged_in": False, "error": "missing"})
    monkeypatch.setattr(
        recovery,
        "resolve_codex_runtime_credentials",
        lambda **kwargs: (_ for _ in ()).throw(recovery.AuthError("missing", provider="openai-codex", code="codex_auth_missing", relogin_required=True)),
    )

    report = recovery.collect_recovery_report(allow_interactive_login=False)

    assert report.status == "HUMAN_REQUIRED"
    assert "interactive_login_disabled" in report.issues
    assert report.validation["attempted"] is False or report.validation["attempted"] == False


def test_collect_recovery_report_classifies_model_errors(monkeypatch, tmp_path):
    recovery = load_recovery_module()

    project_root = tmp_path / "project"
    hermes_home = tmp_path / ".hermes"
    project_root.mkdir()
    hermes_home.mkdir()
    (hermes_home / "config.yaml").write_text("model: gpt-5.4-mini\n", encoding="utf-8")

    monkeypatch.setattr(recovery, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(recovery, "get_hermes_home", lambda: hermes_home)
    monkeypatch.setattr(recovery, "get_env_path", lambda: hermes_home / ".env")
    monkeypatch.setattr(recovery, "get_config_path", lambda: hermes_home / "config.yaml")
    monkeypatch.setattr(recovery, "shutil", SimpleNamespace(which=lambda cmd: f"/usr/bin/{cmd}" if cmd == "codex" else None))
    monkeypatch.setattr(recovery, "load_config", lambda: {"model": "gpt-5.4-mini"})
    monkeypatch.setattr(recovery, "get_codex_auth_status", lambda: {"logged_in": True})
    monkeypatch.setattr(recovery, "resolve_codex_runtime_credentials", lambda **kwargs: {"source": "hermes-auth-store"})
    def fake_run(cmd, **kwargs):
        if cmd[:2] == ["codex", "--version"]:
            return DummyCompletedProcess(returncode=0, stdout="codex-cli 0.136.0")
        if cmd[:2] == ["codex", "exec"]:
            return DummyCompletedProcess(returncode=1, stdout="", stderr="model_not_available: provider down")
        return DummyCompletedProcess(returncode=0, stdout="ok")

    monkeypatch.setattr(recovery, "_run_cmd", fake_run)

    report = recovery.collect_recovery_report()

    assert report.status == "CONFIG_REPAIR_REQUIRED"
    assert report.validation["status"] == "CONFIG_REPAIR_REQUIRED"
    assert report.validation["success"] is False


def test_emit_report_writes_json_file(monkeypatch, tmp_path):
    recovery = load_recovery_module()

    report = recovery.RecoveryReport(
        tool="hermes_reconnect_recovery",
        contract_version="2.0",
        phase="recover",
        status="PRIMARY_RESTORED",
        recommendation="ok",
        issues=[],
        next_step="handoff",
        environment={"project_root": "/tmp/project"},
        auth_before={"logged_in": True},
        auth_after={"logged_in": True},
        validation={"success": True},
        service={"requested": False, "service_name": "hermes-agent", "restarted": False, "method": "none"},
        config={"configured_model": "gpt-5.4-mini"},
        standard_source="estrategia_rearme_modelo_ia_hermes.txt",
        actions=["inspect_auth_status"],
    )

    out = tmp_path / "report.json"
    text = recovery.emit_report(report, output_path=out, pretty=True)

    assert out.exists()
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["status"] == "PRIMARY_RESTORED"
    assert json.loads(text)["contract_version"] == "2.0"
