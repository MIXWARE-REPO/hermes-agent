"""Stage 6 tests for the voice orchestrator dual-channel layer."""


def test_stage6_creates_reactive_and_analytical_channels_for_reflective_phrase():
    from tools.voice_orchestrator import VoiceStage6DualChannelFusion

    stage6 = VoiceStage6DualChannelFusion()
    text = "Mira…, no es que esté enfadada, es que, sinceramente, después de todo lo que ha pasado, me sorprende que todavía sigas preguntando lo mismo…"
    result = stage6.execute(
        text=text,
        context={"interaction_route": "analysis", "voice_trigger": True},
        stage1={"route": "analysis", "route_reason": "context_explicit_route"},
        stage2={"summary": "interaction_route=analysis"},
        stage3={"mode": "reflective"},
        stage4={"sanitized_display_text": text, "speech_text": text},
        stage5={
            "mode": "reflective",
            "speech_script": {"segments": ["Mira…", "no es que esté enfadada"], "segment_count": 2},
            "speech_plan": {"opening_style": "reflective", "segments": ["Mira…", "no es que esté enfadada"]},
            "render_text": text,
        },
    )

    assert result["stage"] == "stage_6_dual_channel_fusion"
    assert result["reactive_channel"]["enabled"] is True
    assert result["reactive_channel"]["ack_text"] in {"Entiendo", "Vale", "Ajá"}
    assert result["analytical_channel"]["mode"] == "reflective"
    assert result["fusion_policy"]["parallel_channels"] is True
    assert result["fusion_policy"]["preserve_reference_phrase"] is True
    assert result["render_text"] == text


def test_stage6_keeps_execution_mode_reactive_and_short():
    from tools.voice_orchestrator import VoiceStage6DualChannelFusion

    stage6 = VoiceStage6DualChannelFusion()
    result = stage6.execute(
        text="Hazlo ahora y cierra el ticket.",
        context={"interaction_route": "execution"},
        stage1={"route": "execution", "route_reason": "context_explicit_route"},
        stage2={"summary": "interaction_route=execution"},
        stage3={"mode": "executive"},
        stage4={"sanitized_display_text": "Hazlo ahora y cierra el ticket.", "speech_text": "Hazlo ahora y cierra el ticket."},
        stage5={
            "mode": "executive",
            "speech_script": {"segments": ["Hazlo ahora", "cierra el ticket"], "segment_count": 2},
            "speech_plan": {"opening_style": "direct", "segments": ["Hazlo ahora", "cierra el ticket"]},
            "render_text": "Hazlo ahora\ncierra el ticket.",
        },
    )

    assert result["reactive_channel"]["ack_text"] == "Vale"
    assert result["reactive_channel"]["latency_ms"] <= 180
    assert result["analytical_channel"]["mode"] == "executive"
    assert result["fusion_policy"]["parallel_channels"] is True
