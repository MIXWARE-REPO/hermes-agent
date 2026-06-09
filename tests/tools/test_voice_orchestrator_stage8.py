"""Stage 8 tests for the voice orchestrator quality validator."""


def test_stage8_accepts_reference_phrase_as_audio_safe_and_high_quality():
    from tools.voice_orchestrator import VoiceStage8QualityValidator

    stage8 = VoiceStage8QualityValidator()
    text = "Mira…, no es que esté enfadada, es que, sinceramente, después de todo lo que ha pasado, me sorprende que todavía sigas preguntando lo mismo…"
    result = stage8.execute(
        text=text,
        context={"interaction_route": "analysis"},
        stage1={"route": "analysis", "route_reason": "context_explicit_route"},
        stage2={"summary": "interaction_route=analysis"},
        stage3={"mode": "reflective"},
        stage4={"sanitized_display_text": text, "speech_text": text},
        stage5={"render_text": "Mira…\n\nno es que esté enfadada\n\nes que\n\nsinceramente\n\ndespués de todo lo que ha pasado\n\nme sorprende que todavía sigas preguntando lo mismo…"},
        stage6={"fusion_policy": {"parallel_channels": True}},
        stage7={"prosody_map": {"reference_phrase_preserved": True, "clause_count": 5}},
    )

    assert result["stage"] == "stage_8_quality_validator"
    assert result["audio_safe"] is True
    assert result["quality_score"] >= 0.9
    assert result["quality_checks"]["reference_phrase_preserved"] is True
    assert result["quality_checks"]["technical_noise_detected"] is False
    assert result["quality_policy"]["allow_audio_delivery"] is True


def test_stage8_flags_technical_noise_and_suggests_text_fallback():
    from tools.voice_orchestrator import VoiceStage8QualityValidator

    stage8 = VoiceStage8QualityValidator()
    result = stage8.execute(
        text="Visita https://example.com y revisa {\"token\":\"abc\"}.",
        context={"interaction_route": "analysis"},
        stage1={"route": "analysis", "route_reason": "context_explicit_route"},
        stage2={"summary": "interaction_route=analysis"},
        stage3={"mode": "analytical"},
        stage4={"sanitized_display_text": "Visita https://example.com y revisa {\"token\":\"abc\"}.", "speech_text": "Visita https://example.com y revisa {\"token\":\"abc\"}."},
        stage5={"render_text": "Visita https://example.com y revisa {\"token\":\"abc\"}."},
        stage6={"fusion_policy": {"parallel_channels": True}},
        stage7={"prosody_map": {"reference_phrase_preserved": False}},
    )

    assert result["audio_safe"] is False
    assert result["quality_checks"]["technical_noise_detected"] is True
    assert result["quality_policy"]["allow_audio_delivery"] is False
    assert "technical_noise_detected" in result["warnings"]
    assert result["fallback_recommendation"] == "text_only"
