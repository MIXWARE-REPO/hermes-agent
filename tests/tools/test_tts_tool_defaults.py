"""Tests for TTS defaults.

This keeps the default voice aligned with the established Spanish voice identity.
"""


def test_default_edge_voice_is_elvira():
    import tools.tts_tool as tts

    assert tts.DEFAULT_EDGE_VOICE == "es-ES-ElviraNeural"
