"""Prosody shaping tests for the voice orchestrator."""

import json


def test_voice_orchestrator_adds_clause_pauses():
    from tools.voice_orchestrator import compose_voice_prompt

    packet = compose_voice_prompt(
        "Esto es una explicación larga porque conviene separar la idea y además darle pausa antes de seguir con la siguiente parte.",
        voice_profile={"pause_density": 0.7, "allow_breaths": True},
    )

    assert "\n" in packet["speech_text"] or "," in packet["speech_text"]
    assert packet["speech_text"] != packet["display_text"]
    assert isinstance(packet["speech_events"], list)
    assert any(event["type"] in {"pause", "breath"} for event in packet["speech_events"])


def test_voice_orchestrator_dry_run_exposes_speech_plan():
    from tools.voice_orchestrator import orchestrate_voice

    result = json.loads(
        orchestrate_voice(
            text="Primero analizamos el problema y luego decidimos el siguiente paso.",
            dry_run=True,
        )
    )

    assert result["status"] == "ok"
    assert result["mode"] == "dry_run"
    assert "speech_plan" in result
    assert result["final_text"]


def test_voice_orchestrator_detects_emphasis_terms():
    from tools.voice_orchestrator import compose_voice_prompt

    packet = compose_voice_prompt(
        'Lo importante es **ahora** y no después, porque "claridad" marca el ritmo.',
        voice_profile={"pause_density": 0.6},
    )

    assert "ahora" in [term.lower() for term in packet["speech_plan"]["emphasis_terms"]]
    assert any(event["type"] == "emphasis" for event in packet["speech_events"])
    assert "," in packet["speech_text"]
