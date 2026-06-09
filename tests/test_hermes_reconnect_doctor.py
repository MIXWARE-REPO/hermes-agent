from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace


def load_doctor_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "hermes_reconnect_doctor.py"
    spec = importlib.util.spec_from_file_location("hermes_reconnect_doctor", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    import sys
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class DummyCompletedProcess:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_collect_report_marks_ready_when_all_core_signals_exist(monkeypatch, tmp_path):
    doctor = load_doctor_module()

    project_root = tmp_path / "project"
    hermes_home = tmp_path / ".hermes"
    project_root.mkdir()
    hermes_home.mkdir()
    (hermes_home / "config.yaml").write_text("model: gpt-5.4-mini\n", encoding="utf-8")
    (hermes_home / ".env").write_text("OPENAI_API_KEY=abc\n", encoding="utf-8")

    monkeypatch.setattr(doctor, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(doctor, "get_hermes_home", lambda: hermes_home)
    monkeypatch.setattr(doctor, "get_env_path", lambda: hermes_home / ".env")
    monkeypatch.setattr(doctor, "get_config_path", lambda: hermes_home / "config.yaml")
    monkeypatch.setattr(doctor, "shutil", SimpleNamespace(which=lambda cmd: f"/usr/bin/{cmd}" if cmd == "codex" else None))
    monkeypatch.setattr(doctor, "importlib", SimpleNamespace(util=SimpleNamespace(find_spec=lambda name: object() if name == "playwright" else None)))
    monkeypatch.setattr(doctor, "subprocess", SimpleNamespace(run=lambda *a, **kw: DummyCompletedProcess(stdout="1.60.0")))
    monkeypatch.setattr(doctor, "get_codex_auth_status", lambda: {"logged_in": True, "last_refresh": "2026-06-06T09:00:00Z"})
    monkeypatch.setattr(doctor, "load_config", lambda: {"model": "gpt-5.4-mini"})

    report = doctor.collect_report()

    assert report.status == "PHASE1_OK"
    assert report.probes["codex_auth"]["logged_in"] is True
    assert report.probes["codex_cli"]["available"] is True
    assert report.probes["playwright"]["available"] is True
    assert report.config["configured_model"] == "gpt-5.4-mini"
    assert report.standard_source == "estrategia_rearme_modelo_ia_hermes.txt"


def test_collect_report_blocks_when_codex_cli_and_auth_missing(monkeypatch, tmp_path):
    doctor = load_doctor_module()

    project_root = tmp_path / "project"
    hermes_home = tmp_path / ".hermes"
    project_root.mkdir()
    hermes_home.mkdir()

    monkeypatch.setattr(doctor, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(doctor, "get_hermes_home", lambda: hermes_home)
    monkeypatch.setattr(doctor, "get_env_path", lambda: hermes_home / ".env")
    monkeypatch.setattr(doctor, "get_config_path", lambda: hermes_home / "config.yaml")
    monkeypatch.setattr(doctor, "shutil", SimpleNamespace(which=lambda cmd: None))
    monkeypatch.setattr(doctor, "importlib", SimpleNamespace(util=SimpleNamespace(find_spec=lambda name: None)))
    monkeypatch.setattr(doctor, "subprocess", SimpleNamespace(run=lambda *a, **kw: DummyCompletedProcess(stdout="")))
    monkeypatch.setattr(doctor, "get_codex_auth_status", lambda: {"logged_in": False, "error": "missing"})
    monkeypatch.setattr(doctor, "load_config", lambda: {})

    report = doctor.collect_report()

    assert report.status == "PHASE1_BLOCKED"
    assert "codex_cli_missing" in report.issues
    assert "codex_auth_missing" in report.issues
    assert "playwright_missing" in report.issues


def test_emit_report_writes_json_file(monkeypatch, tmp_path):
    doctor = load_doctor_module()

    report = doctor.Report(
        tool="hermes_reconnect_doctor",
        contract_version="2.0",
        phase="diagnose",
        status="PHASE1_OK",
        recommendation="ready",
        issues=[],
        next_step="continue",
        environment={"project_root": "/tmp/project"},
        config={"configured_model": "gpt-5.4-mini"},
        probes={},
        standard_source="estrategia_rearme_modelo_ia_hermes.txt",
    )

    out = tmp_path / "report.json"
    text = doctor.emit_report(report, output_path=out, pretty=True)

    assert out.exists()
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["status"] == "PHASE1_OK"
    assert json.loads(text)["contract_version"] == "2.0"
