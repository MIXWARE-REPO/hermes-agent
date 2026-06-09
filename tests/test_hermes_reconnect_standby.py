from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from unittest.mock import patch


def load_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "hermes_reconnect_standby.py"
    spec = importlib.util.spec_from_file_location("hermes_reconnect_standby", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    import sys
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_standby_creates_handoff_when_human_required(tmp_path):
    mod = load_module()

    class Doctor:
        status = "PHASE1_OK"
        recommendation = "ok"
        issues = []
        next_step = "phase 2"
        environment = {}
        config = {}
        probes = {}
        tool = "doctor"
        contract_version = "2.0"
        phase = "diagnose"
        standard_source = "source"

    class Recovery:
        status = "HUMAN_REQUIRED"
        recommendation = "login needed"
        issues = ["token invalid"]
        next_step = "run browser assisted login"
        environment = {}
        auth_before = {}
        auth_after = {}
        validation = {}
        service = {}
        config = {}
        tool = "recovery"
        contract_version = "2.0"
        phase = "recover"
        standard_source = "source"
        actions = ["inspect_auth_status"]

    browser_handoff = Path("/tmp/hermes_reconnect_browser_handoff.json")
    if browser_handoff.exists():
        browser_handoff.unlink()

    with patch.object(mod, "collect_doctor_report", return_value=Doctor()), patch.object(mod, "collect_recovery_report", return_value=Recovery()):
        report = mod.build_standby_report(allow_browser_login=False, restart_service=False, service_name="hermes-agent")

    assert report["ready_for_failure"] is False
    assert report["browser_handoff_path"]
    assert browser_handoff.exists()
    handoff = json.loads(browser_handoff.read_text(encoding="utf-8"))
    assert handoff["status"] == "ready_for_browser_handoff"
    assert "browser-assisted login" in handoff["recommended_action"]


def test_standby_reports_ready_when_restored(tmp_path):
    mod = load_module()

    class Doctor:
        status = "PHASE1_OK"
        recommendation = "ok"
        issues = []
        next_step = "phase 2"
        environment = {}
        config = {}
        probes = {}
        tool = "doctor"
        contract_version = "2.0"
        phase = "diagnose"
        standard_source = "source"

    class Recovery:
        status = "PRIMARY_RESTORED"
        recommendation = "restored"
        issues = []
        next_step = "done"
        environment = {}
        auth_before = {}
        auth_after = {}
        validation = {"success": True}
        service = {"restarted": False}
        config = {}
        tool = "recovery"
        contract_version = "2.0"
        phase = "recover"
        standard_source = "source"
        actions = ["inspect_auth_status", "refresh_codex_credentials", "validate_primary_model"]

    with patch.object(mod, "collect_doctor_report", return_value=Doctor()), patch.object(mod, "collect_recovery_report", return_value=Recovery()):
        report = mod.build_standby_report(allow_browser_login=False, restart_service=False, service_name="hermes-agent")

    assert report["ready_for_failure"] is True
    assert report["browser_handoff"] is None
