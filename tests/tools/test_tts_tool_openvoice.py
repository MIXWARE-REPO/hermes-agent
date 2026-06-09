"""OpenVoice provider tests for the TTS tool.

These tests verify that OpenVoice is the only allowed renderer path and that
failure is explicit when the OpenVoice stack is unavailable.
"""

import json


def test_default_provider_is_openvoice():
    import tools.tts_tool as tts

    assert tts.DEFAULT_PROVIDER == "openvoice"


def test_openvoice_provider_generates_audio_when_available(monkeypatch, tmp_path):
    import tools.tts_tool as tts

    called = {"openvoice": False}

    monkeypatch.setattr(tts, "_load_tts_config", lambda: {"provider": "openvoice"})
    monkeypatch.setattr(tts, "_import_openvoice_modules", lambda: object())
    def fake_openvoice(text, output_path, tts_config):
        called["openvoice"] = True
        with open(output_path, "wb") as f:
            f.write(b"openvoice")
        return output_path

    monkeypatch.setattr(tts, "_generate_openvoice_v2", fake_openvoice)

    result = json.loads(tts.text_to_speech_tool(text="hola mundo", output_path=str(tmp_path / "voice.ogg")))

    assert called["openvoice"] is True
    assert result["success"] is True
    assert result["provider"] == "openvoice"
    assert result["file_path"].endswith("voice.ogg")


def test_openvoice_fails_explicitly_when_dependencies_missing(monkeypatch, tmp_path):
    import tools.tts_tool as tts

    monkeypatch.setattr(tts, "_load_tts_config", lambda: {"provider": "openvoice"})
    monkeypatch.setattr(tts, "_import_openvoice_modules", lambda: (_ for _ in ()).throw(ImportError()))

    result = json.loads(tts.text_to_speech_tool(text="hola mundo", output_path=str(tmp_path / "voice.ogg")))

    assert result["success"] is False
    assert "OpenVoice" in result["error"]


def test_openvoice_applies_pitch_shift_config(monkeypatch):
    import tools.tts_tool as tts

    captured = {}

    def fake_generate_openvoice_v2(text, output_path, tts_config):
        captured["cfg"] = tts_config["openvoice"].copy()
        with open(output_path, "wb") as f:
            f.write(b"RIFF....WAVEfmt ")
        return output_path

    monkeypatch.setattr(tts, "_load_tts_config", lambda: {"provider": "openvoice", "openvoice": {"pitch_semitones": 0.5}})
    monkeypatch.setattr(tts, "_generate_openvoice_v2", fake_generate_openvoice_v2)
    monkeypatch.setattr(tts.os.path, "exists", lambda p: True)
    monkeypatch.setattr(tts.os.path, "getsize", lambda p: 16)

    result = json.loads(tts.text_to_speech_tool(text="hola mundo", output_path="/tmp/voice.ogg"))

    assert result["success"] is True
    assert captured["cfg"]["pitch_semitones"] == 0.5

