#!/usr/bin/env python3
"""Deterministic Playwright runner for Hermes workflows.

Contract:
- input: JSON file with run_id, target_url, browser, headless, stop_on_error,
  capture_screenshots, output_dir, steps[]
- step actions: goto, click, type, wait_visible, assert_text, screenshot
- output: JSON report with normalized status, step results, evidence paths

This runner is intentionally generic so it can be reused by recovery flows,
UI workflows, and future browser-assisted handoffs.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

DEFAULT_TIMEOUT_MS = 10_000
DEFAULT_BROWSER = "chromium"
NORMALIZED_ERRORS = {
    "INVALID_INPUT",
    "NAVIGATION_FAILED",
    "ELEMENT_NOT_FOUND",
    "ACTION_TIMEOUT",
    "ASSERTION_FAILED",
    "ACTION_FAILED",
    "SCREENSHOT_FAILED",
    "INTERNAL_ERROR",
}


@dataclass
class StepResult:
    index: int
    action: str
    status: str
    duration_ms: int
    error_code: str = ""
    error_detail: str = ""
    evidence: Dict[str, Any] = None

    def __post_init__(self) -> None:
        if self.evidence is None:
            self.evidence = {}


@dataclass
class RunReport:
    run_id: str
    status: str
    browser: str
    headless: bool
    target_url: str
    final_url: str
    steps_ok: int
    steps_error: int
    step_results: List[Dict[str, Any]]
    evidence: Dict[str, Any]
    started_at: float
    finished_at: float


def _load_input(path: Path) -> Dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Input JSON must be an object")
    return data


def _normalize_error_code(code: str) -> str:
    if code in NORMALIZED_ERRORS:
        return code
    return "INTERNAL_ERROR"


def _error_result(index: int, action: str, code: str, detail: str, duration_ms: int) -> StepResult:
    return StepResult(
        index=index,
        action=action,
        status="error",
        duration_ms=duration_ms,
        error_code=_normalize_error_code(code),
        error_detail=detail,
        evidence={},
    )


def _resolve_url(target_url: str) -> str:
    if not target_url:
        raise ValueError("target_url is required")
    parsed = urlparse(target_url)
    if parsed.scheme in {"http", "https", "file", "data"}:
        return target_url
    if target_url.startswith("/"):
        return f"file://{target_url}"
    # tolerate plain local paths
    return Path(target_url).expanduser().resolve().as_uri()


def _get_timeout_ms(step: Dict[str, Any], default: int = DEFAULT_TIMEOUT_MS) -> int:
    raw = step.get("timeout_ms", default)
    try:
        return max(1, int(raw))
    except Exception:
        return default


def _ensure_selector(step: Dict[str, Any]) -> str:
    selector = step.get("selector", "")
    if not isinstance(selector, str) or not selector.strip():
        raise ValueError("selector is required")
    return selector.strip()


def _ensure_text(step: Dict[str, Any]) -> str:
    text = step.get("text", "")
    if not isinstance(text, str):
        raise ValueError("text must be a string")
    return text


def _serialize_error(exc: Exception) -> str:
    return re.sub(r"\s+", " ", str(exc)).strip() or exc.__class__.__name__


def run_contract(input_data: Dict[str, Any]) -> RunReport:
    run_id = str(input_data.get("run_id") or "hermes-playwright-run")
    target_url = _resolve_url(str(input_data.get("target_url") or ""))
    browser = str(input_data.get("browser") or DEFAULT_BROWSER)
    headless = bool(input_data.get("headless", True))
    stop_on_error = bool(input_data.get("stop_on_error", True))
    capture_screenshots = bool(input_data.get("capture_screenshots", True))
    output_dir = Path(input_data.get("output_dir") or ".").expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir = output_dir / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    output_screenshot_dir = evidence_dir / "screenshots"
    output_screenshot_dir.mkdir(parents=True, exist_ok=True)

    steps = input_data.get("steps", [])
    if not isinstance(steps, list):
        raise ValueError("steps must be a list")

    started_at = time.time()
    step_results: List[StepResult] = []
    evidence: Dict[str, Any] = {"output_dir": str(output_dir), "evidence_dir": str(evidence_dir)}
    steps_ok = 0
    steps_error = 0
    final_url = target_url
    status = "ok"

    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise RuntimeError(f"Playwright import failed: {_serialize_error(exc)}") from exc

    if browser != "chromium":
        raise ValueError("Only chromium is supported for deterministic runs")

    with sync_playwright() as p:
        launch_kwargs = {
            "headless": headless,
        }
        browser_obj = p.chromium.launch(**launch_kwargs)
        page = browser_obj.new_page(viewport={"width": 1280, "height": 900})
        page.goto(target_url, wait_until="domcontentloaded")
        final_url = page.url

        for idx, raw_step in enumerate(steps):
            step_started = time.time()
            if not isinstance(raw_step, dict):
                result = _error_result(idx, "<invalid>", "INVALID_INPUT", "step must be an object", int((time.time() - step_started) * 1000))
                step_results.append(result)
                steps_error += 1
                status = "error"
                if stop_on_error:
                    break
                continue

            action = str(raw_step.get("action") or "").strip()
            result_evidence: Dict[str, Any] = {}
            try:
                if action == "goto":
                    url = str(raw_step.get("url") or target_url)
                    if not url:
                        raise ValueError("url is required")
                    page.goto(_resolve_url(url), wait_until="domcontentloaded", timeout=_get_timeout_ms(raw_step))
                    final_url = page.url
                elif action == "click":
                    selector = _ensure_selector(raw_step)
                    page.locator(selector).first.click(timeout=_get_timeout_ms(raw_step))
                elif action == "type":
                    selector = _ensure_selector(raw_step)
                    text = _ensure_text(raw_step)
                    locator = page.locator(selector).first
                    if raw_step.get("clear", True):
                        locator.fill(text, timeout=_get_timeout_ms(raw_step))
                    else:
                        locator.type(text, timeout=_get_timeout_ms(raw_step))
                elif action == "wait_visible":
                    selector = _ensure_selector(raw_step)
                    page.locator(selector).first.wait_for(state="visible", timeout=_get_timeout_ms(raw_step))
                elif action == "assert_text":
                    selector = _ensure_selector(raw_step)
                    expected = _ensure_text(raw_step)
                    mode = str(raw_step.get("mode") or "contains").lower()
                    text = page.locator(selector).first.inner_text(timeout=_get_timeout_ms(raw_step))
                    if mode == "equals":
                        if text.strip() != expected:
                            raise AssertionError(f"expected exact text {expected!r} but got {text!r}")
                    else:
                        if expected not in text:
                            raise AssertionError(f"expected substring {expected!r} but got {text!r}")
                elif action == "screenshot":
                    name = str(raw_step.get("path") or f"step-{idx + 1:02d}.png")
                    out_path = Path(name)
                    if not out_path.is_absolute():
                        out_path = output_screenshot_dir / out_path.name
                    page.screenshot(path=str(out_path), full_page=bool(raw_step.get("full_page", True)))
                    result_evidence["screenshot_path"] = str(out_path)
                else:
                    raise ValueError(f"unsupported action: {action}")

                if capture_screenshots and action != "screenshot":
                    shot_path = output_screenshot_dir / f"step-{idx + 1:02d}-{action}.png"
                    page.screenshot(path=str(shot_path), full_page=True)
                    result_evidence["screenshot_path"] = str(shot_path)

                duration_ms = int((time.time() - step_started) * 1000)
                step_results.append(
                    StepResult(
                        index=idx,
                        action=action,
                        status="ok",
                        duration_ms=duration_ms,
                        evidence=result_evidence,
                    )
                )
                steps_ok += 1
                final_url = page.url
            except PlaywrightTimeoutError as exc:
                duration_ms = int((time.time() - step_started) * 1000)
                step_results.append(_error_result(idx, action, "ACTION_TIMEOUT", _serialize_error(exc), duration_ms))
                steps_error += 1
                status = "error"
                if stop_on_error:
                    break
            except AssertionError as exc:
                duration_ms = int((time.time() - step_started) * 1000)
                step_results.append(_error_result(idx, action, "ASSERTION_FAILED", _serialize_error(exc), duration_ms))
                steps_error += 1
                status = "error"
                if stop_on_error:
                    break
            except ValueError as exc:
                duration_ms = int((time.time() - step_started) * 1000)
                code = "INVALID_INPUT" if "unsupported action" not in str(exc).lower() else "ACTION_FAILED"
                step_results.append(_error_result(idx, action or "<invalid>", code, _serialize_error(exc), duration_ms))
                steps_error += 1
                status = "error"
                if stop_on_error:
                    break
            except Exception as exc:
                duration_ms = int((time.time() - step_started) * 1000)
                step_results.append(_error_result(idx, action or "<unknown>", "INTERNAL_ERROR", _serialize_error(exc), duration_ms))
                steps_error += 1
                status = "error"
                if stop_on_error:
                    break

        browser_obj.close()

    finished_at = time.time()
    if steps_error == 0:
        status = "ok"
    elif status != "error":
        status = "error"

    evidence["screenshot_dir"] = str(output_screenshot_dir)
    evidence["capture_screenshots"] = capture_screenshots
    evidence["stop_on_error"] = stop_on_error

    return RunReport(
        run_id=run_id,
        status=status,
        browser=browser,
        headless=headless,
        target_url=target_url,
        final_url=final_url,
        steps_ok=steps_ok,
        steps_error=steps_error,
        step_results=[asdict(item) for item in step_results],
        evidence=evidence,
        started_at=started_at,
        finished_at=finished_at,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Hermes deterministic Playwright runner")
    parser.add_argument("--input", required=True, help="Path to JSON contract input")
    parser.add_argument("--output", required=True, help="Path for JSON result output")
    parser.add_argument("--compact", action="store_true", help="Emit compact JSON")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input).expanduser()
    output_path = Path(args.output).expanduser()
    input_data = _load_input(input_path)
    report = run_contract(input_data)
    payload = asdict(report)
    text = json.dumps(payload, ensure_ascii=False, indent=None if args.compact else 2)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report.status == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
