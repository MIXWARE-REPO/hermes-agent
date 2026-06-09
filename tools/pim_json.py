#!/usr/bin/env python3
"""PIM-JSON helpers for deterministic voice prosody planning.

This module turns Spanish text into a schema-valid PIM-JSON document and also
projects that document into a practical OpenVoice rendering profile.

The goal is to keep three layers separate:
- text analysis -> PIM-JSON
- schema validation -> jsonschema
- audio rendering -> OpenVoice/tts_tool
"""

from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List, Optional

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - dependency is present in the working venv
    Draft202012Validator = None  # type: ignore[assignment]

SCHEMA_VERSION = "voice_prosody_v1"
FORMAT_NAME = "PIM-JSON"

CONNECTORS = {
    "y", "e", "o", "u", "pero", "aunque", "porque", "si", "cuando",
    "mientras", "entonces", "luego", "además", "sin", "con", "de", "del",
    "al", "por", "para", "en", "sobre", "entretanto", "así", "que",
    "sin embargo", "de hecho", "por eso", "por lo tanto", "en cambio",
}
AUXILIARY_VERBS = {
    "ser", "estar", "haber", "poder", "deber", "querer", "ir", "tener", "soler",
}
ACTION_VERBS = {
    "validar", "hacer", "decidir", "explicar", "mostrar", "crear", "entregar",
    "ajustar", "probar", "cerrar", "enviar", "buscar", "tomar", "marcar",
    "cargar", "leer", "escribir", "revisar", "mejorar", "asistir", "asistirte",
    "priorizar", "controlar", "mantener", "gestionar", "confirmar", "activar",
    "preparar", "construir", "traducir", "interpretar", "registrar", "renderizar",
}
ADJECTIVE_ENDINGS = (
    "oso", "osa", "ivo", "iva", "al", "able", "ible", "ante", "ente", "ario",
    "aria", "ado", "ada", "ido", "ida", "ico", "ica", "al", "il", "ar", "or",
)
CLOSING_WORDS = {
    "firma", "firmar", "cierre", "cerrar", "lista", "conclusión", "concluir",
    "resumen", "final", "termina", "terminar", "queda", "listo", "aprobado",
}
EMOTION_KEYWORDS = {
    "importante": 0.12,
    "importancia": 0.12,
    "potente": 0.15,
    "energía": 0.18,
    "energia": 0.18,
    "tranquila": 0.08,
    "tranquilo": 0.08,
    "asistirte": 0.14,
    "asistir": 0.10,
    "hola": 0.08,
    "perfecto": 0.10,
    "ahora": 0.09,
    "muy": 0.05,
}


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _normalize_text(text: str) -> str:
    text = (text or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-záéíóúüñ]+", text.lower())


def _split_text(text: str) -> List[str]:
    normalized = _normalize_text(text)
    if not normalized:
        return []

    def _merge_fragments(fragments: List[str], target_min: int = 52, target_max: int = 118) -> List[str]:
        merged: List[str] = []
        buffer = ""
        connector_words = {
            "y", "e", "o", "u", "pero", "aunque", "porque", "que", "si", "cuando",
            "mientras", "entonces", "luego", "además", "sin", "con", "de", "del", "al",
            "por", "para", "en", "sobre", "sin embargo", "por eso", "por lo tanto",
        }

        def _starts_like_connector(text: str) -> bool:
            first = _tokenize(text)[:1]
            return bool(first) and first[0] in connector_words

        for frag in fragments:
            frag = (frag or "").strip()
            if not frag:
                continue
            if not buffer:
                buffer = frag
                continue
            candidate = f"{buffer} {frag}".strip()
            should_keep_together = (
                len(buffer) < target_min
                or len(candidate) <= target_max
                or _starts_like_connector(frag)
                or buffer.endswith((",", ";", ":", "—", "–"))
            )
            if should_keep_together:
                buffer = candidate
            else:
                merged.append(buffer)
                buffer = frag
        if buffer:
            merged.append(buffer)
        return merged

    # Prefer sentence boundaries first so the phrase planner operates on natural clauses.
    sentence_parts = [p.strip() for p in re.split(r"(?<=[\.!?])\s+", normalized) if p.strip()]
    if len(sentence_parts) > 1:
        return sentence_parts

    sentence = sentence_parts[0] if sentence_parts else normalized
    if len(sentence) <= 115:
        return [sentence]

    raw_clauses = [p.strip() for p in re.split(r"(?<=[,;:—–])\s+", sentence) if p.strip()]
    if len(raw_clauses) <= 1:
        raw_clauses = re.split(r"\s+(?=(?:pero|aunque|porque|entonces|además|sin embargo|por eso|por lo tanto)\b)", sentence, flags=re.IGNORECASE)
        raw_clauses = [p.strip() for p in raw_clauses if p.strip()]
    if len(raw_clauses) <= 1:
        return [sentence]

    return _merge_fragments(raw_clauses)


def _looks_verbish(token: str) -> bool:
    if token in ACTION_VERBS or token in AUXILIARY_VERBS:
        return True
    return token.endswith((
        "ar", "er", "ir", "ando", "iendo", "ado", "ada", "ido", "ida",
        "amos", "emos", "imos", "aré", "eré", "iré", "aba", "ía", "ó", "é", "í",
    ))


def _looks_adjective(tokens: List[str]) -> bool:
    if not tokens:
        return False
    if any(_looks_verbish(token) for token in tokens):
        return False
    return any(token.endswith(ADJECTIVE_ENDINGS) for token in tokens)


def _is_connector(segment: str, tokens: List[str]) -> bool:
    if not tokens:
        return False
    first = tokens[0]
    if first in CONNECTORS:
        return True
    lower = segment.lower().strip()
    return any(lower.startswith(connector + " ") for connector in CONNECTORS if " " in connector)


def _classify_segment(segment: str, index: int, total: int) -> str:
    tokens = _tokenize(segment)
    if not tokens:
        return "connector"

    lower = segment.lower().strip()
    if _is_connector(segment, tokens):
        return "connector"
    if index == total - 1 and any(word in lower for word in CLOSING_WORDS):
        return "conceptual_close"
    if index == total - 1 and lower.endswith((".", "!", "?")) and any(
        marker in lower for marker in ("para ", "cerrar", "cierre", "firma", "queda listo", "queda lista")
    ):
        return "conceptual_close"
    if _looks_adjective(tokens):
        return "qualifying_adjective"
    if any(_looks_verbish(token) for token in tokens):
        if index == total - 1 and any(word in lower for word in (CLOSING_WORDS | {"cerrar", "firmar", "terminar"})):
            return "conceptual_close"
        if tokens[0] in AUXILIARY_VERBS:
            return "auxiliary_verb"
        return "main_verb"
    if index == 0:
        return "subject"
    if index == total - 1 and len(tokens) >= 2:
        return "conceptual_close" if lower.endswith((".", "!", "?")) else "object_phrase"
    return "object_phrase"


def _semantic_role_for(grammar_role: str) -> str:
    mapping = {
        "subject": "main_entity",
        "main_verb": "core_action",
        "auxiliary_verb": "support_action",
        "object_phrase": "relevant_object",
        "qualifying_adjective": "evaluative_adjective",
        "connector": "discourse_marker",
        "conceptual_close": "conclusion",
    }
    return mapping.get(grammar_role, "relevant_object")


def _phrase_intent(segment: str, grammar_role: str, emotion_level: float) -> str:
    """Classify the phrase as a whole so prosody follows phrase meaning, not isolated words."""
    lower = segment.lower()
    if grammar_role == "connector":
        return "flow_bridge"
    if grammar_role == "conceptual_close":
        return "landing"
    if any(marker in lower for marker in ("pero", "aunque", "sin embargo", "en cambio")):
        return "contrast"
    if any(marker in lower for marker in ("porque", "ya que", "puesto que", "así que", "por eso", "de hecho")):
        return "explanation"
    if any(marker in lower for marker in ("importante", "potente", "energía", "energia", "asistirte", "apasion", "encanta", "quiero")):
        return "passion"
    if grammar_role == "main_verb" and emotion_level >= 0.72:
        return "commitment"
    if grammar_role == "main_verb":
        return "action"
    if grammar_role == "subject":
        return "framing"
    if grammar_role == "qualifying_adjective":
        return "color"
    if segment.endswith(("?", "!")):
        return "accent"
    return "continuation"


def _emotion_level(segment: str, grammar_role: str, index: int, total: int) -> float:
    base = {
        "subject": 0.44,
        "main_verb": 0.66,
        "auxiliary_verb": 0.25,
        "object_phrase": 0.50,
        "qualifying_adjective": 0.60,
        "connector": 0.20,
        "conceptual_close": 0.38,
    }.get(grammar_role, 0.40)
    lower = segment.lower()
    keyword_bonus = sum(bonus for word, bonus in EMOTION_KEYWORDS.items() if word in lower)
    length_bonus = 0.04 if len(segment) > 42 else 0.0
    position_bonus = 0.04 if index == 0 else (0.06 if index == total - 1 else 0.0)
    punctuation_bonus = 0.05 if segment.endswith("!") else (0.02 if segment.endswith("?") else 0.0)
    return _clamp(base + keyword_bonus + length_bonus + position_bonus + punctuation_bonus, 0.05, 0.95)


def _semantic_weight(grammar_role: str, emotion_level: float, segment: str) -> float:
    base = {
        "subject": 0.85,
        "main_verb": 0.92,
        "auxiliary_verb": 0.42,
        "object_phrase": 0.75,
        "qualifying_adjective": 0.67,
        "connector": 0.25,
        "conceptual_close": 0.82,
    }.get(grammar_role, 0.60)
    if any(word in segment.lower() for word in ("importante", "potente", "energía", "energia", "asistirte")):
        base += 0.05
    return _clamp(base + (emotion_level - 0.5) * 0.10, 0.05, 0.99)


def _prosody_for(grammar_role: str, emotion_level: float, segment: str, index: int, total: int) -> Dict[str, float]:
    intent = _phrase_intent(segment, grammar_role, emotion_level)
    if grammar_role == "main_verb":
        values = {
            "pitch_shift_pct": 3.5,
            "energy_boost_db": 2.8,
            "rate_pct": -2,
            "duration_pct": 4,
            "vowel_stretch_pct": 0,
            "attack": 0.86,
            "emphasis_level": 0.88,
        }
    elif grammar_role == "subject":
        values = {
            "pitch_shift_pct": 1.5,
            "energy_boost_db": 1.4,
            "rate_pct": -2,
            "duration_pct": 3,
            "vowel_stretch_pct": 0,
            "attack": 0.62,
            "emphasis_level": 0.70,
        }
    elif grammar_role == "qualifying_adjective":
        values = {
            "pitch_shift_pct": 2.5,
            "energy_boost_db": 1.0,
            "rate_pct": -4,
            "duration_pct": 8,
            "vowel_stretch_pct": 10,
            "attack": 0.46,
            "emphasis_level": 0.62,
        }
    elif grammar_role == "connector":
        values = {
            "pitch_shift_pct": -0.5,
            "energy_boost_db": -0.8,
            "rate_pct": 4,
            "duration_pct": -3,
            "vowel_stretch_pct": 0,
            "attack": 0.22,
            "emphasis_level": 0.22,
        }
    elif grammar_role == "conceptual_close":
        values = {
            "pitch_shift_pct": -2.5,
            "energy_boost_db": -0.4,
            "rate_pct": -6,
            "duration_pct": 4,
            "vowel_stretch_pct": 2,
            "attack": 0.38,
            "emphasis_level": 0.48,
        }
    elif grammar_role == "auxiliary_verb":
        values = {
            "pitch_shift_pct": 0,
            "energy_boost_db": -0.4,
            "rate_pct": 1,
            "duration_pct": -1,
            "vowel_stretch_pct": 0,
            "attack": 0.32,
            "emphasis_level": 0.26,
        }
    else:
        values = {
            "pitch_shift_pct": 0.8,
            "energy_boost_db": 0.8,
            "rate_pct": -1,
            "duration_pct": 3,
            "vowel_stretch_pct": 0,
            "attack": 0.48,
            "emphasis_level": 0.58,
        }

    # Phrase intent shapes the emotional contour without fragmenting the sentence.
    intent_boost = {
        "passion": {"energy": 1.2, "rate": 0.0, "pitch": 1.6, "attack": 0.06, "emphasis": 0.08, "stretch": 3.0},
        "commitment": {"energy": 1.0, "rate": -0.5, "pitch": 1.1, "attack": 0.05, "emphasis": 0.06, "stretch": 1.0},
        "action": {"energy": 0.5, "rate": 0.2, "pitch": 0.3, "attack": 0.03, "emphasis": 0.04, "stretch": 0.0},
        "framing": {"energy": 0.3, "rate": -0.1, "pitch": 0.2, "attack": 0.02, "emphasis": 0.03, "stretch": 0.0},
        "color": {"energy": 0.4, "rate": -0.3, "pitch": 0.4, "attack": 0.02, "emphasis": 0.03, "stretch": 2.0},
        "contrast": {"energy": 0.2, "rate": -0.2, "pitch": 0.6, "attack": 0.01, "emphasis": 0.02, "stretch": 0.0},
        "explanation": {"energy": -0.1, "rate": -0.4, "pitch": -0.2, "attack": -0.01, "emphasis": 0.00, "stretch": 0.0},
        "landing": {"energy": -0.2, "rate": -0.6, "pitch": -0.9, "attack": -0.02, "emphasis": 0.00, "stretch": 1.0},
        "flow_bridge": {"energy": -0.4, "rate": 0.3, "pitch": 0.0, "attack": -0.03, "emphasis": -0.02, "stretch": 0.0},
        "continuation": {"energy": 0.0, "rate": 0.0, "pitch": 0.0, "attack": 0.0, "emphasis": 0.0, "stretch": 0.0},
        "accent": {"energy": 0.2, "rate": -0.1, "pitch": 0.4, "attack": 0.02, "emphasis": 0.03, "stretch": 0.0},
    }.get(intent, {"energy": 0.0, "rate": 0.0, "pitch": 0.0, "attack": 0.0, "emphasis": 0.0, "stretch": 0.0})

    values["pitch_shift_pct"] = round(_clamp(values["pitch_shift_pct"] + emotion_level * 2.6 + intent_boost["pitch"], -8, 10), 2)
    values["energy_boost_db"] = round(_clamp(values["energy_boost_db"] + emotion_level * 1.2 + intent_boost["energy"], -4, 5), 2)
    values["rate_pct"] = round(_clamp(values["rate_pct"] + intent_boost["rate"] + (0.2 if len(segment) > 34 else 0.0), -18, 10), 2)
    values["duration_pct"] = round(_clamp(values["duration_pct"] + (2.0 if len(segment) > 26 else 0.0) + (1.0 if intent == "passion" else 0.0), -20, 40), 2)
    values["attack"] = round(_clamp(values["attack"] + emotion_level * 0.06 + intent_boost["attack"], 0.0, 1.0), 2)
    values["emphasis_level"] = round(_clamp(values["emphasis_level"] + emotion_level * 0.10 + intent_boost["emphasis"], 0.0, 1.0), 2)
    values["vowel_stretch_pct"] = round(_clamp(values["vowel_stretch_pct"] + intent_boost["stretch"] + (2.0 if grammar_role == "qualifying_adjective" else 0.0), 0, 35), 2)
    return values


def _contour_for(grammar_role: str, emotion_level: float, index: int, total: int) -> Dict[str, Any]:
    if grammar_role == "conceptual_close":
        return {"type": "falling", "start_pitch_pct": 2, "end_pitch_pct": -4}
    if grammar_role == "main_verb":
        return {"type": "rise_fall", "start_pitch_pct": 0, "peak_pitch_pct": 5 + round(emotion_level * 3), "end_pitch_pct": -1}
    if grammar_role == "subject":
        return {"type": "soft_rise_fall", "start_pitch_pct": 0, "peak_pitch_pct": 4, "end_pitch_pct": 1}
    if emotion_level >= 0.65 and index < total - 1:
        return {"type": "progressive_rise", "start_pitch_pct": -2, "end_pitch_pct": 8, "curve": "linear_soft"}
    return {"type": "flat", "start_pitch_pct": 0, "end_pitch_pct": 0}


def _pause_after_ms(segment: str, grammar_role: str, index: int, total: int) -> int:
    segment = segment.strip()
    if grammar_role == "conceptual_close":
        pause = 720
    elif segment.endswith("...") or segment.endswith("…"):
        pause = 280
    elif segment.endswith((".", "!", "?")):
        pause = 170
    elif segment.endswith((";", ":", "—", "–")):
        pause = 110
    elif segment.endswith(","):
        pause = 70
    elif grammar_role == "connector":
        pause = 50
    elif grammar_role == "main_verb":
        pause = 90
    elif grammar_role == "subject":
        pause = 150
    else:
        pause = 120
    if index == total - 1:
        pause += 90
    if len(segment) > 65:
        pause += 40
    return int(_clamp(pause, 20, 1500))


def _global_voice_style(segments: List[Dict[str, Any]]) -> Dict[str, Any]:
    emotions = [float(seg.get("emotion_level", 0.4)) for seg in segments] or [0.4]
    weights = [float(seg.get("semantic_weight", 0.6)) for seg in segments] or [0.6]
    avg_emotion = mean(emotions)
    avg_weight = mean(weights)
    pace = 1.0 + (avg_emotion - 0.45) * 0.18 + (avg_weight - 0.7) * 0.04
    pace = _clamp(pace, 0.90, 1.16)
    pause_density = _clamp(0.98 - avg_emotion * 0.18, 0.55, 1.10)
    return {
        "persona": "humana_profesional",
        "base_pitch": "medium_high" if avg_emotion > 0.55 else "medium_low",
        "base_energy": "medium_high" if avg_emotion > 0.55 else "medium",
        "base_rate": round(1.0 / pace, 2),
        "natural_variation": {
            "enabled": True,
            "pause_jitter_ms": [-40, 60],
            "pitch_jitter_pct": [-2, 2],
            "energy_jitter_db": [-0.8, 0.8],
        },
        "pace_hint": round(pace, 2),
        "pause_density_hint": round(pause_density, 2),
    }


def _rendering_hints(segments: List[Dict[str, Any]]) -> Dict[str, Any]:
    emotions = [float(seg.get("emotion_level", 0.4)) for seg in segments] or [0.4]
    weights = [float(seg.get("semantic_weight", 0.6)) for seg in segments] or [0.6]
    avg_emotion = mean(emotions)
    avg_weight = mean(weights)
    energetic = avg_emotion > 0.52 or avg_weight > 0.78
    speed = _clamp(1.0 + avg_emotion * 0.12 + (0.03 if energetic else 0.0), 0.92, 1.18)
    # Keep pitch more conservative by default; energetic delivery should come
    # primarily from rate, pause shape and energy, not from an aggressively high pitch.
    pitch = _clamp(-0.10 + avg_emotion * 0.42 + (0.06 if energetic else 0.0), -0.9, 0.95)
    pause_scale = _clamp(1.02 - avg_emotion * 0.16, 0.76, 1.05)
    contour_strength = _clamp(0.03 + avg_emotion * 0.06, 0.02, 0.10)
    return {
        "provider": "openvoice",
        "openvoice": {
            "speed": round(speed, 3),
            "prosody_mode": "energetic" if energetic else "expressive",
            "prosody_pause_scale": round(pause_scale, 3),
            "pitch_semitones": round(pitch, 3),
            "pitch_contour_strength": round(contour_strength, 3),
            "pitch_contour_sections": 4 if len(segments) < 5 else 5,
            "base_provider": "edge",
        },
        "voice_profile": {
            "speed": round(speed, 3),
            "pause_density": round(_clamp(1.0 - pause_scale * 0.35, 0.45, 0.95), 3),
            "authority": round(_clamp(0.75 + avg_weight * 0.2, 0.0, 1.0), 3),
            "warmth": round(_clamp(0.22 + (1.0 - avg_emotion) * 0.12, 0.0, 1.0), 3),
            "intonation_variation": round(_clamp(0.62 + avg_emotion * 0.22, 0.0, 1.0), 3),
            "allow_breaths": len(segments) > 3 or avg_emotion > 0.58,
            "dialogue_posture": "professional_trust",
            "communication_quality": "high",
        },
    }


def build_pim_json(text: str, language: str = "es") -> Dict[str, Any]:
    normalized = _normalize_text(text)
    segments_text = _split_text(normalized)
    if not segments_text and normalized:
        segments_text = [normalized]

    segments: List[Dict[str, Any]] = []
    total = len(segments_text)
    for idx, segment_text in enumerate(segments_text):
        grammar_role = _classify_segment(segment_text, idx, total)
        emotion = _emotion_level(segment_text, grammar_role, idx, total)
        phrase_intent = _phrase_intent(segment_text, grammar_role, emotion)
        semantic_weight = _semantic_weight(grammar_role, emotion, segment_text)
        prosody = _prosody_for(grammar_role, emotion, segment_text, idx, total)
        segment = {
            "id": f"s{idx + 1}",
            "text": segment_text,
            "grammar_role": grammar_role,
            "semantic_role": _semantic_role_for(grammar_role),
            "phrase_intent": phrase_intent,
            "emotion_level": round(emotion, 3),
            "semantic_weight": round(semantic_weight, 3),
            "prosody": prosody,
            "contour": _contour_for(grammar_role, emotion, idx, total),
            "pause_after_ms": _pause_after_ms(segment_text, grammar_role, idx, total),
        }
        segments.append(segment)

    pim = {
        "schema_version": SCHEMA_VERSION,
        "format": FORMAT_NAME,
        "language": language,
        "text": normalized,
        "display_text": normalized,
        "speech_text": normalized,
        "overall_intent": _infer_intent(normalized, segments),
        "global_voice_style": _global_voice_style(segments),
        "segments": segments,
        "rendering_hints": _rendering_hints(segments),
    }
    return pim


def _infer_intent(text: str, segments: List[Dict[str, Any]]) -> str:
    lower = text.lower()
    if "hola" in lower or "presentación" in lower:
        return "introduccion_humana"
    if any(seg["grammar_role"] == "conceptual_close" for seg in segments):
        return "interes_cerrado"
    if any(seg["emotion_level"] >= 0.7 for seg in segments):
        return "interes_creciente"
    return "explicacion_controlada"


PIM_JSON_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "PIM-JSON voice prosody schema",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema_version",
        "format",
        "language",
        "text",
        "display_text",
        "speech_text",
        "overall_intent",
        "global_voice_style",
        "segments",
        "rendering_hints",
    ],
    "properties": {
        "schema_version": {"type": "string", "const": SCHEMA_VERSION},
        "format": {"type": "string", "const": FORMAT_NAME},
        "language": {"type": "string", "minLength": 2},
        "text": {"type": "string"},
        "display_text": {"type": "string"},
        "speech_text": {"type": "string"},
        "overall_intent": {
            "type": "string",
            "enum": ["introduccion_humana", "interes_creciente", "interes_cerrado", "explicacion_controlada"],
        },
        "global_voice_style": {
            "type": "object",
            "additionalProperties": False,
            "required": ["persona", "base_pitch", "base_energy", "base_rate", "natural_variation"],
            "properties": {
                "persona": {"type": "string"},
                "base_pitch": {"type": "string"},
                "base_energy": {"type": "string"},
                "base_rate": {"type": "number"},
                "natural_variation": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["enabled", "pause_jitter_ms", "pitch_jitter_pct", "energy_jitter_db"],
                    "properties": {
                        "enabled": {"type": "boolean"},
                        "pause_jitter_ms": {
                            "type": "array",
                            "minItems": 2,
                            "maxItems": 2,
                            "items": {"type": "number"},
                        },
                        "pitch_jitter_pct": {
                            "type": "array",
                            "minItems": 2,
                            "maxItems": 2,
                            "items": {"type": "number"},
                        },
                        "energy_jitter_db": {
                            "type": "array",
                            "minItems": 2,
                            "maxItems": 2,
                            "items": {"type": "number"},
                        },
                    },
                },
                "pace_hint": {"type": "number"},
                "pause_density_hint": {"type": "number"},
            },
        },
        "segments": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "id",
                    "text",
                    "grammar_role",
                    "semantic_role",
                    "phrase_intent",
                    "emotion_level",
                    "semantic_weight",
                    "prosody",
                    "pause_after_ms",
                ],
                "properties": {
                    "id": {"type": "string"},
                    "text": {"type": "string"},
                    "grammar_role": {
                        "type": "string",
                        "enum": [
                            "subject",
                            "main_verb",
                            "auxiliary_verb",
                            "object_phrase",
                            "qualifying_adjective",
                            "connector",
                            "conceptual_close",
                        ],
                    },
                    "semantic_role": {"type": "string"},
                    "phrase_intent": {
                        "type": "string",
                        "enum": [
                            "flow_bridge",
                            "landing",
                            "contrast",
                            "explanation",
                            "passion",
                            "commitment",
                            "action",
                            "framing",
                            "color",
                            "accent",
                            "continuation",
                        ],
                    },
                    "emotion_level": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    "semantic_weight": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    "prosody": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": [
                            "pitch_shift_pct",
                            "energy_boost_db",
                            "rate_pct",
                            "duration_pct",
                            "vowel_stretch_pct",
                            "attack",
                            "emphasis_level",
                        ],
                        "properties": {
                            "pitch_shift_pct": {"type": "number"},
                            "energy_boost_db": {"type": "number"},
                            "rate_pct": {"type": "number"},
                            "duration_pct": {"type": "number"},
                            "vowel_stretch_pct": {"type": "number"},
                            "attack": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                            "emphasis_level": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                        },
                    },
                    "contour": {
                        "type": "object",
                        "additionalProperties": True,
                    },
                    "pause_after_ms": {"type": "integer", "minimum": 20, "maximum": 1500},
                },
            },
        },
        "rendering_hints": {
            "type": "object",
            "additionalProperties": False,
            "required": ["provider", "openvoice", "voice_profile"],
            "properties": {
                "provider": {"type": "string"},
                "openvoice": {"type": "object"},
                "voice_profile": {"type": "object"},
            },
        },
    },
}


def validate_pim_json(document: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a PIM-JSON document and return it unchanged if valid."""
    if not isinstance(document, dict):
        raise TypeError("PIM-JSON document must be a dictionary")

    if Draft202012Validator is None:  # pragma: no cover
        # Minimal fallback checks if jsonschema is unavailable.
        required = PIM_JSON_SCHEMA["required"]
        missing = [key for key in required if key not in document]
        if missing:
            raise ValueError(f"Missing required keys: {missing}")
        return document

    Draft202012Validator(PIM_JSON_SCHEMA).validate(document)
    return document


def pim_to_openvoice_overrides(document: Dict[str, Any]) -> Dict[str, Any]:
    """Map PIM-JSON into a practical OpenVoice config override set."""
    pim = validate_pim_json(document)
    hints = pim.get("rendering_hints", {}).get("openvoice", {}) or {}
    return deepcopy(hints)


def pim_to_voice_profile(document: Dict[str, Any]) -> Dict[str, Any]:
    """Return the higher-level voice profile used by the orchestrator."""
    pim = validate_pim_json(document)
    return deepcopy(pim.get("rendering_hints", {}).get("voice_profile", {}))


def dump_schema() -> str:
    return json.dumps(PIM_JSON_SCHEMA, indent=2, ensure_ascii=False)


def render_sample_text(text: str, output_path: str) -> Dict[str, Any]:
    """Build PIM-JSON, derive OpenVoice overrides, and render a sample audio file."""
    from tools.tts_tool import _generate_openvoice_v2, _load_tts_config

    pim = build_pim_json(text)
    validate_pim_json(pim)
    tts_config = _load_tts_config()
    tts_config = deepcopy(tts_config)
    tts_config.setdefault("provider", "openvoice")
    tts_config.setdefault("openvoice", {})
    tts_config["openvoice"].update(pim_to_openvoice_overrides(pim))
    _generate_openvoice_v2(text=pim["speech_text"], output_path=output_path, tts_config=tts_config)
    return {
        "pim": pim,
        "output_path": output_path,
        "voice_profile": pim_to_voice_profile(pim),
    }


if __name__ == "__main__":  # pragma: no cover
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Build and validate PIM-JSON")
    parser.add_argument("text", nargs="?", help="Text to convert into PIM-JSON")
    parser.add_argument("--schema", action="store_true", help="Print the JSON schema")
    parser.add_argument("--render", metavar="PATH", help="Render a sample voice file to PATH")
    args = parser.parse_args()

    if args.schema:
        print(dump_schema())
        raise SystemExit(0)

    if not args.text:
        parser.error("text is required unless --schema is used")

    pim = build_pim_json(args.text)
    validate_pim_json(pim)
    print(json.dumps(pim, indent=2, ensure_ascii=False))

    if args.render:
        render_sample_text(args.text, args.render)
        print(f"Rendered: {args.render}", file=sys.stderr)
