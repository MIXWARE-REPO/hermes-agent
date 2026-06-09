"""Stage 4 tests for the voice orchestrator semantic sanitizer."""


def test_stage4_detects_and_summarizes_technical_noise_without_leaking_it():
    from tools.voice_orchestrator import VoiceStage4SemanticSanitizer

    stage4 = VoiceStage4SemanticSanitizer()
    result = stage4.execute(
        text="Visita https://example.com y revisa POST /api/auth/login con {\"token\":\"abc\"}.",
        context={"interaction_route": "analysis"},
        stage1={"route": "analysis", "route_reason": "context_explicit_route"},
        stage2={"summary": "interaction_route=analysis"},
        stage3={"mode": "analytical"},
    )

    assert result["stage"] == "stage_4_semantic_sanitizer"
    assert result["technical_items"]
    assert result["sanitized_display_text"] == "Visita el sitio y revisa el login con un token."
    assert result["speech_text"] == "Visita el sitio y revisa el login con un token."
    assert result["semantic_policy"]["summarize_technical_items"] is True
    assert result["rendering_hints"]["do_not_read_technical_items_verbatim"] is True


def test_stage4_keeps_emotional_reference_phrase_stable_when_no_technical_noise_exists():
    from tools.voice_orchestrator import VoiceStage4SemanticSanitizer

    stage4 = VoiceStage4SemanticSanitizer()
    text = "Mira…, no es que esté enfadada, es que, sinceramente, después de todo lo que ha pasado, me sorprende que todavía sigas preguntando lo mismo…"
    result = stage4.execute(
        text=text,
        context={"interaction_route": "analysis"},
        stage1={"route": "analysis", "route_reason": "context_explicit_route"},
        stage2={"summary": "interaction_route=analysis"},
        stage3={"mode": "reflective"},
    )

    assert result["sanitized_display_text"] == text
    assert result["speech_text"] == text
    assert result["technical_items"] == []
    assert result["semantic_policy"]["preserve_emotional_phrase"] is True
