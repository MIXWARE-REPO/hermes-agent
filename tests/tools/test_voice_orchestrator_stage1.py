"""Stage 1 tests for the voice orchestrator channel gate."""


def test_stage1_text_input_defaults_to_text_channel_and_no_voice_trigger():
    from tools.voice_orchestrator import VoiceStage1ChannelGate

    gate = VoiceStage1ChannelGate()
    result = gate.execute(text="Hola mundo", audio_path=None, context={})

    assert result["stage"] == "stage_1_channel_gate"
    assert result["input_channel"] == "text"
    assert result["voice_trigger"] is False
    assert result["source_kind"] == "text"
    assert result["route"] == "analysis"


def test_stage1_audio_input_enables_voice_trigger_and_voice_channel():
    from tools.voice_orchestrator import VoiceStage1ChannelGate

    gate = VoiceStage1ChannelGate()
    result = gate.execute(text="", audio_path="/tmp/input.ogg", context={})

    assert result["input_channel"] == "voice"
    assert result["voice_trigger"] is True
    assert result["source_kind"] == "audio"
    assert result["route"] == "analysis"


def test_stage1_preserves_explicit_execution_route_from_context():
    from tools.voice_orchestrator import VoiceStage1ChannelGate

    gate = VoiceStage1ChannelGate()
    result = gate.execute(text="Hazlo", audio_path=None, context={"interaction_route": "execution"})

    assert result["route"] == "execution"
    assert result["route_reason"] == "context_explicit_route"
