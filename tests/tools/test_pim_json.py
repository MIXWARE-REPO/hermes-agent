import json


def test_pim_json_schema_and_translation():
    from tools.pim_json import build_pim_json, validate_pim_json

    text = (
        "Hola, mi nombre es Laya, me gusta mucho asistirte, soy una persona muy potente, "
        "tengo mucha energía, pero también puedo ser muy tranquila."
    )
    doc = build_pim_json(text)
    validated = validate_pim_json(doc)

    assert validated["schema_version"] == "voice_prosody_v1"
    assert validated["format"] == "PIM-JSON"
    assert validated["language"] == "es"
    assert validated["segments"]
    assert len(validated["segments"]) <= 4
    assert all("phrase_intent" in seg for seg in validated["segments"])
    assert validated["rendering_hints"]["provider"] == "openvoice"
    assert validated["rendering_hints"]["openvoice"]["speed"] > 1.0
    assert validated["rendering_hints"]["openvoice"]["prosody_pause_scale"] < 1.0
    assert any(seg["grammar_role"] == "main_verb" for seg in validated["segments"])
    assert any(seg["phrase_intent"] in {"passion", "commitment", "contrast"} for seg in validated["segments"])
    assert any(seg["semantic_weight"] >= 0.8 for seg in validated["segments"])


def test_pim_json_marks_pause_and_close_segments():
    from tools.pim_json import build_pim_json

    text = "Primero analizamos el problema y luego decidimos el siguiente paso para cerrar la idea."
    doc = build_pim_json(text)

    assert doc["segments"][-1]["pause_after_ms"] >= 500
    assert doc["segments"][-1]["grammar_role"] in {"conceptual_close", "object_phrase"}
    assert doc["overall_intent"] in {"interes_cerrado", "interes_creciente", "explicacion_controlada"}
