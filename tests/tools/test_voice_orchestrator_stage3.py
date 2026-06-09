"""Stage 3 tests for the voice orchestrator mode detector."""


def test_stage3_detects_reflective_mode_from_emotional_softening_phrase():
    from tools.voice_orchestrator import VoiceStage3ModeDetector

    stage3 = VoiceStage3ModeDetector()
    result = stage3.execute(
        text="Mira…, no es que esté enfadada, es que, sinceramente, después de todo lo que ha pasado, me sorprende que todavía sigas preguntando lo mismo…",
        context={"interaction_route": "analysis"},
        stage1={"route": "analysis", "route_reason": "context_explicit_route"},
        stage2={"summary": "interaction_route=analysis"},
    )

    assert result["stage"] == "stage_3_mode_detector"
    assert result["mode"] == "reflective"
    assert result["tone"] == "reflective"
    assert result["mode_reason"] == "reflective_markers"
    assert result["voice_profile_patch"]["speed"] < 0.93
    assert result["style_profile_patch"]["depth"] >= 0.8


def test_stage3_detects_execution_mode_for_direct_action_language():
    from tools.voice_orchestrator import VoiceStage3ModeDetector

    stage3 = VoiceStage3ModeDetector()
    result = stage3.execute(
        text="Hazlo ahora y cierra el ticket.",
        context={"interaction_route": "execution"},
        stage1={"route": "execution", "route_reason": "context_explicit_route"},
        stage2={"summary": "interaction_route=execution"},
    )

    assert result["mode"] == "executive"
    assert result["tone"] == "executive"
    assert result["mode_reason"] == "explicit_execution_route"
    assert result["voice_profile_patch"]["speed"] >= 1.0
    assert result["style_profile_patch"]["stance"] == "decisive"
