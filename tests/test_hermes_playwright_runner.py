from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def load_runner_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "hermes_playwright_runner.py"
    spec = importlib.util.spec_from_file_location("hermes_playwright_runner", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    import sys
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_run_contract_executes_deterministic_browser_flow(tmp_path):
    runner = load_runner_module()

    html = """
    <html>
      <body>
        <h1 id="title">Hermes Ready</h1>
        <input id="name" type="text" />
        <button id="save">Save</button>
        <div id="result">Pending</div>
        <script>
          const name = document.getElementById('name');
          const result = document.getElementById('result');
          document.getElementById('save').addEventListener('click', () => {
            result.textContent = 'Saved: ' + name.value;
          });
        </script>
      </body>
    </html>
    """.strip()
    target_url = "data:text/html," + html.replace("\n", "").replace("  ", "")
    out_dir = tmp_path / "out"

    report = runner.run_contract(
        {
            "run_id": "test-run",
            "target_url": target_url,
            "browser": "chromium",
            "headless": True,
            "capture_screenshots": True,
            "stop_on_error": True,
            "output_dir": str(out_dir),
            "steps": [
                {"action": "wait_visible", "selector": "#title", "timeout_ms": 5000},
                {"action": "type", "selector": "#name", "text": "Laia"},
                {"action": "click", "selector": "#save"},
                {"action": "assert_text", "selector": "#result", "text": "Saved: Laia", "mode": "contains"},
                {"action": "screenshot", "path": "final.png"},
            ],
        }
    )

    assert report.status == "ok"
    assert report.steps_ok == 5
    assert report.steps_error == 0
    assert report.final_url.startswith("data:text/html")
    screenshot_dir = Path(report.evidence["screenshot_dir"])
    assert screenshot_dir.exists()
    assert any(screenshot_dir.glob("*.png"))


def test_run_contract_normalizes_invalid_input(tmp_path):
    runner = load_runner_module()
    out_dir = tmp_path / "out"

    report = runner.run_contract(
        {
            "run_id": "test-run",
            "target_url": "data:text/html,<html><body><h1>OK</h1></body></html>",
            "browser": "chromium",
            "headless": True,
            "capture_screenshots": False,
            "stop_on_error": True,
            "output_dir": str(out_dir),
            "steps": [
                {"action": "bogus"},
            ],
        }
    )

    assert report.status == "error"
    assert report.steps_error == 1
    assert report.step_results[0]["error_code"] in {"INVALID_INPUT", "ACTION_FAILED", "INTERNAL_ERROR"}


def test_emit_json_output_roundtrips(tmp_path):
    runner = load_runner_module()
    input_path = tmp_path / "input.json"
    output_path = tmp_path / "output.json"

    payload = {
        "run_id": "test-run",
        "target_url": "data:text/html,<html><body><h1>OK</h1></body></html>",
        "browser": "chromium",
        "headless": True,
        "capture_screenshots": False,
        "stop_on_error": True,
        "output_dir": str(tmp_path / "out"),
        "steps": [{"action": "wait_visible", "selector": "h1", "timeout_ms": 5000}],
    }
    input_path.write_text(json.dumps(payload), encoding="utf-8")

    report = runner.run_contract(payload)
    output_path.write_text(json.dumps(report.__dict__, default=str), encoding="utf-8")

    assert output_path.exists()
