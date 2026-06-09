"""Stage 5 tests for the voice orchestrator speech planner."""


def test_stage5_builds_segmented_speech_plan_for_reflective_phrase():
    from tools.voice_orchestrator import VoiceStage5SpeechPlanner

    stage5 = VoiceStage5SpeechPlanner()
    text = "Mira…, no es que esté enfadada, es que, sinceramente, después de todo lo que ha pasado, me sorprende que todavía sigas preguntando lo mismo…"
    result = stage5.execute(
        text=text,
        context={"interaction_route": "analysis"},
        stage1={"route": "analysis", "route_reason": "context_explicit_route"},
        stage2={"summary": "interaction_route=analysis"},
        stage3={"mode": "reflective"},
        stage4={"sanitized_display_text": text, "speech_text": text},
    )

    assert result["stage"] == "stage_5_speech_planner"
    assert result["opening"] == "Mira…"
    assert result["mode"] == "reflective"
    assert result["speech_script"]["segment_count"] >= 3
    assert result["speech_script"]["segments"][0] == "Mira…"
    assert "sinceramente" in result["speech_script"]["segments"]
    assert result["render_text"]
    assert result["speech_plan"]["opening_style"] == "reflective"


def test_stage5_keeps_strong_action_language_short_and_direct():
    from tools.voice_orchestrator import VoiceStage5SpeechPlanner

    stage5 = VoiceStage5SpeechPlanner()
    result = stage5.execute(
        text="Hazlo ahora y cierra el ticket.",
        context={"interaction_route": "execution"},
        stage1={"route": "execution", "route_reason": "context_explicit_route"},
        stage2={"summary": "interaction_route=execution"},
        stage3={"mode": "executive"},
        stage4={"sanitized_display_text": "Hazlo ahora y cierra el ticket.", "speech_text": "Hazlo ahora y cierra el ticket."},
    )

    assert result["mode"] == "executive"
    assert result["speech_plan"]["opening_style"] == "direct"
    assert result["speech_script"]["segment_count"] <= 2
    assert result["render_text"].startswith("Hazlo")
