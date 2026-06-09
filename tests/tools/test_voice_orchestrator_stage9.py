"""Stage 9 tests for the voice orchestrator stage comparator."""


def test_stage9_reports_stable_progression_for_reference_phrase():
    from tools.voice_orchestrator import VoiceStage9StageComparator

    stage9 = VoiceStage9StageComparator()
    text = "Mira…, no es que esté enfadada, es que, sinceramente, después de todo lo que ha pasado, me sorprende que todavía sigas preguntando lo mismo…"
    result = stage9.execute(
        text=text,
        context={"interaction_route": "analysis"},
        stage1={"route": "analysis", "route_reason": "context_explicit_route", "voice_trigger": True},
        stage2={"summary": "interaction_route=analysis", "source_kind": "text"},
        stage3={"mode": "reflective"},
        stage4={"sanitized_display_text": text, "speech_text": text, "technical_items": []},
        stage5={"render_text": "Mira…\n\nno es que esté enfadada\n\nes que\n\nsinceramente\n\ndespués de todo lo que ha pasado\n\nme sorprende que todavía sigas preguntando lo mismo…", "speech_script": {"segment_count": 6}},
        stage6={"fusion_policy": {"parallel_channels": True}, "reactive_channel": {"ack_text": "Entiendo"}},
        stage7={"prosody_map": {"cadence": "reflective", "clause_count": 5}},
        stage8={"audio_safe": True, "quality_score": 1.0, "quality_checks": {"reference_phrase_preserved": True}},
    )

    assert result["stage"] == "stage_9_stage_comparator"
    assert result["readiness"]["ready_for_audio"] is True
    assert result["readiness"]["stable_progression"] is True
    assert result["readiness"]["improvement_score"] >= 0.9
    assert result["regressions"] == []
    assert result["comparison_policy"]["stable_by_stages"] is True
    assert len(result["stage_order"]) == 8
    assert any(item["name"] == "quality_gate" and item["after"] is True for item in result["comparisons"])


def test_stage9_detects_regressions_when_noise_and_audio_safety_fail():
    from tools.voice_orchestrator import VoiceStage9StageComparator

    stage9 = VoiceStage9StageComparator()
    result = stage9.execute(
        text="Visita https://example.com y revisa {\"token\":\"abc\"}.",
        context={"interaction_route": "analysis"},
        stage1={"route": "analysis", "route_reason": "context_explicit_route", "voice_trigger": True},
        stage2={"summary": "interaction_route=analysis", "source_kind": "text"},
        stage3={"mode": "analytical"},
        stage4={"sanitized_display_text": "Visita https://example.com y revisa {\"token\":\"abc\"}.", "speech_text": "Visita https://example.com y revisa {\"token\":\"abc\"}.", "technical_items": [{"kind": "url", "value": "https://example.com", "replacement": "el sitio"}]},
        stage5={"render_text": "Visita y revisa.", "speech_script": {"segment_count": 1}},
        stage6={"fusion_policy": {"parallel_channels": False}, "reactive_channel": {"ack_text": "Ajá"}},
        stage7={"prosody_map": {"cadence": "strategic", "clause_count": 0}},
        stage8={"audio_safe": False, "quality_score": 0.42, "quality_checks": {"reference_phrase_preserved": False}},
    )

    assert result["readiness"]["ready_for_audio"] is False
    assert result["readiness"]["stable_progression"] is False
    assert "audio_not_safe" in result["regressions"]
    assert "dual_channel_missing" in result["regressions"]
    assert "reference_phrase_lost" in result["regressions"]
    assert result["stage8_audio_safe"] is False
