"""Stage 2 tests for the voice orchestrator context recovery layer."""


def test_stage2_compacts_context_and_preserves_useful_memory():
    from tools.voice_orchestrator import VoiceStage2ContextMemory

    stage2 = VoiceStage2ContextMemory()
    result = stage2.execute(
        text="Mira, seguimos.",
        context={
            "interaction_route": "analysis",
            "route_reason": "prosody_reference",
            "topic": "voice_orchestrator",
            "theme": "humanization",
            "irrelevant_debug": "drop_me",
            "recent_messages": ["uno", "dos", "tres"],
        },
    )

    assert result["stage"] == "stage_2_context_memory"
    assert result["context_summary"]["interaction_route"] == "analysis"
    assert result["context_summary"]["route_reason"] == "prosody_reference"
    assert result["context_summary"]["topic"] == "voice_orchestrator"
    assert result["context_summary"]["theme"] == "humanization"
    assert "irrelevant_debug" not in result["context_summary"]
    assert result["memory_hints"] == ["topic=voice_orchestrator", "theme=humanization"]


def test_stage2_uses_stage1_route_and_voice_trigger_when_present():
    from tools.voice_orchestrator import VoiceStage2ContextMemory

    stage2 = VoiceStage2ContextMemory()
    result = stage2.execute(
        text="Hola",
        context={"topic": "voice", "voice_trigger": True},
        stage1={"route": "execution", "voice_trigger": True, "source_kind": "audio"},
    )

    assert result["context_summary"]["route"] == "execution"
    assert result["context_summary"]["voice_trigger"] is True
    assert result["context_summary"]["source_kind"] == "audio"
    assert result["context_summary"]["stage1_route"] == "execution"
