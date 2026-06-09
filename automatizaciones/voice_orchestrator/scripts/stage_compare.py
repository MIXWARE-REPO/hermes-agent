#!/usr/bin/env python3
"""Parallel stage comparison harness for the Voice Orchestrator.

This script runs a small set of representative samples through the current
voice pipeline and compares route/profile variants in parallel so we can see
how the system behaves before and after a change.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from tools.voice_orchestrator import VoiceStage1ChannelGate, compose_voice_prompt, validate_voice_packet


@dataclass
class Sample:
    name: str
    text: str
    context: Dict[str, Any]


SAMPLES: List[Sample] = [
    Sample(
        name="technical_noise",
        text="POST /api/auth/login devuelve 401 cuando el JWT expira.",
        context={"interaction_route": "analysis", "voice_trigger": False},
    ),
    Sample(
        name="reflective_exploration",
        text="Creo que la voz del agente no debería ser solo lectura, sino presencia.",
        context={"interaction_route": "analysis", "voice_trigger": False},
    ),
    Sample(
        name="breath_only",
        text="ssss...",
        context={"interaction_route": "analysis", "voice_trigger": False},
    ),
]


VARIANTS = [
    {
        "name": "base",
        "voice_profile": None,
        "style_profile": None,
        "identity_profile": None,
    },
    {
        "name": "analysis_route",
        "voice_profile": None,
        "style_profile": None,
        "identity_profile": None,
        "context_patch": {"interaction_route": "analysis", "route_reason": "compare_pipeline"},
    },
    {
        "name": "execution_route",
        "voice_profile": None,
        "style_profile": None,
        "identity_profile": None,
        "context_patch": {"interaction_route": "execution", "route_reason": "compare_pipeline"},
    },
]


def run_variant(sample: Sample, variant: Dict[str, Any]) -> Dict[str, Any]:
    context = dict(sample.context)
    context.update(variant.get("context_patch") or {})
    stage1 = VoiceStage1ChannelGate().execute(text=sample.text, audio_path=None, context=context)
    composed = compose_voice_prompt(
        sample.text,
        context={**context, **{"interaction_route": stage1["route"], "route_reason": stage1["route_reason"]}},
        identity_profile=variant.get("identity_profile"),
        voice_profile=variant.get("voice_profile"),
        style_profile=variant.get("style_profile"),
    )
    validated = validate_voice_packet(composed)
    return {
        "sample": sample.name,
        "variant": variant["name"],
        "stage1": stage1,
        "display_text": validated.get("display_text"),
        "speech_text": validated.get("speech_text"),
        "speech_events": validated.get("speech_events", []),
        "voice_reference": validated.get("identity_profile", {}).get("voice_reference"),
        "voice_profile": validated.get("voice_profile", {}),
        "style_profile": validated.get("style_profile", {}),
        "status": validated.get("status"),
        "warnings": validated.get("warnings", []),
        "speech_len": len(validated.get("speech_text") or ""),
        "event_count": len(validated.get("speech_events", [])),
    }


def main() -> None:
    out_dir = Path(__file__).resolve().parent.parent / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)

    rows: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = []
        for sample in SAMPLES:
            for variant in VARIANTS:
                futures.append(executor.submit(run_variant, sample, variant))
        for future in as_completed(futures):
            rows.append(future.result())

    rows.sort(key=lambda x: (x["sample"], x["variant"]))

    report = {
        "samples": [asdict(s) for s in SAMPLES],
        "variants": [v["name"] for v in VARIANTS],
        "results": rows,
    }

    report_path = out_dir / "stage_compare_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({"status": "ok", "report_path": str(report_path), "result_count": len(rows)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
