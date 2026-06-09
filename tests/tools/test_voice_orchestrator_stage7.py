"""Stage 7 tests for the voice orchestrator fine prosody layer."""


def test_stage7_refines_reflective_phrase_with_clause_level_cadence():
    from tools.voice_orchestrator import VoiceStage7FineProsody

    stage7 = VoiceStage7FineProsody()
    text = "Mira…, no es que esté enfadada, es que, sinceramente, después de todo lo que ha pasado, me sorprende que todavía sigas preguntando lo mismo…"
    result = stage7.execute(
        text=text,
        context={"interaction_route": "analysis"},
        stage1={"route": "analysis", "route_reason": "context_explicit_route"},
        stage2={"summary": "interaction_route=analysis"},
        stage3={"mode": "reflective"},
        stage4={"sanitized_display_text": text, "speech_text": text},
        stage5={
            "mode": "reflective",
            "speech_script": {
                "segments": [
                    "Mira…",
                    "no es que esté enfadada",
                    "es que",
                    "sinceramente",
                    "después de todo lo que ha pasado",
                    "me sorprende que todavía sigas preguntando lo mismo…",
                ],
                "segment_count": 6,
            },
            "speech_plan": {"opening_style": "reflective"},
            "render_text": "Mira…\n\nno es que esté enfadada\n\nes que\n\nsinceramente\n\ndespués de todo lo que ha pasado\n\nme sorprende que todavía sigas preguntando lo mismo…",
        },
    )

    assert result["stage"] == "stage_7_fine_prosody"
    assert result["mode"] == "reflective"
    assert result["render_text"].count("\n\n") >= 3
    assert ",\n\n" in result["render_text"] or ",\n" in result["render_text"]
    assert result["prosody_profile_patch"]["speed"] >= 0.9
    assert result["prosody_profile_patch"]["pause_density"] >= 0.8
    assert result["prosody_map"]["clause_count"] >= 4


def test_stage7_keeps_execution_text_direct_but_with_short_pauses():
    from tools.voice_orchestrator import VoiceStage7FineProsody

    stage7 = VoiceStage7FineProsody()
    result = stage7.execute(
        text="Hazlo ahora y cierra el ticket.",
        context={"interaction_route": "execution"},
        stage1={"route": "execution", "route_reason": "context_explicit_route"},
        stage2={"summary": "interaction_route=execution"},
        stage3={"mode": "executive"},
        stage4={"sanitized_display_text": "Hazlo ahora y cierra el ticket.", "speech_text": "Hazlo ahora y cierra el ticket."},
        stage5={
            "mode": "executive",
            "speech_script": {"segments": ["Hazlo ahora", "cierra el ticket."], "segment_count": 2},
            "speech_plan": {"opening_style": "direct"},
            "render_text": "Hazlo ahora\ncierra el ticket.",
        },
    )

    assert result["mode"] == "executive"
    assert result["prosody_profile_patch"]["speed"] >= 1.0
    assert result["prosody_profile_patch"]["pause_density"] <= 0.75
    assert result["prosody_map"]["cadence"] == "direct"
