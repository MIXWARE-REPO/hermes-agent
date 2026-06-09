"""Identity tests for the voice orchestrator.

These tests pin the default reference style so the voice stays natural and
consistent even before config overrides are added.
"""


def test_default_identity_reflects_customer_care_reference():
    from tools.voice_orchestrator import compose_voice_prompt

    payload = compose_voice_prompt("Hola, ¿en qué puedo ayudarte?")

    assert payload["voice_profile"]["profile"] == "strategic_consultant"
    assert payload["voice_profile"]["authority"] >= 0.8
    assert payload["voice_profile"]["warmth"] <= 0.35
    assert payload["voice_profile"]["allow_fillers"] is False
    assert payload["identity_profile"]["voice_reference"] == "voice_9"
    assert payload["identity_profile"]["relationship_model"] == "professional_trust_with_dialogue"
    assert "strategic_and_communicative" in payload["identity_profile"]["voice_characteristics"]
    assert payload["style_profile"]["mode"] == "strategic_consultant"
    assert payload["style_profile"]["counterpoint"] >= 0.6
    assert payload["style_profile"]["translation_mode"] == "complex_to_simple"
