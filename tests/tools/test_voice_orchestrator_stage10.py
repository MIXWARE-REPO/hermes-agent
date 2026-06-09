"""Stage 10 tests for the voice orchestrator production hardening layer."""


def test_stage10_locks_release_for_audio_when_all_previous_stages_are_valid():
    from tools.voice_orchestrator import VoiceStage10ProductionHardening

    stage10 = VoiceStage10ProductionHardening()
    text = "Mira…, no es que esté enfadada, es que, sinceramente, después de todo lo que ha pasado, me sorprende que todavía sigas preguntando lo mismo…"
    result = stage10.execute(
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
        stage9={"readiness": {"ready_for_audio": True, "stable_progression": True, "improvement_score": 0.9, "reference_phrase_preserved": True}, "regressions": []},
    )

    assert result["stage"] == "stage_10_production_hardening"
    assert result["release_decision"] == "go_live"
    assert result["locked"] is True
    assert result["delivery_mode"] == "audio"
    assert result["fallback_mode"] == "none"
    assert result["contract"]["contract_version"] == "1.0.0"
    assert result["contract"]["strict_mode"] is True
    assert result["release_checks"]["audio_safe"] is True
    assert result["release_checks"]["stable_progression"] is True


def test_stage10_forces_text_only_when_quality_or_readiness_is_bad():
    from tools.voice_orchestrator import VoiceStage10ProductionHardening

    stage10 = VoiceStage10ProductionHardening()
    result = stage10.execute(
        text="Visita https://example.com y revisa {\"token\":\"abc\"}.",
        context={"interaction_route": "analysis"},
        stage1={"route": "analysis", "route_reason": "context_explicit_route", "voice_trigger": True},
        stage2={"summary": "interaction_route=analysis", "source_kind": "text"},
        stage3={"mode": "analytical"},
        stage4={"sanitized_display_text": "Visita y revisa.", "speech_text": "Visita y revisa.", "technical_items": [{"kind": "url", "value": "https://example.com", "replacement": "el sitio"}]},
        stage5={"render_text": "Visita y revisa.", "speech_script": {"segment_count": 1}},
        stage6={"fusion_policy": {"parallel_channels": False}, "reactive_channel": {"ack_text": "Ajá"}},
        stage7={"prosody_map": {"cadence": "strategic", "clause_count": 0}},
        stage8={"audio_safe": False, "quality_score": 0.42, "quality_checks": {"reference_phrase_preserved": False}},
        stage9={"readiness": {"ready_for_audio": False, "stable_progression": False, "improvement_score": 0.35, "reference_phrase_preserved": False}, "regressions": ["audio_not_safe"]},
    )

    assert result["release_decision"] == "text_only"
    assert result["locked"] is True
    assert result["delivery_mode"] == "text"
    assert result["fallback_mode"] == "text_only"
    assert result["release_checks"]["audio_safe"] is False
    assert result["release_checks"]["ready_for_audio"] is False
    assert "audio_not_safe" in result["release_checks"]["regressions"]
