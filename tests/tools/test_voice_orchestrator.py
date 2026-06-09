"""Tests for tools.voice_orchestrator.

The orchestrator is the joint voice skill: it composes the voice contract,
validates speech-safe output, renders audio via the TTS pipeline, and emits
platform-ready metadata.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest


class TestVoiceOrchestratorComposition:
    def test_compose_separates_display_and_speech(self):
        from tools.voice_orchestrator import compose_voice_prompt

        payload = compose_voice_prompt(
            text="**Hola**. Visita https://example.com y revisa `codigo`.",
            context={"channel": "telegram"},
        )

        assert payload["display_text"] == "**Hola**. Visita el sitio y revisa el código."
        assert payload["speech_text"] == "Hola. Visita el sitio y revisa el código."
        assert "MEDIA:" not in payload["speech_text"]
        assert "[[audio_as_voice]]" not in payload["speech_text"]
        assert "https://" not in payload["speech_text"]
        assert payload["voice_profile"]["profile"] == "strategic_consultant"
        assert payload["voice_profile"]["dialogue_posture"] == "professional_trust"
        assert payload["voice_profile"]["communication_quality"] == "high"
        assert payload["style_profile"]["mode"] == "strategic_consultant"
        assert payload["style_profile"]["stance"] == "formed_opinion"
        assert payload["style_profile"]["translation_mode"] == "complex_to_simple"
        assert payload["stage4"]["technical_items"]
        assert payload["stage9"]["stage"] == "stage_9_stage_comparator"
        assert payload["stage10"]["stage"] == "stage_10_production_hardening"
        assert payload["stage10"]["release_decision"] in {"go_live", "text_only"}
        assert payload["llm_request"]["llm_task"] == "generate_voice_ready_response"

    def test_compose_treats_onomatopoeia_as_sonic_cues(self):
        from tools.voice_orchestrator import compose_voice_prompt

        payload = compose_voice_prompt(
            text="Vale, mmm uff jeje y seguimos.",
            context={},
        )

        assert payload["speech_plan"]["onomatopoeia_terms"] == ["mmm", "uff", "jeje"]
        assert any(evt["type"] == "onomatopoeia" for evt in payload["speech_events"])
        assert payload["llm_request"]["speech_event_policy"]["do_not_read_onomatopoeia_as_sigla"] is True
        assert payload["llm_request"]["speech_event_policy"]["onomatopoeia_examples"] == ["mmm", "uff", "jeje", "jaja"]
        assert "mmm" in payload["speech_plan"]["render_text"]
        assert "uff" in payload["speech_plan"]["render_text"]

    def test_compose_treats_sustained_s_sound_as_breath(self):
        from tools.voice_orchestrator import compose_voice_prompt

        payload = compose_voice_prompt(
            text="ssss...",
            context={},
        )

        assert payload["speech_plan"]["breath_terms"] == ["ssss..."]
        assert any(evt["type"] == "breath" for evt in payload["speech_events"])
        assert payload["llm_request"]["response_requirements"]["mark_breath_spaces_instead_of_reading_them"] is True
        assert payload["llm_request"]["response_requirements"]["identify_when_breath_carries_agobio_or_context_load"] is True
        assert payload["llm_request"]["speech_event_policy"]["breath_coding_policy"]["encode_breath_spaces"] is True
        assert payload["llm_request"]["speech_event_policy"]["breath_coding_policy"]["breath_slots_schema"] == ["position", "intent", "reason", "duration_ms"]
        assert "breath_slots" in payload["llm_request"]["required_output_schema"]

    def test_validate_infers_pause_events_and_cleans_speech(self):
        from tools.voice_orchestrator import compose_voice_prompt, validate_voice_packet

        composed = compose_voice_prompt(
            text="Primero. Luego seguimos.\n\nDespués cerramos.",
            context={},
        )
        validated = validate_voice_packet(composed)

        assert validated["speech_text"] == "Primero. Luego seguimos. Después cerramos."
        assert any(evt["type"] == "pause" for evt in validated["speech_events"])
        assert validated["status"] == "ok"


class TestVoiceOrchestratorRendering:
    def test_render_uses_tts_and_emits_media_tag(self, monkeypatch, tmp_path):
        from tools import voice_orchestrator as vo

        monkeypatch.setattr(
            vo,
            "_synthesize_voice_audio",
            lambda speech_text, output_path=None, platform=None: {
                "success": True,
                "file_path": str(tmp_path / "voice.mp3"),
                "media_tag": f"MEDIA:{tmp_path / 'voice.mp3'}",
                "provider": "openvoice",
                "voice_compatible": False,
            },
        )

        result = vo.orchestrate_voice(
            text="Hola mundo.",
            output_path=str(tmp_path / "voice.mp3"),
            platform="cli",
            dry_run=False,
        )
        data = json.loads(result)

        assert data["status"] == "ok"
        assert data["rendered"]["success"] is True
        assert data["audio_path"].endswith("voice.mp3")
        assert data["media_tag"] == f"MEDIA:{tmp_path / 'voice.mp3'}"
        assert data["final_text"] == "Hola mundo."

    def test_validation_overrides_render_text_with_clean_speech(self, monkeypatch, tmp_path):
        from tools import voice_orchestrator as vo

        captured = {"texts": []}

        def _fake_synth(speech_text, output_path=None, platform=None):
            captured["texts"].append(speech_text)
            return {
                "success": True,
                "file_path": str(tmp_path / "voice.mp3"),
                "media_tag": f"MEDIA:{tmp_path / 'voice.mp3'}",
                "provider": "openvoice",
                "voice_compatible": False,
            }

        monkeypatch.setattr(vo, "_synthesize_voice_audio", _fake_synth)

        result = vo.orchestrate_voice(
            text="Te paso el endpoint de registro /api/v1/auth/register para que lo uses.",
            output_path=str(tmp_path / "voice.mp3"),
            platform="cli",
            dry_run=False,
        )
        data = json.loads(result)

        assert "dirección" in data["validated"]["speech_text"].lower()
        assert "endpoint" not in data["validated"]["speech_text"].lower()
        assert "/api" not in data["validated"]["speech_text"].lower()
        assert captured["texts"] == [data["validated"]["speech_text"]]
        assert data["rendered"]["success"] is True

    def test_render_uses_hiss_for_breath_only_text(self, monkeypatch, tmp_path):
        from tools import voice_orchestrator as vo

        called = {"value": False}

        def _fake_hiss(output_path, duration_ms=650):
            called["value"] = True
            return {
                "success": True,
                "file_path": output_path,
                "media_tag": f"MEDIA:{output_path}",
                "provider": "hiss",
                "voice_compatible": True,
            }

        monkeypatch.setattr(vo, "_generate_hiss_audio", _fake_hiss)

        result = vo.orchestrate_voice(
            text="ssss...",
            output_path=str(tmp_path / "hiss.ogg"),
            platform="cli",
            dry_run=False,
        )
        data = json.loads(result)

        assert called["value"] is True
        assert data["rendered"]["provider"] == "hiss"
        assert data["audio_path"].endswith("hiss.ogg")
        assert data["media_tag"] == f"MEDIA:{tmp_path / 'hiss.ogg'}"

    def test_technical_sentences_collapse_once(self):
        from tools.voice_orchestrator import _collapse_technical_sentences

        collapsed = _collapse_technical_sentences(
            "Primero hablamos del endpoint /api/v1/auth/register. Luego del webhook https://example.com/hook y cerramos."
        )

        assert "dirección" in collapsed
        assert "endpoint" not in collapsed.lower()
        assert "/api" not in collapsed.lower()

    def test_technical_auth_and_json_chunks_are_rewritten_for_users(self):
        from tools.voice_orchestrator import _normalize_technical_phrases_for_speech

        auth_text = _normalize_technical_phrases_for_speech("Necesitas un token de auth para entrar al sistema")
        json_text = _normalize_technical_phrases_for_speech("Te paso el json del entorno backend y el script de despliegue")

        assert "llave de acceso" in auth_text or "llave" in auth_text
        assert "configuración" in json_text
        assert "automatización" in json_text
        assert "token" not in auth_text.lower()
        assert "json" not in json_text.lower()

    def test_dry_run_skips_audio_generation(self, monkeypatch, tmp_path):
        from tools import voice_orchestrator as vo

        called = {"value": False}

        def _fake_synth(*args, **kwargs):
            called["value"] = True
            return {"success": True, "file_path": str(tmp_path / "voice.mp3")}

        monkeypatch.setattr(vo, "_synthesize_voice_audio", _fake_synth)

        result = vo.orchestrate_voice(
            text="Hola mundo.",
            output_path=str(tmp_path / "voice.mp3"),
            platform="cli",
            dry_run=True,
        )
        data = json.loads(result)

        assert called["value"] is False
        assert data["status"] == "ok"
        assert data["rendered"] is None
        assert data["media_tag"] is None
        assert data["validated"]["speech_text"] == "Hola mundo."

    def test_orchestrate_voice_input_transcribes_audio_and_sets_voice_trigger(self, monkeypatch, tmp_path):
        from tools import voice_orchestrator as vo

        captured = {}

        def _fake_transcribe(audio_path, model=None):
            captured["audio_path"] = audio_path
            captured["model"] = model
            return {"success": True, "transcript": "Hola, este es el audio"}

        def _fake_orchestrate_voice(**kwargs):
            captured["kwargs"] = kwargs
            return json.dumps({
                "status": "ok",
                "mode": "rendered",
                "display_text": kwargs["text"],
                "speech_text": kwargs["text"],
                "audio_path": str(tmp_path / "reply.ogg"),
                "media_tag": f"MEDIA:{tmp_path / 'reply.ogg'}",
                "provider": "openvoice",
                "validation": {"contract_valid": True, "step_order_valid": True, "artifact_valid": True},
                "warnings": [],
                "error": None,
                "final_text": kwargs["text"],
            }, ensure_ascii=False)

        monkeypatch.setattr(vo, "_transcribe_voice_input", _fake_transcribe)
        monkeypatch.setattr(vo, "orchestrate_voice", _fake_orchestrate_voice)

        result = vo.orchestrate_voice_input(
            audio_path=str(tmp_path / "input.ogg"),
            context={"interaction_route": "analysis"},
            platform="telegram",
            transcribe_model="whisper-large-v3-turbo",
        )
        data = json.loads(result)

        assert captured["audio_path"].endswith("input.ogg")
        assert captured["model"] == "whisper-large-v3-turbo"
        assert captured["kwargs"]["text"] == "Hola, este es el audio"
        assert captured["kwargs"]["context"]["voice_trigger"] is True
        assert captured["kwargs"]["context"]["input_channel"] == "voice"
        assert data["source_kind"] == "audio"
        assert data["transcript"] == "Hola, este es el audio"
        assert data["transcription"]["success"] is True
        assert data["final_text"] == "Hola, este es el audio"

    def test_voice_orchestrator_tool_accepts_audio_path(self, monkeypatch, tmp_path):
        from tools import voice_orchestrator as vo

        called = {}

        def _fake_input(**kwargs):
            called.update(kwargs)
            return json.dumps({"status": "ok", "mode": "rendered", "final_text": "transcribed"}, ensure_ascii=False)

        monkeypatch.setattr(vo, "orchestrate_voice_input", _fake_input)

        result = vo.voice_orchestrator_tool(
            text="",
            audio_path=str(tmp_path / "msg.ogg"),
            transcribe_model="base",
        )
        data = json.loads(result)

        assert called["audio_path"].endswith("msg.ogg")
        assert called["transcribe_model"] == "base"
        assert data["status"] == "ok"
