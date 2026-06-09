#!/usr/bin/env python3
"""Voice Orchestrator — shared voice pipeline for Hermes.

This module implements the voice architecture as a single coherent skill:

1. Voice Prompt Composer
2. Voice Response Validator
3. Voice Renderer (TTS synthesis)
4. Voice Emitter (platform-ready metadata)

The design keeps display text and speech text separate, so the caller can
show a rich textual response while speaking a cleaned-up oral version.
Identity profiling is intentionally configuration-driven and can be tuned later
without changing the pipeline shape.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

MAX_TEXT_LENGTH = 4000
DEFAULT_PLATFORM = "cli"
DEFAULT_VOICE_PROFILE = {
    "profile": "strategic_consultant",
    "speed": 0.96,
    "pause_density": 0.72,
    "authority": 0.84,
    "warmth": 0.30,
    "intonation_variation": 0.88,
    "smile_onset": True,
    "allow_fillers": False,
    "allow_breaths": True,
    "allow_soft_laughter": True,
    "dialogue_posture": "professional_trust",
    "communication_quality": "high",
    "voice_age": "adult_fresh",
    "youthfulness": 0.34,
    "accent_hint": "sur_de_espana_sutil",
}
DEFAULT_STYLE_PROFILE = {
    "mode": "strategic_consultant",
    "depth": 0.8,
    "technicality": 0.36,
    "conciseness": 0.64,
    "counterpoint": 0.62,
    "stance": "formed_opinion",
    "analysis_frame": "factorized",
    "translation_mode": "complex_to_simple",
    "clarity_priority": 0.95,
    "persuasive_capacity": 0.74,
}
DEFAULT_IDENTITY_PROFILE = {
    "name": "Laia",
    "persona": "executive_cognitive_assistant",
    "voice_identity": "strategic_consultant",
    "voice_reference": "voice_9",
    "relationship_model": "professional_trust_with_dialogue",
    "voice_characteristics": [
        "strategic_and_precise",
        "resolutive",
        "clear_with_boundaries",
        "authoritative_not_colloquial",
        "consultative_not_friendly",
        "dialogic_but_opinionated",
        "proactive_with_alternatives",
        "strategic_and_communicative",
        "complex_to_simple",
        "pragmatic_and_factorized",
        "convincing_without_jargon",
    ],
}
DEFAULT_POLICY = {
    "separate_display_and_speech": True,
    "avoid_literal_urls": True,
    "avoid_literal_endpoints": True,
    "avoid_literal_json": True,
    "avoid_literal_code": True,
    "allow_reflective_pauses": True,
    "allow_micro_fillers": False,
    "allow_breath_events": False,
    "prefer_short_opening": True,
    "preserve_display_text": True,
}

_STAGE_1_ROUTES = {"analysis", "execution"}


class VoiceStage1ChannelGate:
    """Stage 1: classify channel, source kind, and route.

    This gate is intentionally tiny and deterministic: it decides whether the
    input is text or audio, whether the voice trigger is active, and whether the
    route should be analysis or execution.
    """

    stage_name = "stage_1_channel_gate"

    def execute(
        self,
        text: str = "",
        audio_path: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        context = dict(context or {})
        has_audio = bool(audio_path)
        source_kind = "audio" if has_audio else "text"
        input_channel = "voice" if has_audio else "text"

        explicit_route = str(context.get("interaction_route") or context.get("session_route") or "").strip().lower()
        if explicit_route in _STAGE_1_ROUTES:
            route = explicit_route
            route_reason = "context_explicit_route"
        else:
            route = "analysis"
            route_reason = "default_analysis"

        return {
            "stage": self.stage_name,
            "input_channel": input_channel,
            "voice_trigger": has_audio,
            "source_kind": source_kind,
            "route": route,
            "route_reason": route_reason,
            "text_present": bool((text or "").strip()),
            "audio_path": audio_path,
            "context": context,
        }


_STAGE_1_GATE = VoiceStage1ChannelGate()


class VoiceStage2ContextMemory:
    """Stage 2: recover only the context that is useful for the current turn.

    The goal is to keep token usage low while preserving the information that
    actually shapes the response: route, topic, theme, and minimal memory hints.
    """

    stage_name = "stage_2_context_memory"
    _useful_keys = (
        "interaction_route",
        "route_reason",
        "topic",
        "theme",
        "current_topic",
        "topic_epoch",
        "current_goal",
        "intent",
        "voice_trigger",
        "source_kind",
        "input_channel",
    )

    def execute(
        self,
        text: str = "",
        context: Optional[Dict[str, Any]] = None,
        stage1: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        context = dict(context or {})
        stage1 = dict(stage1 or {})

        compact_context: Dict[str, Any] = {}
        for key in self._useful_keys:
            if key in context and context.get(key) is not None:
                compact_context[key] = context[key]

        if stage1:
            compact_context.setdefault("route", stage1.get("route"))
            compact_context.setdefault("voice_trigger", stage1.get("voice_trigger"))
            compact_context.setdefault("source_kind", stage1.get("source_kind"))
            compact_context.setdefault("input_channel", stage1.get("input_channel"))
            compact_context.setdefault("stage1_route", stage1.get("route"))
            compact_context.setdefault("stage1_route_reason", stage1.get("route_reason"))

        if not compact_context.get("interaction_route") and stage1.get("route"):
            compact_context["interaction_route"] = stage1["route"]

        memory_hints: list[str] = []
        if compact_context.get("topic"):
            memory_hints.append(f"topic={compact_context['topic']}")
        if compact_context.get("theme"):
            memory_hints.append(f"theme={compact_context['theme']}")
        if compact_context.get("current_goal"):
            memory_hints.append(f"goal={compact_context['current_goal']}")
        if compact_context.get("intent"):
            memory_hints.append(f"intent={compact_context['intent']}")

        summary_bits = []
        for key in ("interaction_route", "route_reason", "topic", "theme", "current_goal", "voice_trigger", "source_kind"):
            value = compact_context.get(key)
            if value is not None and value != "":
                summary_bits.append(f"{key}={value}")

        return {
            "stage": self.stage_name,
            "text_present": bool((text or "").strip()),
            "context_summary": compact_context,
            "memory_hints": memory_hints,
            "summary": " | ".join(summary_bits),
        }


_STAGE_2_MEMORY = VoiceStage2ContextMemory()


class VoiceStage3ModeDetector:
    """Stage 3: infer the conversational mode from route and lexical cues."""

    stage_name = "stage_3_mode_detector"

    _reflective_markers = (
        "sinceramente",
        "me sorprende",
        "no es que",
        "después de todo",
        "todavía sigas",
        "me parece",
        "me da la impresión",
        "mmm",
        "…",
        "...",
    )
    _executive_markers = (
        "hazlo",
        "cierra",
        "ejecuta",
        "envía",
        "marca",
        "pon",
        "ahora",
        "ya",
    )

    def execute(
        self,
        text: str = "",
        context: Optional[Dict[str, Any]] = None,
        stage1: Optional[Dict[str, Any]] = None,
        stage2: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        context = dict(context or {})
        stage1 = dict(stage1 or {})
        stage2 = dict(stage2 or {})
        normalized = (text or "").strip().lower()
        route = str(stage1.get("route") or context.get("interaction_route") or "").strip().lower()

        if route == "execution":
            mode = "executive"
            tone = "executive"
            mode_reason = "explicit_execution_route"
        elif any(marker in normalized for marker in self._reflective_markers):
            mode = "reflective"
            tone = "reflective"
            mode_reason = "reflective_markers"
        elif any(marker in normalized for marker in self._executive_markers):
            mode = "executive"
            tone = "executive"
            mode_reason = "executive_markers"
        elif "hola" in normalized and "ayudarte" in normalized:
            mode = "strategic"
            tone = "strategic"
            mode_reason = "greeting_strategy"
        elif "?" in (text or "") or "por qué" in normalized or "como" in normalized:
            mode = "analytical"
            tone = "analytical"
            mode_reason = "questioning_markers"
        else:
            mode = "strategic"
            tone = "strategic"
            mode_reason = "default_strategic"

        voice_profile_patch = {
            "speed": 0.96,
            "pause_density": 0.72,
            "authority": 0.84,
            "warmth": 0.30,
            "intonation_variation": 0.88,
            "allow_breaths": True,
            "allow_fillers": False,
            "dialogue_posture": "professional_trust",
            "communication_quality": "high",
        }
        style_profile_patch = {
            "mode": "strategic_consultant",
            "depth": 0.80,
            "technicality": 0.36,
            "conciseness": 0.64,
            "counterpoint": 0.62,
            "stance": "formed_opinion",
            "analysis_frame": "factorized",
            "translation_mode": "complex_to_simple",
            "clarity_priority": 0.95,
            "persuasive_capacity": 0.74,
        }

        if mode == "reflective":
            voice_profile_patch.update({
                "speed": 0.89,
                "pause_density": 0.76,
                "authority": 0.78,
                "warmth": 0.38,
                "intonation_variation": 0.52,
            })
            style_profile_patch.update({
                "depth": 0.92,
                "conciseness": 0.56,
                "counterpoint": 0.68,
                "stance": "exploratory_questioning",
            })
        elif mode == "executive":
            voice_profile_patch.update({
                "speed": 1.03,
                "pause_density": 0.54,
                "authority": 0.91,
                "warmth": 0.20,
                "intonation_variation": 0.68,
                "allow_breaths": False,
            })
            style_profile_patch.update({
                "depth": 0.58,
                "conciseness": 0.82,
                "counterpoint": 0.32,
                "stance": "decisive",
                "analysis_frame": "action_first",
                "persuasive_capacity": 0.72,
            })
        elif mode == "analytical":
            voice_profile_patch.update({
                "speed": 0.92,
                "pause_density": 0.78,
                "authority": 0.78,
                "warmth": 0.35,
                "intonation_variation": 0.74,
            })
            style_profile_patch.update({
                "depth": 0.95,
                "conciseness": 0.50,
                "counterpoint": 0.78,
                "stance": "exploratory_questioning",
            })

        return {
            "stage": self.stage_name,
            "mode": mode,
            "tone": tone,
            "mode_reason": mode_reason,
            "voice_profile_patch": voice_profile_patch,
            "style_profile_patch": style_profile_patch,
            "stage1_route": stage1.get("route"),
            "stage2_summary": stage2.get("summary"),
            "route": route,
        }


_STAGE_3_MODE = VoiceStage3ModeDetector()


class VoiceStage4SemanticSanitizer:
    """Stage 4: convert technical noise into speech-safe semantic language."""

    stage_name = "stage_4_semantic_sanitizer"

    _url_re = re.compile(r"https?://[^\s)]+", flags=re.IGNORECASE)
    _endpoint_re = re.compile(r"\b(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+(/[^\s,;]+)", flags=re.IGNORECASE)
    _inline_code_re = re.compile(r"`([^`]+)`")
    _json_blob_re = re.compile(r"\{[^{}]*\}")
    _file_path_re = re.compile(r"(?:/|[A-Za-z]:\\)[^\s,;]+")

    def _summarize_technical_item(self, match_text: str) -> str:
        text = match_text.strip()
        lower = text.lower()
        if self._url_re.fullmatch(text):
            return "el sitio"
        if self._endpoint_re.fullmatch(text):
            path = self._endpoint_re.fullmatch(text).group(2)  # type: ignore[union-attr]
            if any(key in path.lower() for key in ("login", "auth", "signin")):
                return "el login"
            if any(key in path.lower() for key in ("ticket", "close")):
                return "el ticket"
            return "el endpoint"
        if self._inline_code_re.fullmatch(text):
            return self._summarize_inline_code(self._inline_code_re.fullmatch(text).group(1))  # type: ignore[union-attr]
        if self._json_blob_re.fullmatch(text):
            if "token" in lower:
                return "un token"
            if "url" in lower or "endpoint" in lower:
                return "un dato técnico"
            return "un bloque técnico"
        if self._file_path_re.fullmatch(text):
            return "una ruta"
        return "un dato técnico"

    def _summarize_inline_code(self, code: str) -> str:
        lower = code.lower().strip()
        if lower in {"codigo", "code"}:
            return "el código"
        if lower in {"login", "signin"}:
            return "el login"
        if lower in {"token"}:
            return "un token"
        if lower.startswith("/"):
            return self._summarize_technical_item(lower)
        return "el detalle técnico"

    def execute(
        self,
        text: str = "",
        context: Optional[Dict[str, Any]] = None,
        stage1: Optional[Dict[str, Any]] = None,
        stage2: Optional[Dict[str, Any]] = None,
        stage3: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        original_text = (text or "").strip()
        sanitized = original_text
        technical_items: list[Dict[str, Any]] = []

        def _collect(kind: str, value: str, replacement: str) -> None:
            technical_items.append({"kind": kind, "value": value, "replacement": replacement})

        for pattern, kind in (
            (self._url_re, "url"),
            (self._endpoint_re, "endpoint"),
            (self._inline_code_re, "code"),
            (self._json_blob_re, "json"),
            (self._file_path_re, "path"),
        ):
            while True:
                match = pattern.search(sanitized)
                if not match:
                    break
                raw = match.group(0)
                replacement = self._summarize_technical_item(raw)
                _collect(kind, raw, replacement)
                sanitized = sanitized[: match.start()] + replacement + sanitized[match.end() :]

        sanitized = re.sub(r"\s+", " ", sanitized).strip()
        sanitized = re.sub(r"\s+([,.;:!?])", r"\1", sanitized)
        sanitized = re.sub(r"\bPOST\b|\bGET\b|\bPUT\b|\bPATCH\b|\bDELETE\b|\bHEAD\b|\bOPTIONS\b", "", sanitized, flags=re.IGNORECASE)
        sanitized = re.sub(r"\s{2,}", " ", sanitized).strip()

        semantic_policy = {
            "summarize_technical_items": True,
            "preserve_emotional_phrase": True,
            "avoid_literal_urls": True,
            "avoid_literal_endpoints": True,
            "avoid_literal_json": True,
            "avoid_literal_code": True,
        }
        rendering_hints = {
            "do_not_read_technical_items_verbatim": True,
            "prefer_semantic_summary": True,
            "preserve_rhythm_on_nontechnical_text": True,
        }

        return {
            "stage": self.stage_name,
            "original_text": original_text,
            "sanitized_display_text": sanitized,
            "speech_text": sanitized,
            "technical_items": technical_items,
            "semantic_policy": semantic_policy,
            "rendering_hints": rendering_hints,
            "stage1_route": (stage1 or {}).get("route"),
            "stage2_summary": (stage2 or {}).get("summary"),
            "stage3_mode": (stage3 or {}).get("mode"),
        }


_STAGE_4_SANITIZER = VoiceStage4SemanticSanitizer()


class VoiceStage5SpeechPlanner:
    """Stage 5: turn sanitized text into a structured oral script."""

    stage_name = "stage_5_speech_planner"

    def _split_reflective(self, text: str) -> list[str]:
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            return []
        opening = ""
        rest = text
        m = re.match(r"^(Mira…|Mira\.\.\.|Mira\.)[, ]*(.*)$", text, flags=re.IGNORECASE)
        if m:
            opening = m.group(1).strip()
            rest = m.group(2).strip()
        parts = [p.strip() for p in re.split(r"(?<=[,;:.!?…])\s+|\s*,\s*", rest) if p.strip()]
        segments = []
        if opening:
            segments.append(opening)
        for part in parts:
            if part and part not in segments:
                segments.append(part)
        return segments or ([text] if text else [])

    def _split_executive(self, text: str) -> list[str]:
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            return []
        parts = [p.strip() for p in re.split(r"\s+y\s+|\s*,\s*", text) if p.strip()]
        if len(parts) <= 2:
            return parts or [text]
        return [parts[0], "y " + " y ".join(parts[1:])]

    def execute(
        self,
        text: str = "",
        context: Optional[Dict[str, Any]] = None,
        stage1: Optional[Dict[str, Any]] = None,
        stage2: Optional[Dict[str, Any]] = None,
        stage3: Optional[Dict[str, Any]] = None,
        stage4: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        context = dict(context or {})
        stage3 = dict(stage3 or {})
        stage4 = dict(stage4 or {})
        mode = str(stage3.get("mode") or "strategic").strip().lower()
        sanitized_text = (stage4.get("speech_text") or text or "").strip()

        if mode == "reflective":
            segments = self._split_reflective(sanitized_text)
            opening_style = "reflective"
            separator = "\n\n"
            opening = segments[0] if segments else ""
        elif mode == "executive":
            segments = self._split_executive(sanitized_text)
            opening_style = "direct"
            separator = "\n"
            opening = segments[0] if segments else ""
        else:
            segments = [p.strip() for p in re.split(r"(?<=[.!?…])\s+", sanitized_text) if p.strip()] or [sanitized_text]
            opening_style = "strategic"
            separator = "\n"
            opening = segments[0] if segments else ""

        if not segments:
            segments = [sanitized_text]

        pauses_ms = []
        for idx in range(max(0, len(segments) - 1)):
            if mode == "reflective":
                pauses_ms.append(320 if idx == 0 else 260)
            elif mode == "executive":
                pauses_ms.append(180)
            else:
                pauses_ms.append(240)

        speech_script = {
            "segments": segments,
            "segment_count": len(segments),
            "pauses_ms": pauses_ms,
            "separator": separator,
            "opening": opening,
        }
        render_text = separator.join(segments).strip()
        speech_plan = {
            "opening_style": opening_style,
            "mode": mode,
            "segment_count": len(segments),
            "segments": segments,
            "pauses_ms": pauses_ms,
            "render_text": render_text,
        }

        return {
            "stage": self.stage_name,
            "mode": mode,
            "opening": opening,
            "speech_script": speech_script,
            "speech_plan": speech_plan,
            "render_text": render_text,
            "stage1_route": (stage1 or {}).get("route"),
            "stage2_summary": (stage2 or {}).get("summary"),
            "stage4_sanitized_text": stage4.get("sanitized_display_text"),
        }


_STAGE_5_PLANNER = VoiceStage5SpeechPlanner()


class VoiceStage6DualChannelFusion:
    """Stage 6: keep a fast reactive channel alongside the analytical plan."""

    stage_name = "stage_6_dual_channel_fusion"

    def execute(
        self,
        text: str = "",
        context: Optional[Dict[str, Any]] = None,
        stage1: Optional[Dict[str, Any]] = None,
        stage2: Optional[Dict[str, Any]] = None,
        stage3: Optional[Dict[str, Any]] = None,
        stage4: Optional[Dict[str, Any]] = None,
        stage5: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        context = dict(context or {})
        stage1 = dict(stage1 or {})
        stage2 = dict(stage2 or {})
        stage3 = dict(stage3 or {})
        stage4 = dict(stage4 or {})
        stage5 = dict(stage5 or {})

        mode = str(stage3.get("mode") or stage5.get("mode") or "strategic").strip().lower()
        route = str(stage1.get("route") or context.get("interaction_route") or "").strip().lower()
        voice_trigger = bool(context.get("voice_trigger") or stage1.get("voice_trigger") or stage4.get("source_kind") == "audio")
        text_present = bool((text or "").strip())

        if mode == "executive" or route == "execution":
            ack_text = "Vale"
            latency_ms = 120
        elif mode == "reflective":
            ack_text = "Entiendo"
            latency_ms = 160
        elif mode == "analytical":
            ack_text = "Ajá"
            latency_ms = 150
        else:
            ack_text = "Entiendo"
            latency_ms = 140

        if voice_trigger:
            latency_ms = min(latency_ms, 140)
        if text_present and len(text) > 120:
            latency_ms = min(latency_ms + 20, 180)

        reactive_channel = {
            "enabled": True,
            "ack_text": ack_text,
            "latency_ms": latency_ms,
            "delivery_mode": "front_channel",
            "purpose": "presence_and_ack",
            "should_audibilize": False,
        }
        analytical_channel = {
            "enabled": True,
            "mode": mode,
            "speech_script": stage5.get("speech_script", {}),
            "render_text": stage5.get("render_text") or stage4.get("speech_text") or text,
            "stage5_opening": stage5.get("opening"),
        }
        fusion_policy = {
            "parallel_channels": True,
            "preserve_reference_phrase": True,
            "reactive_channel_first": True,
            "analysis_channel_continues": True,
            "reactive_ack_visible_only_in_streaming": True,
            "do_not_change_reference_audio_text": True,
        }

        return {
            "stage": self.stage_name,
            "mode": mode,
            "route": route,
            "reactive_channel": reactive_channel,
            "analytical_channel": analytical_channel,
            "fusion_policy": fusion_policy,
            "render_text": analytical_channel["render_text"],
            "stage1_route": stage1.get("route"),
            "stage2_summary": stage2.get("summary"),
            "stage5_opening": stage5.get("opening"),
        }


_STAGE_6_DUAL_CHANNEL = VoiceStage6DualChannelFusion()


class VoiceStage7FineProsody:
    """Stage 7: fine-grained prosody control for clause-level cadence."""

    stage_name = "stage_7_fine_prosody"

    _pause_markers = ("sin embargo", "además", "de hecho", "por eso", "entonces", "sinceramente", "después de todo")

    def _segment_reflective(self, text: str) -> list[str]:
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            return []
        segments = [s.strip() for s in re.split(r"\n+", text) if s.strip()]
        if len(segments) <= 1:
            segments = [s.strip() for s in re.split(r"(?<=[,;:.!?…])\s+", text) if s.strip()]
        refined: list[str] = []
        for segment in segments:
            if not refined:
                refined.append(segment)
                continue
            if segment.lower().startswith("es que") or segment.lower().startswith("y "):
                refined.append(segment)
            else:
                refined.append(segment)
        return refined or [text]

    def _build_render_text(self, segments: list[str], mode: str) -> str:
        if not segments:
            return ""
        if mode == "reflective":
            lines: list[str] = []
            for idx, seg in enumerate(segments):
                seg = seg.strip()
                if not seg:
                    continue
                if idx == 0:
                    lines.append(seg)
                elif idx < len(segments) - 1:
                    if not seg.endswith((",", ";", ":", "…")):
                        seg = f"{seg},"
                    lines.append(seg)
                else:
                    lines.append(seg)
            return "\n\n".join(lines)
        if mode == "executive":
            if len(segments) <= 2:
                return "\n".join(segments)
            return "\n".join([segments[0], "y " + " y ".join(segments[1:])])
        return "\n".join(segments)

    def execute(
        self,
        text: str = "",
        context: Optional[Dict[str, Any]] = None,
        stage1: Optional[Dict[str, Any]] = None,
        stage2: Optional[Dict[str, Any]] = None,
        stage3: Optional[Dict[str, Any]] = None,
        stage4: Optional[Dict[str, Any]] = None,
        stage5: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        context = dict(context or {})
        stage3 = dict(stage3 or {})
        stage4 = dict(stage4 or {})
        stage5 = dict(stage5 or {})

        mode = str(stage3.get("mode") or stage5.get("mode") or "strategic").strip().lower()
        source_text = (stage5.get("render_text") or stage4.get("speech_text") or text or "").strip()
        segments = list(stage5.get("speech_script", {}).get("segments") or [])
        if not segments:
            segments = self._segment_reflective(source_text)

        clause_count = max(0, len(segments) - 1)
        pause_bands: list[int] = []
        for idx in range(clause_count):
            if mode == "reflective":
                pause_bands.append(340 if idx == 0 else 280 if idx < clause_count - 1 else 240)
            elif mode == "executive":
                pause_bands.append(160 if idx == 0 else 140)
            else:
                pause_bands.append(220)

        if mode == "reflective":
            prosody_profile_patch = {
                "speed": 0.92,
                "pause_density": 0.86,
                "authority": 0.81,
                "warmth": 0.34,
                "intonation_variation": 0.56,
                "allow_breaths": True,
                "allow_fillers": False,
            }
            cadence = "reflective"
            pitch_profile = {"pitch_contour_strength": 0.0, "pitch_enabled": False}
        elif mode == "executive":
            prosody_profile_patch = {
                "speed": 1.04,
                "pause_density": 0.62,
                "authority": 0.93,
                "warmth": 0.18,
                "intonation_variation": 0.68,
                "allow_breaths": False,
                "allow_fillers": False,
            }
            cadence = "direct"
            pitch_profile = {"pitch_contour_strength": 0.0, "pitch_enabled": False}
        else:
            prosody_profile_patch = {
                "speed": 0.94,
                "pause_density": 0.74,
                "authority": 0.80,
                "warmth": 0.28,
                "intonation_variation": 0.62,
                "allow_breaths": True,
                "allow_fillers": False,
            }
            cadence = "strategic"
            pitch_profile = {"pitch_contour_strength": 0.0, "pitch_enabled": False}

        render_text = self._build_render_text(segments, mode)
        prosody_map = {
            "cadence": cadence,
            "clause_count": clause_count,
            "pause_bands_ms": pause_bands,
            "opening_emphasis": segments[0] if segments else "",
            "closing_emphasis": segments[-1] if segments else "",
            "reference_phrase_preserved": True,
            "pause_markers": [marker for marker in self._pause_markers if marker in source_text.lower()],
        }
        render_hints = {
            "prefer_clause_breaks": True,
            "prefer_commas_over_flat_pause": True,
            "preserve_reference_phrase": True,
            "avoid_pitch_spike": True,
        }

        return {
            "stage": self.stage_name,
            "mode": mode,
            "render_text": render_text,
            "prosody_profile_patch": {**prosody_profile_patch, **pitch_profile},
            "prosody_map": prosody_map,
            "render_hints": render_hints,
            "stage1_route": (stage1 or {}).get("route"),
            "stage2_summary": (stage2 or {}).get("summary"),
            "stage5_opening": (stage5 or {}).get("opening"),
        }


_STAGE_7_FINE_PROSODY = VoiceStage7FineProsody()


class VoiceStage8QualityValidator:
    """Stage 8: validate audio safety and quality before delivery."""

    stage_name = "stage_8_quality_validator"

    _technical_patterns = (
        re.compile(r"https?://[^\s)]+", flags=re.IGNORECASE),
        re.compile(r"\b(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+(/[^\s,;]+)", flags=re.IGNORECASE),
        re.compile(r"\{[^{}]*\}"),
        re.compile(r"`[^`]+`"),
        re.compile(r"(?:/|[A-Za-z]:\\)[^\s,;]+"),
    )

    def _detect_technical_noise(self, text: str) -> bool:
        return any(pattern.search(text) for pattern in self._technical_patterns)

    def execute(
        self,
        text: str = "",
        context: Optional[Dict[str, Any]] = None,
        stage1: Optional[Dict[str, Any]] = None,
        stage2: Optional[Dict[str, Any]] = None,
        stage3: Optional[Dict[str, Any]] = None,
        stage4: Optional[Dict[str, Any]] = None,
        stage5: Optional[Dict[str, Any]] = None,
        stage6: Optional[Dict[str, Any]] = None,
        stage7: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        context = dict(context or {})
        stage4 = dict(stage4 or {})
        stage5 = dict(stage5 or {})
        stage6 = dict(stage6 or {})
        stage7 = dict(stage7 or {})

        display_text = (stage4.get("sanitized_display_text") or text or "").strip()
        speech_text = (stage4.get("speech_text") or display_text or "").strip()
        render_text = (stage5.get("render_text") or speech_text or "").strip()
        technical_noise_detected = self._detect_technical_noise(display_text) or self._detect_technical_noise(speech_text) or self._detect_technical_noise(render_text)
        reference_phrase = "mira" in render_text.lower() and "me sorprende" in render_text.lower()
        stage7_map = stage7.get("prosody_map") or {}
        clause_count = int(stage7_map.get("clause_count") or max(0, len([s for s in render_text.splitlines() if s.strip()]) - 1))
        has_clause_breaks = "\n\n" in render_text or clause_count >= 3
        has_dual_channel = bool((stage6.get("fusion_policy") or {}).get("parallel_channels"))
        no_empty_render = bool(render_text.strip())
        audio_safe = not technical_noise_detected and no_empty_render and has_dual_channel and reference_phrase

        quality_checks = {
            "technical_noise_detected": technical_noise_detected,
            "reference_phrase_preserved": reference_phrase,
            "clause_breaks_present": has_clause_breaks,
            "dual_channel_present": has_dual_channel,
            "render_text_nonempty": no_empty_render,
            "speech_safe": not technical_noise_detected,
        }
        quality_score = 0.0
        quality_score += 0.35 if not technical_noise_detected else 0.0
        quality_score += 0.25 if reference_phrase else 0.0
        quality_score += 0.15 if has_clause_breaks else 0.0
        quality_score += 0.15 if has_dual_channel else 0.0
        quality_score += 0.10 if no_empty_render else 0.0
        quality_score = round(min(1.0, quality_score), 2)

        warnings: list[str] = []
        if technical_noise_detected:
            warnings.append("technical_noise_detected")
        if not reference_phrase:
            warnings.append("reference_phrase_not_preserved")
        if not has_clause_breaks:
            warnings.append("missing_clause_breaks")
        if not has_dual_channel:
            warnings.append("dual_channel_missing")
        if not no_empty_render:
            warnings.append("empty_render_text")

        quality_policy = {
            "allow_audio_delivery": audio_safe,
            "allow_text_fallback": True,
            "fallback_priority": "text_only" if not audio_safe else "audio_ok",
            "strict_mode": True,
            "min_quality_score": 0.85,
        }
        fallback_recommendation = "audio" if audio_safe else "text_only"

        return {
            "stage": self.stage_name,
            "audio_safe": audio_safe,
            "quality_score": quality_score,
            "quality_checks": quality_checks,
            "quality_policy": quality_policy,
            "warnings": warnings,
            "fallback_recommendation": fallback_recommendation,
            "stage1_route": (stage1 or {}).get("route"),
            "stage2_summary": (stage2 or {}).get("summary"),
            "stage7_cadence": stage7_map.get("cadence"),
            "render_text": render_text,
        }


_STAGE_8_QUALITY = VoiceStage8QualityValidator()


class VoiceStage9StageComparator:
    """Stage 9: compare the accumulated stages and detect regressions."""

    stage_name = "stage_9_stage_comparator"

    def _stage_status(self, stage: Dict[str, Any], key: str, default: Any = None) -> Any:
        if not isinstance(stage, dict):
            return default
        return stage.get(key, default)

    def execute(
        self,
        text: str = "",
        context: Optional[Dict[str, Any]] = None,
        stage1: Optional[Dict[str, Any]] = None,
        stage2: Optional[Dict[str, Any]] = None,
        stage3: Optional[Dict[str, Any]] = None,
        stage4: Optional[Dict[str, Any]] = None,
        stage5: Optional[Dict[str, Any]] = None,
        stage6: Optional[Dict[str, Any]] = None,
        stage7: Optional[Dict[str, Any]] = None,
        stage8: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        context = dict(context or {})
        stage1 = dict(stage1 or {})
        stage2 = dict(stage2 or {})
        stage3 = dict(stage3 or {})
        stage4 = dict(stage4 or {})
        stage5 = dict(stage5 or {})
        stage6 = dict(stage6 or {})
        stage7 = dict(stage7 or {})
        stage8 = dict(stage8 or {})

        original_text = (text or "").strip()
        display_text = (stage4.get("sanitized_display_text") or original_text).strip()
        speech_text = (stage4.get("speech_text") or display_text).strip()
        render_text = (stage7.get("render_text") or stage5.get("render_text") or speech_text).strip()

        stage_snapshots = {
            "stage1": {
                "route": stage1.get("route"),
                "route_reason": stage1.get("route_reason"),
                "voice_trigger": stage1.get("voice_trigger"),
            },
            "stage2": {
                "summary": stage2.get("summary"),
                "source_kind": stage2.get("source_kind"),
            },
            "stage3": {
                "mode": stage3.get("mode"),
                "voice_profile_patch": stage3.get("voice_profile_patch", {}),
            },
            "stage4": {
                "technical_items": len(stage4.get("technical_items") or []),
                "sanitized_changed": display_text != original_text,
            },
            "stage5": {
                "segment_count": int(stage5.get("speech_script", {}).get("segment_count") or 0),
                "opening": stage5.get("opening"),
            },
            "stage6": {
                "parallel_channels": bool((stage6.get("fusion_policy") or {}).get("parallel_channels")),
                "ack_text": (stage6.get("reactive_channel") or {}).get("ack_text"),
            },
            "stage7": {
                "cadence": (stage7.get("prosody_map") or {}).get("cadence"),
                "clause_count": int((stage7.get("prosody_map") or {}).get("clause_count") or 0),
            },
            "stage8": {
                "audio_safe": bool(stage8.get("audio_safe")),
                "quality_score": float(stage8.get("quality_score") or 0.0),
            },
        }

        comparisons: list[dict[str, Any]] = []
        regressions: list[str] = []

        def add_comparison(name: str, before: Any, after: Any, improvement: bool = False) -> None:
            changed = before != after
            if changed:
                direction = "improved" if improvement else "changed"
            else:
                direction = "stable"
            comparisons.append({"name": name, "before": before, "after": after, "direction": direction})

        add_comparison("sanitization", original_text, display_text, improvement=display_text != original_text)
        add_comparison("speech_planning", speech_text, render_text, improvement=bool(render_text and render_text != speech_text))
        add_comparison("reactive_channel", None, (stage6.get("reactive_channel") or {}).get("ack_text"), improvement=True)
        add_comparison("prosody_refinement", stage5.get("render_text"), render_text, improvement=bool(render_text))
        add_comparison("quality_gate", None, stage8.get("audio_safe"), improvement=bool(stage8.get("audio_safe")))

        if stage4.get("technical_items") and not stage8.get("audio_safe"):
            regressions.append("technical_noise_persisted")
        if not stage6.get("fusion_policy", {}).get("parallel_channels"):
            regressions.append("dual_channel_missing")
        if not stage8.get("audio_safe"):
            regressions.append("audio_not_safe")
        if not stage8.get("quality_checks", {}).get("reference_phrase_preserved", False):
            regressions.append("reference_phrase_lost")

        improvement_score = 0.0
        improvement_score += 0.20 if stage_snapshots["stage4"]["sanitized_changed"] else 0.0
        improvement_score += 0.15 if stage5.get("speech_script", {}).get("segment_count", 0) >= 2 else 0.0
        improvement_score += 0.15 if stage6.get("fusion_policy", {}).get("parallel_channels") else 0.0
        improvement_score += 0.15 if stage7.get("prosody_map", {}).get("clause_count", 0) >= 3 else 0.0
        improvement_score += 0.20 if stage8.get("quality_checks", {}).get("reference_phrase_preserved", False) else 0.0
        improvement_score += 0.15 if stage8.get("audio_safe") else 0.0
        improvement_score += float(stage8.get("quality_score") or 0.0) * 0.10
        improvement_score = round(min(1.0, improvement_score), 2)

        readiness = {
            "ready_for_audio": bool(stage8.get("audio_safe")) and not regressions,
            "stable_progression": not regressions,
            "quality_score": stage8.get("quality_score", 0.0),
            "improvement_score": improvement_score,
            "reference_phrase_preserved": stage8.get("quality_checks", {}).get("reference_phrase_preserved", False),
        }

        report = {
            "stage": self.stage_name,
            "stage_order": [f"stage_{i}" for i in range(1, 9)],
            "stage_snapshots": stage_snapshots,
            "comparisons": comparisons,
            "regressions": regressions,
            "readiness": readiness,
            "comparison_policy": {
                "stable_by_stages": True,
                "prefer_incremental_changes": True,
                "preserve_reference_phrase": True,
                "reject_technical_noise_regressions": True,
            },
            "stage1_route": stage1.get("route"),
            "stage2_summary": stage2.get("summary"),
            "stage8_audio_safe": stage8.get("audio_safe"),
        }
        return report


_STAGE_9_COMPARATOR = VoiceStage9StageComparator()


class VoiceStage10ProductionHardening:
    """Stage 10: lock the release decision and enforce production fallback."""

    stage_name = "stage_10_production_hardening"

    def execute(
        self,
        text: str = "",
        context: Optional[Dict[str, Any]] = None,
        stage1: Optional[Dict[str, Any]] = None,
        stage2: Optional[Dict[str, Any]] = None,
        stage3: Optional[Dict[str, Any]] = None,
        stage4: Optional[Dict[str, Any]] = None,
        stage5: Optional[Dict[str, Any]] = None,
        stage6: Optional[Dict[str, Any]] = None,
        stage7: Optional[Dict[str, Any]] = None,
        stage8: Optional[Dict[str, Any]] = None,
        stage9: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        context = dict(context or {})
        stage1 = dict(stage1 or {})
        stage2 = dict(stage2 or {})
        stage3 = dict(stage3 or {})
        stage4 = dict(stage4 or {})
        stage5 = dict(stage5 or {})
        stage6 = dict(stage6 or {})
        stage7 = dict(stage7 or {})
        stage8 = dict(stage8 or {})
        stage9 = dict(stage9 or {})

        ready_for_audio = bool((stage9.get("readiness") or {}).get("ready_for_audio"))
        stable_progression = bool((stage9.get("readiness") or {}).get("stable_progression"))
        audio_safe = bool(stage8.get("audio_safe"))
        regressions = list(stage9.get("regressions") or [])
        route = str(stage1.get("route") or context.get("interaction_route") or "analysis").strip().lower()
        mode = str(stage3.get("mode") or "strategic").strip().lower()
        preferred_delivery = "audio" if ready_for_audio and audio_safe and stable_progression else "text"
        fallback_mode = "none" if preferred_delivery == "audio" else "text_only"
        release_decision = "go_live" if preferred_delivery == "audio" else "text_only"
        locked = True

        contract = {
            "contract_version": "1.0.0",
            "strict_mode": True,
            "route": route,
            "mode": mode,
            "delivery_policy": {
                "prefer_audio_when_safe": True,
                "fallback_to_text": True,
                "no_silent_failure": True,
                "no_production_guessing": True,
            },
            "rendering_contract": {
                "preserve_reference_phrase": True,
                "preserve_display_text": True,
                "keep_dual_channel": bool((stage6.get("fusion_policy") or {}).get("parallel_channels")),
                "keep_quality_gate": audio_safe,
            },
        }

        release_checks = {
            "audio_safe": audio_safe,
            "ready_for_audio": ready_for_audio,
            "stable_progression": stable_progression,
            "regressions": regressions,
            "quality_score": stage8.get("quality_score", 0.0),
            "reference_phrase_preserved": bool((stage9.get("readiness") or {}).get("reference_phrase_preserved")),
            "parallel_channels": bool((stage6.get("fusion_policy") or {}).get("parallel_channels")),
        }

        output_policy = {
            "delivery_mode": preferred_delivery,
            "fallback_mode": fallback_mode,
            "locked": locked,
            "release_decision": release_decision,
            "strict_text_fallback": True,
            "no_audio_when_not_safe": True,
        }

        return {
            "stage": self.stage_name,
            "release_decision": release_decision,
            "locked": locked,
            "delivery_mode": preferred_delivery,
            "fallback_mode": fallback_mode,
            "contract": contract,
            "release_checks": release_checks,
            "output_policy": output_policy,
            "stage1_route": stage1.get("route"),
            "stage2_summary": stage2.get("summary"),
            "stage9_readiness": (stage9.get("readiness") or {}).copy(),
        }


_STAGE_10_HARDENING = VoiceStage10ProductionHardening()

ANALYSIS_ROUTE_VOICE_PROFILE = {
    "speed": 0.92,
    "pause_density": 0.88,
    "authority": 0.72,
    "warmth": 0.36,
    "intonation_variation": 0.94,
    "allow_breaths": True,
    "allow_soft_laughter": False,
    "dialogue_posture": "consultative_dialectic",
    "communication_quality": "high",
}

ANALYSIS_ROUTE_STYLE_PROFILE = {
    "mode": "analytical_consultant",
    "depth": 0.94,
    "technicality": 0.44,
    "conciseness": 0.46,
    "counterpoint": 0.82,
    "stance": "exploratory_questioning",
    "analysis_frame": "contrastive_factorized",
    "translation_mode": "complex_to_simple",
    "clarity_priority": 0.98,
    "persuasive_capacity": 0.48,
}

EXECUTION_ROUTE_VOICE_PROFILE = {
    "speed": 1.03,
    "pause_density": 0.56,
    "authority": 0.92,
    "warmth": 0.20,
    "intonation_variation": 0.66,
    "allow_breaths": False,
    "allow_soft_laughter": False,
    "dialogue_posture": "direct_action",
    "communication_quality": "high",
}

EXECUTION_ROUTE_STYLE_PROFILE = {
    "mode": "executive_assistant",
    "depth": 0.56,
    "technicality": 0.26,
    "conciseness": 0.84,
    "counterpoint": 0.34,
    "stance": "decisive",
    "analysis_frame": "action_first",
    "translation_mode": "complex_to_simple",
    "clarity_priority": 0.99,
    "persuasive_capacity": 0.70,
}

_MD_CODE_BLOCK = re.compile(r"```[\s\S]*?```", flags=re.MULTILINE)
_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_MD_URL = re.compile(r"https?://\S+")
_MD_BOLD = re.compile(r"\*\*(.+?)\*\*")
_MD_ITALIC = re.compile(r"\*(.+?)\*")
_MD_INLINE_CODE = re.compile(r"`(.+?)`")
_MD_HEADER = re.compile(r"^#+\s*", flags=re.MULTILINE)
_MD_LIST_ITEM = re.compile(r"^\s*[-*]\s+", flags=re.MULTILINE)
_MD_HR = re.compile(r"---+")
_MD_EXCESS_NL = re.compile(r"\n{3,}")

_SENTENCE_SPLIT_RE = re.compile(r"([^.!?\n]+[.!?]?)")
_EMPHASIS_MD_RE = re.compile(r"\*\*(.+?)\*\*")
_EMPHASIS_QUOTE_RE = re.compile(r"[«\"“](.+?)[»\"”]")


def _load_orchestrator_config() -> Dict[str, Any]:
    """Load optional voice orchestrator configuration from Hermes config."""
    try:
        from hermes_cli.config import load_config

        cfg = load_config() or {}
        return cfg.get("voice_orchestrator", {}) or {}
    except Exception:
        return {}


def _merge_dict(base: Dict[str, Any], override: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    result = deepcopy(base)
    if not override:
        return result
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge_dict(result[key], value)
        else:
            result[key] = value
    return result


def _normalize_technical_phrases_for_speech(chunk: str, source_text: str | None = None) -> str:
    """Rewrite backend-heavy markers into user-facing language while keeping the sentence natural."""
    text = re.sub(r"\s+", " ", chunk).strip()
    source = re.sub(r"\s+", " ", source_text or chunk).strip().lower()

    # Only rewrite the backend markers the user asked us to hide.
    if any(term in source for term in ("endpoint", "ruta", "path", "url", "webhook")):
        text = re.sub(r"(?i)\bendpoint\b", "dirección", text)
        text = re.sub(r"(?i)\b(webhook|url|path|ruta)\b", "ruta", text)
    if any(term in source for term in ("script", "scripts", "runner", "shell", "automatiz", "pipeline")):
        text = re.sub(r"(?i)\b(scripts?|script|runner|shell|pipeline)\b", "automatización", text)
    if any(term in source for term in ("json", "payload", "body", "query", "param", "header", "env", "entorno", "backend")):
        text = re.sub(r"(?i)\b(json|payload|body|query|param(?:eter)?|header|env(?:ironment)?|entorno\s+backend|backend)\b", "configuración", text)
    if any(term in source for term in ("auth", "login", "token", "bearer", "clave", "permiso")):
        text = re.sub(r"(?i)\b(auth|login|token|bearer|clave|permiso)\b", "llave de acceso", text)
    if any(term in source for term in ("database", "db", "sql", "table")):
        text = re.sub(r"(?i)\b(database|db|sql|table)\b", "base de datos", text)
    if any(term in source for term in ("api", "registro", "register", "connect", "connector")):
        text = re.sub(r"(?i)\b(api|connect|connector)\b", "conexión", text)
        text = re.sub(r"(?i)\b(registro|register)\b", "registro", text)

    text = _PATH_LIKE_TOKEN_RE.sub(" ", text)
    text = _TECHNICAL_TOKEN_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _collapse_technical_sentences(text: str, source_text: str | None = None) -> str:
    """Remove or condense sentences that are still technical after token stripping."""
    chunks = re.split(r"(?<=[.!?])\s+|\n+", text)
    cleaned: list[str] = []
    technical_summary_added = False
    for chunk in chunks:
        chunk = re.sub(r"\s+", " ", chunk).strip()
        if not chunk:
            continue
        tech_signals = len(re.findall(r"[\\/{}\[\]<>:=@]", chunk)) + len(_TECHNICAL_KEYWORD_RE.findall(chunk))
        tech_signals += 1 if re.search(r"(?<!\w)[\w.-]*[_-][\w.-]*\d", chunk) else 0
        rewritten = _normalize_technical_phrases_for_speech(chunk, source_text=source_text or chunk)
        if tech_signals >= 2 or (tech_signals >= 1 and len(chunk.split()) > 6):
            if not technical_summary_added and rewritten:
                cleaned.append(rewritten)
                technical_summary_added = True
        else:
            cleaned.append(rewritten)
    return " ".join(cleaned).strip()


def _strip_for_speech(text: str, source_text: str | None = None) -> str:
    """Convert rich text into a speech-safe plain text string."""
    if not text:
        return ""
    raw_text = str(text)
    source_text = str(source_text or raw_text)
    text = raw_text
    text = _AUDIO_VOICE_DIRECTIVE_RE.sub(" ", text)
    text = _MEDIA_DIRECTIVE_RE.sub(" ", text)
    text = _MD_CODE_BLOCK.sub(" ", text)
    text = _MD_LINK.sub(r"\1", text)
    text = _MD_URL.sub("", text)
    text = _MD_BOLD.sub(r"\1", text)
    text = _MD_ITALIC.sub(r"\1", text)
    text = _MD_INLINE_CODE.sub(r"\1", text)
    text = _MD_HEADER.sub("", text)
    text = _MD_LIST_ITEM.sub("", text)
    text = _MD_HR.sub(" ", text)
    text = _PATH_LIKE_TOKEN_RE.sub(" ", text)
    text = _TECHNICAL_TOKEN_RE.sub(" ", text)
    text = _collapse_technical_sentences(text, source_text=source_text)
    text = text.replace("<think>", " ").replace("</think>", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


_AUDIO_VOICE_DIRECTIVE_RE = re.compile(r"\[\[audio_as_voice\]\]", flags=re.IGNORECASE)
_MEDIA_DIRECTIVE_RE = re.compile(r"MEDIA:\s*", flags=re.IGNORECASE)
_PATH_LIKE_TOKEN_RE = re.compile(r"(?<!\w)(?:[\w.-]+(?:/[\w.-]+)+|[\w.-]+(?:\\[\w.-]+)+)(?!\w)")
_TECHNICAL_TOKEN_RE = re.compile(r"(?<!\w)(?=[\w.-]*[_-])(?=[\w.-]*\d)[\w.-]{8,}(?!\w)")
_TECHNICAL_KEYWORD_RE = re.compile(r"\b(endpoint|api|ruta|url|path|registro|auth|login|token|webhook|payload|header|json|query|param(?:eter)?|bearer)\b", flags=re.IGNORECASE)
_CAUSAL_BREAKS = re.compile(r"\s+(pero|sin embargo|aunque|porque|entonces|así que|por eso|además|de hecho|en cambio|mientras|cuando)\s+", flags=re.IGNORECASE)
_MODAL_VERB_RE = re.compile(
    r"\b(deberías|podrías|tienes que|hay que|vamos a|puedes|necesitas|necesitamos|quiero que|debo|deben)\s+"
    r"(hacer|separar|analizar|organizar|probar|tomar|mostrar|revisar|activar|decidir|corregir|mejorar|entregar|validar|ajustar|ejecutar|priorizar|usar|conectar|enviar|cerrar|buscar|crear)\b",
    flags=re.IGNORECASE,
)
_ONOMATOPOEIA_RE = re.compile(
    r"\b(?:(?:m{2,})|(?:u+f+)|(?:a+h+)|(?:e+h+)|(?:o+h+)|(?:j[aeio]{1,2}(?:\s+j[aeio]{1,2}){1,5})|(?:j[aeio]{2,6})|(?:h[aeio]{2,6})|(?:jaja(?:ja)?)|(?:jeje(?:je)?)|(?:jiji(?:ji)?)|(?:jojo(?:jo)?))\b",
    flags=re.IGNORECASE,
)
_BREATH_CUE_RE = re.compile(r"(?<!\\w)s{3,}(?:\.\.\.|\.)*(?!\\w)", flags=re.IGNORECASE)


def _extract_emphasis_terms(text: str) -> list[str]:
    """Extract emphasis cues from the raw text before it is normalized."""
    if not text:
        return []

    terms: list[str] = []
    seen = set()
    patterns = (_EMPHASIS_MD_RE, _EMPHASIS_QUOTE_RE)
    for pattern in patterns:
        for match in pattern.finditer(text):
            term = re.sub(r"\s+", " ", match.group(1)).strip()
            if term and term.lower() not in seen and len(term) > 1:
                seen.add(term.lower())
                terms.append(term)

    return terms[:12]


def _extract_onomatopoeia_terms(text: str) -> list[str]:
    """Extract sonic cues that should be treated as interjections, not acronyms."""
    if not text:
        return []

    matches: list[str] = []
    seen = set()
    for match in _ONOMATOPOEIA_RE.finditer(text):
        term = re.sub(r"\s+", " ", match.group(0)).strip()
        if term and term.lower() not in seen:
            seen.add(term.lower())
            matches.append(term)

    return matches[:20]


def _extract_breath_terms(text: str) -> list[str]:
    """Extract breath-like hisses such as ssss... and treat them as respiration cues."""
    if not text:
        return []

    matches: list[str] = []
    seen = set()
    for match in _BREATH_CUE_RE.finditer(text):
        term = re.sub(r"\s+", " ", match.group(0)).strip()
        if term and term.lower() not in seen:
            seen.add(term.lower())
            matches.append(term)

    return matches[:20]


def _shape_onomatopoeias_for_speech(text: str, onomatopoeia_terms: Optional[list[str]] = None) -> str:
    """Keep sonic interjections isolated so the renderer treats them as sound cues."""
    if not text:
        return ""

    if onomatopoeia_terms is None:
        onomatopoeia_terms = _extract_onomatopoeia_terms(text)

    if not onomatopoeia_terms:
        return text

    shaped = text
    for raw_term in sorted(set(onomatopoeia_terms), key=len, reverse=True):
        term = re.sub(r"\s+", " ", raw_term).strip()
        if not term:
            continue

        lower = term.lower()
        if re.fullmatch(r"j[aeio]{2,6}", lower):
            syllable = lower[:2]
            repeats = max(2, len(lower) // 2)
            replacement = ", ".join([syllable] * repeats)
        elif re.fullmatch(r"(?:j[aeio]{1,2})(?:\s+j[aeio]{1,2})+", lower):
            replacement = ", ".join(lower.split())
        elif re.fullmatch(r"m{2,}|u+f+|a+h+|e+h+|o+h+|ay+|uy+", lower):
            replacement = f"{lower}..."
        else:
            replacement = term

        pattern = re.compile(rf"(?<!\\w){re.escape(term)}(?!\\w)", flags=re.IGNORECASE)
        shaped = pattern.sub(replacement, shaped)

    shaped = re.sub(r"\s+,\s+", ", ", shaped)
    shaped = re.sub(r",{2,}", ",", shaped)
    return shaped


def _shape_breaths_for_speech(text: str, breath_terms: Optional[list[str]] = None) -> str:
    """Keep hissy respirations like ssss... isolated and pause-ready."""
    if not text:
        return ""

    if breath_terms is None:
        breath_terms = _extract_breath_terms(text)

    if not breath_terms:
        return text

    shaped = text
    for raw_term in sorted(set(breath_terms), key=len, reverse=True):
        term = re.sub(r"\s+", " ", raw_term).strip()
        if not term:
            continue

        lower = term.lower()
        replacement = "..."
        pattern = re.compile(rf"(?<!\\w){re.escape(term)}(?!\\w)", flags=re.IGNORECASE)
        shaped = pattern.sub(replacement, shaped)

    shaped = re.sub(r"\s+,\s+", ", ", shaped)
    shaped = re.sub(r",{2,}", ",", shaped)
    return shaped


def _is_breath_only_text(text: str) -> bool:
    """Return True when the content is just a sustained airy consonant cue."""
    if not text:
        return False
    stripped = _strip_for_speech(text, source_text=text)
    stripped = _shape_breaths_for_speech(stripped)
    stripped = re.sub(r"[\s\.,;:!?…-]+", "", stripped)
    stripped = re.sub(r"[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", "", stripped)
    return bool(stripped) == False and bool(_extract_breath_terms(text))


def _generate_hiss_audio(output_path: str, duration_ms: int = 650) -> Dict[str, Any]:
    """Generate a soft air hiss to emulate sustained breath consonants."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        try:
            from imageio_ffmpeg import get_ffmpeg_exe

            ffmpeg = get_ffmpeg_exe()
        except Exception:
            ffmpeg = None
    if not ffmpeg:
        return {"success": False, "error": "ffmpeg is required to generate breath audio"}

    out_path = str(Path(output_path))
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    duration_s = max(0.25, min(1.5, duration_ms / 1000.0))
    fade_out_start = max(0.0, duration_s - 0.12)
    filter_chain = (
        "highpass=f=4200,"
        "lowpass=f=8800,"
        "volume=0.08,"
        f"afade=t=in:st=0:d=0.04,afade=t=out:st={fade_out_start:.2f}:d=0.12"
    )
    cmd = [
        ffmpeg,
        "-f",
        "lavfi",
        "-i",
        f"anoisesrc=color=white:duration={duration_s}:amplitude=0.08",
        "-af",
        filter_chain,
        "-y",
        "-loglevel",
        "error",
        out_path,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    if proc.returncode != 0:
        return {"success": False, "error": proc.stderr.strip() or "ffmpeg hiss generation failed"}

    return {
        "success": True,
        "file_path": out_path,
        "provider": "hiss",
        "voice_compatible": True,
        "media_tag": f"[[audio_as_voice]]\nMEDIA:{out_path}",
    }


def _shape_speech_text_for_prosody(
    text: str,
    voice_profile: Dict[str, Any],
    style_profile: Dict[str, Any],
    emphasis_terms: Optional[list[str]] = None,
    onomatopoeia_terms: Optional[list[str]] = None,
    breath_terms: Optional[list[str]] = None,
    aggressive: bool = False,
) -> str:
    """Shape the speech text so the renderer can produce better pauses and intonation."""
    text = _strip_for_speech(text, source_text=text)
    if not text:
        return ""

    pause_density = float(voice_profile.get("pause_density", 0.5) or 0.5)
    allow_breaths = bool(voice_profile.get("allow_breaths"))
    reflectiveness = bool(DEFAULT_POLICY.get("allow_reflective_pauses", True))
    emphasis_terms = emphasis_terms or []
    if not reflectiveness:
        return text

    if emphasis_terms:
        for term in sorted(emphasis_terms, key=len, reverse=True):
            if not term:
                continue
            pattern = re.compile(rf"(?<!\w)({re.escape(term)})(?!\w)", flags=re.IGNORECASE)
            def _emphasize(match):
                next_char = text[match.end():match.end() + 1]
                if next_char and next_char in ".!?;:,":
                    return match.group(1)
                return f"{match.group(1)},"
            text = pattern.sub(_emphasize, text)
        text = re.sub(r"\s+,\s+", ", ", text)
        text = re.sub(r",{2,}", ",", text)

    text = _shape_onomatopoeias_for_speech(text, onomatopoeia_terms=onomatopoeia_terms)
    text = _shape_breaths_for_speech(text, breath_terms=breath_terms)
    text = _MODAL_VERB_RE.sub(lambda m: f"{m.group(1)}, {m.group(2)}", text)
    text = re.sub(r"\b(y además|además|sin embargo|por eso|de hecho|entonces)\b", r", \1,", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+,\s+", ", ", text)
    text = re.sub(r",{2,}", ",", text)

    if not aggressive:
        return re.sub(r"\s+", " ", text).strip()

    sentences = [m.group(1).strip() for m in _SENTENCE_SPLIT_RE.finditer(text)]
    sentences = [s for s in sentences if s]
    if not sentences:
        return text

    shaped_sentences: list[str] = []
    strong_breaks = ("pero", "sin embargo", "además", "entonces", "porque", "así que", "de hecho", "por eso")
    for idx, sentence in enumerate(sentences):
        sentence = re.sub(r"\s+", " ", sentence).strip()
        sentence = _CAUSAL_BREAKS.sub(r", \1,", sentence)
        if len(sentence.split()) > 12:
            for marker in strong_breaks:
                m = re.search(rf"\b{marker}\b", sentence, flags=re.IGNORECASE)
                if m:
                    left = sentence[:m.start()].rstrip(" ,")
                    right = sentence[m.start():].lstrip(" ,")
                    if left and right:
                        sentence = f"{left}.\n\n{right}"
                    break
        sentence = re.sub(r"\s+,\s+", ", ", sentence)
        sentence = re.sub(r",{2,}", ",", sentence)
        sentence = re.sub(r"\n{3,}", "\n\n", sentence)
        sentence = sentence.strip()
        if allow_breaths and idx < len(sentences) - 1 and len(sentence.split()) > 16:
            sentence = sentence.rstrip(".?!") + "."
        shaped_sentences.append(sentence)

    if not shaped_sentences:
        return text

    separator = "\n" if pause_density < 0.6 else "\n\n"
    return separator.join(shaped_sentences).strip()


def _infer_speech_events(speech_text: str, voice_profile: Dict[str, Any], emphasis_terms: Optional[list[str]] = None, onomatopoeia_terms: Optional[list[str]] = None, breath_terms: Optional[list[str]] = None) -> list[dict[str, Any]]:
    """Infer a minimal set of speech events for downstream renderers."""
    events: list[dict[str, Any]] = []
    if not speech_text:
        return events

    allow_breaths = bool(voice_profile.get("allow_breaths"))
    allow_fillers = bool(voice_profile.get("allow_fillers"))
    onomatopoeia_terms = onomatopoeia_terms or _extract_onomatopoeia_terms(speech_text)
    breath_terms = breath_terms or _extract_breath_terms(speech_text)

    sentences = [m.group(1).strip() for m in _SENTENCE_SPLIT_RE.finditer(speech_text)]
    sentences = [s for s in sentences if s]
    for idx, sentence in enumerate(sentences):
        ending = sentence[-1] if sentence else ""
        pause_ms = 180
        if ending == "?":
            pause_ms = 260
        elif ending == "!":
            pause_ms = 220
        elif ending == ".":
            pause_ms = 200
        elif ending in {";", ":"}:
            pause_ms = 240

        if idx < len(sentences) - 1:
            events.append(
                {
                    "type": "pause",
                    "position": f"sentence_{idx + 1}",
                    "duration_ms": pause_ms,
                    "value": ending,
                }
            )

        clause_pause_count = sentence.count(",")
        if clause_pause_count:
            events.append(
                {
                    "type": "pause",
                    "position": f"clause_{idx + 1}",
                    "duration_ms": 140 + min(60, clause_pause_count * 10),
                    "value": ",",
                }
            )

        for term in emphasis_terms or []:
            if term and re.search(rf"(?<!\\w){re.escape(term)}(?!\\w)", sentence, flags=re.IGNORECASE):
                events.append(
                    {
                        "type": "emphasis",
                        "position": f"sentence_{idx + 1}",
                        "duration_ms": 110,
                        "value": term,
                    }
                )
                events.append(
                    {
                        "type": "pause",
                        "position": f"after_emphasis_{idx + 1}",
                        "duration_ms": 120,
                        "value": term,
                    }
                )

        for term in onomatopoeia_terms:
            if term and re.search(rf"(?<!\\w){re.escape(term)}(?!\\w)", sentence, flags=re.IGNORECASE):
                events.append(
                    {
                        "type": "onomatopoeia",
                        "position": f"sentence_{idx + 1}",
                        "duration_ms": 90,
                        "value": term,
                    }
                )

        for term in breath_terms:
            if term and re.search(rf"(?<!\\w){re.escape(term)}(?!\\w)", sentence, flags=re.IGNORECASE):
                events.append(
                    {
                        "type": "breath",
                        "position": f"sentence_{idx + 1}",
                        "duration_ms": 120,
                        "value": term,
                    }
                )

        if allow_breaths and len(sentence) > 130 and idx < len(sentences) - 1:
            events.append(
                {
                    "type": "breath",
                    "position": f"sentence_{idx + 1}",
                    "duration_ms": 120,
                    "value": "light",
                }
            )

        if allow_fillers and idx == 0 and len(sentence) > 50:
            events.append(
                {
                    "type": "filler",
                    "position": "opening",
                    "duration_ms": 80,
                    "value": "mmm",
                }
            )

    if breath_terms and not any(event.get("type") == "breath" for event in events):
        for term in breath_terms:
            events.append(
                {
                    "type": "breath",
                    "position": "breath_only",
                    "duration_ms": 120,
                    "value": term,
                }
            )

    return events


def compose_voice_prompt(
    text: str,
    context: Optional[Dict[str, Any]] = None,
    identity_profile: Optional[Dict[str, Any]] = None,
    voice_profile: Optional[Dict[str, Any]] = None,
    style_profile: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build the voice contract that the rest of the pipeline consumes."""
    cfg = _load_orchestrator_config()
    context = dict(context or {})

    stage1 = _STAGE_1_GATE.execute(text=text, audio_path=None, context=context)
    stage2 = _STAGE_2_MEMORY.execute(text=text, context=context, stage1=stage1)

    route = str(stage1.get("route") or context.get("interaction_route") or context.get("session_route") or "").strip().lower()
    route_reason = str(stage1.get("route_reason") or context.get("route_reason") or "").strip().lower()

    merged_identity = _merge_dict(DEFAULT_IDENTITY_PROFILE, cfg.get("identity_profile"))
    merged_identity = _merge_dict(merged_identity, identity_profile)
    merged_voice = _merge_dict(DEFAULT_VOICE_PROFILE, cfg.get("voice_profile"))
    merged_voice = _merge_dict(merged_voice, voice_profile)
    merged_style = _merge_dict(DEFAULT_STYLE_PROFILE, cfg.get("style_profile"))
    merged_style = _merge_dict(merged_style, style_profile)

    stage3 = _STAGE_3_MODE.execute(text=text, context=context, stage1=stage1, stage2=stage2)
    merged_voice = _merge_dict(merged_voice, stage3.get("voice_profile_patch"))
    merged_style = _merge_dict(merged_style, stage3.get("style_profile_patch"))

    stage4 = _STAGE_4_SANITIZER.execute(text=text, context=context, stage1=stage1, stage2=stage2, stage3=stage3)
    stage5 = _STAGE_5_PLANNER.execute(text=text, context=context, stage1=stage1, stage2=stage2, stage3=stage3, stage4=stage4)
    stage6 = _STAGE_6_DUAL_CHANNEL.execute(text=text, context=context, stage1=stage1, stage2=stage2, stage3=stage3, stage4=stage4, stage5=stage5)
    stage7 = _STAGE_7_FINE_PROSODY.execute(text=text, context=context, stage1=stage1, stage2=stage2, stage3=stage3, stage4=stage4, stage5=stage5)
    stage8 = _STAGE_8_QUALITY.execute(text=text, context=context, stage1=stage1, stage2=stage2, stage3=stage3, stage4=stage4, stage5=stage5, stage6=stage6, stage7=stage7)
    stage9 = _STAGE_9_COMPARATOR.execute(text=text, context=context, stage1=stage1, stage2=stage2, stage3=stage3, stage4=stage4, stage5=stage5, stage6=stage6, stage7=stage7, stage8=stage8)
    stage10 = _STAGE_10_HARDENING.execute(text=text, context=context, stage1=stage1, stage2=stage2, stage3=stage3, stage4=stage4, stage5=stage5, stage6=stage6, stage7=stage7, stage8=stage8, stage9=stage9)

    merged_voice = _merge_dict(merged_voice, stage7.get("prosody_profile_patch"))
    merged_style = _merge_dict(merged_style, {"quality_gate": stage8.get("quality_score"), "comparison_score": stage9.get("readiness", {}).get("improvement_score"), "production_lock": stage10.get("release_decision")})

    policy = _merge_dict(DEFAULT_POLICY, cfg.get("policy"))

    display_text = stage4.get("sanitized_display_text") or (text or "").strip()
    emphasis_terms = _extract_emphasis_terms(display_text)
    onomatopoeia_terms = _extract_onomatopoeia_terms(display_text)
    breath_terms = _extract_breath_terms(display_text)
    speech_text = _shape_speech_text_for_prosody(
        stage7.get("render_text") or stage5.get("render_text") or stage4.get("speech_text") or display_text,
        merged_voice,
        merged_style,
        emphasis_terms=emphasis_terms,
        onomatopoeia_terms=onomatopoeia_terms,
        breath_terms=breath_terms,
        aggressive=False,
    )
    render_text = _shape_speech_text_for_prosody(
        stage7.get("render_text") or stage5.get("render_text") or stage4.get("speech_text") or display_text,
        merged_voice,
        merged_style,
        emphasis_terms=emphasis_terms,
        onomatopoeia_terms=onomatopoeia_terms,
        breath_terms=breath_terms,
        aggressive=True,
    )

    llm_request = {
        "llm_task": "generate_voice_ready_response",
        "output_channel": "voice",
        "context": {
            **stage2.get("context_summary", {}),
            **(context or {}),
            "interaction_route": route,
            "route_reason": route_reason,
            "voice_route": route or "unspecified",
            "stage1": stage1,
            "stage2": stage2,
            "stage3": stage3,
            "stage4": stage4,
            "stage5": stage5,
            "stage6": stage6,
            "stage7": stage7,
            "stage8": stage8,
            "stage9": stage9,
            "stage10": stage10,
        },
        "response_requirements": {
            "language": "es",
            "separate_display_and_speech": True,
            "avoid_literal_urls": True,
            "avoid_literal_endpoints": True,
            "avoid_literal_json": True,
            "avoid_literal_code": True,
            "prefer_short_opening": True,
            "make_complex_simple": True,
            "preserve_strategic_depth": True,
            "mark_breath_spaces_instead_of_reading_them": True,
            "identify_when_breath_carries_agobio_or_context_load": True,
            "treat_sighs_as_structural_feedback": True,
        },
        "technical_speech_policy": {
            "do_not_read_urls_verbatim": True,
            "do_not_read_endpoints_verbatim": True,
            "do_not_read_json_verbatim": True,
            "do_not_read_code_verbatim": True,
            "summarize_technical_items": True,
        },
        "humanization_policy": {
            "allow_reflective_pauses": policy.get("allow_reflective_pauses", True),
            "allow_micro_fillers": policy.get("allow_micro_fillers", False),
            "allow_breath_events": policy.get("allow_breath_events", False),
            "prefer_short_opening": policy.get("prefer_short_opening", True),
            "dialogue_posture": merged_voice.get("dialogue_posture", "professional_trust"),
            "communication_quality": merged_voice.get("communication_quality", "high"),
            "stance": merged_style.get("stance", "formed_opinion"),
            "analysis_frame": merged_style.get("analysis_frame", "factorized"),
            "translation_mode": merged_style.get("translation_mode", "complex_to_simple"),
            "clarity_priority": merged_style.get("clarity_priority", 0.9),
            "persuasive_capacity": merged_style.get("persuasive_capacity", 0.78),
            "treat_onomatopoeia_as_sound": True,
            "treat_breath_hisses_as_respiration": True,
            "preserve_soft_laughter": bool(merged_voice.get("allow_soft_laughter", True)),
        },
        "speech_event_policy": {
            "required_sound_events": ["onomatopoeia"],
            "breath_style": "soft_air_only",
            "onomatopoeia_style": "sound_only_not_acronym",
            "onomatopoeia_examples": ["mmm", "uff", "jeje", "jaja"],
            "do_not_read_onomatopoeia_as_sigla": True,
            "breath_coding_policy": {
                "encode_breath_spaces": True,
                "identify_breath_slots": True,
                "breath_slots_schema": ["position", "intent", "reason", "duration_ms"],
                "breath_intents": ["agobio", "pausa_mental", "carga_contextual", "cierre_de_idea"],
                "breath_usage_examples": [
                    "cuando el contexto es demasiado denso",
                    "cuando quiere mostrar agobio",
                    "cuando necesita marcar una pausa de carga",
                    "cuando quiere separar una idea que pesa demasiado",
                ],
                "do_not_emit_literal_breath_text": True,
            },
        },
        "rendering_policy": {
            "target_renderer": "tts_tool",
            "preserve_display_text": True,
            "speech_max_chars": MAX_TEXT_LENGTH,
            "prefer_asset_insert_for_breaths": True,
            "prefer_asset_insert_for_laughter": True,
            "prefer_sound_event_encoding": True,
        },
        "required_output_schema": {
            "display_text": "string",
            "speech_text": "string",
            "suggested_segments": "array",
            "breath_slots": "array",
            "speech_events": "array",
            "technical_items": "array",
            "pronunciation_hints": "array",
            "voice_style": "object",
            "rendering_hints": "object",
        },
    }

    return {
        "status": "composed",
        "display_text": display_text,
        "speech_text": speech_text,
        "source_text": text,
        "context": context or {},
        "stage1": stage1,
        "stage2": stage2,
        "stage3": stage3,
        "stage4": stage4,
        "stage5": stage5,
        "stage6": stage6,
        "stage7": stage7,
        "stage8": stage8,
        "stage9": stage9,
        "stage10": stage10,
        "identity_profile": merged_identity,
        "voice_profile": merged_voice,
        "style_profile": merged_style,
        "policy": policy,
        "speech_events": _infer_speech_events(render_text, merged_voice, emphasis_terms=emphasis_terms, onomatopoeia_terms=onomatopoeia_terms, breath_terms=breath_terms),
        "speech_plan": {
            "pause_density": merged_voice.get("pause_density", 0.5),
            "allow_breaths": merged_voice.get("allow_breaths", False),
            "allow_fillers": merged_voice.get("allow_fillers", False),
            "separator": "\n\n" if float(merged_voice.get("pause_density", 0.5) or 0.5) >= 0.6 else "\n",
            "emphasis_terms": emphasis_terms,
            "onomatopoeia_terms": onomatopoeia_terms,
            "breath_terms": breath_terms,
            "render_text": render_text,
            "dual_channel": stage6,
            "fine_prosody": stage7,
            "quality_validation": stage8,
            "stage_comparison": stage9,
            "production_hardening": stage10,
        },
        "llm_request": llm_request,
    }


def validate_voice_packet(packet: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and normalize a voice packet before audio rendering."""
    if not isinstance(packet, dict):
        raise TypeError("voice packet must be a dict")

    validated = deepcopy(packet)
    display_text = (validated.get("display_text") or "").strip()
    speech_text = (validated.get("speech_text") or "").strip()
    voice_profile = validated.get("voice_profile") or deepcopy(DEFAULT_VOICE_PROFILE)

    if not display_text:
        display_text = speech_text
    if not speech_text:
        speech_text = _strip_for_speech(display_text, source_text=validated.get("source_text") or display_text)

    speech_text = _strip_for_speech(speech_text, source_text=validated.get("source_text") or speech_text)
    display_text = display_text.strip()

    if len(speech_text) > MAX_TEXT_LENGTH:
        speech_text = speech_text[:MAX_TEXT_LENGTH].rstrip()

    if len(display_text) > MAX_TEXT_LENGTH:
        display_text = display_text[:MAX_TEXT_LENGTH].rstrip()

    speech_plan = deepcopy(validated.get("speech_plan") or {})
    if speech_plan:
        speech_plan["render_text"] = speech_text
        if isinstance(speech_plan.get("segments"), list) and speech_text:
            speech_plan["segments"] = [speech_text]
            speech_plan["segment_count"] = 1
            speech_plan["pauses_ms"] = []
            speech_plan["separator"] = "\n"
        validated["speech_plan"] = speech_plan

    speech_events = _infer_speech_events(speech_text, voice_profile)
    warnings: list[str] = []
    if not speech_text:
        warnings.append("speech_text_empty")

    validated.update(
        {
            "status": "ok" if speech_text else "error",
            "display_text": display_text,
            "speech_text": speech_text,
            "speech_events": speech_events,
            "warnings": warnings,
        }
    )
    return validated


def _synthesize_voice_audio(
    speech_text: str,
    output_path: Optional[str] = None,
    platform: Optional[str] = None,
) -> Dict[str, Any]:
    """Call the existing TTS tool and return its structured result."""
    from tools.tts_tool import text_to_speech_tool

    prev_platform = os.environ.get("HERMES_SESSION_PLATFORM")
    # Normalize platform: accept str or enum (e.g. Platform.TELEGRAM)
    platform_str: Optional[str] = (
        platform.value if hasattr(platform, "value") else str(platform)
    ) if platform else None
    try:
        if platform_str:
            os.environ["HERMES_SESSION_PLATFORM"] = platform_str
        result_json = text_to_speech_tool(text=speech_text, output_path=output_path)
        if isinstance(result_json, str):
            return json.loads(result_json)
        return dict(result_json)
    finally:
        if platform_str is not None:
            if prev_platform is None:
                os.environ.pop("HERMES_SESSION_PLATFORM", None)
            else:
                os.environ["HERMES_SESSION_PLATFORM"] = prev_platform


def render_voice_packet(
    packet: Dict[str, Any],
    output_path: Optional[str] = None,
    platform: Optional[str] = None,
) -> Dict[str, Any]:
    """Render validated speech into audio via the existing TTS pipeline."""
    if packet.get("status") != "ok":
        return {
            "success": False,
            "error": "voice packet is not valid for rendering",
        }

    speech_text = packet.get("speech_text", "")
    render_text = packet.get("speech_text", "") or packet.get("speech_plan", {}).get("render_text") or packet.get("render_text") or speech_text
    source_text = packet.get("display_text") or speech_text or render_text
    if not render_text:
        return {
            "success": False,
            "error": "speech_text is empty",
        }

    if _is_breath_only_text(source_text):
        out_path = output_path
        if not out_path:
            out_path = str(Path(tempfile.gettempdir()) / "hermes_breath_hiss.ogg")
        rendered = _generate_hiss_audio(out_path, duration_ms=750)
        if not rendered.get("success"):
            return rendered
        return rendered

    rendered = _synthesize_voice_audio(render_text, output_path=output_path, platform=platform)
    if not rendered.get("success"):
        return rendered

    return rendered


def _emit_voice_result(
    packet: Dict[str, Any],
    rendered: Optional[Dict[str, Any]],
    platform: Optional[str] = None,
) -> Dict[str, Any]:
    """Build the final platform-ready result."""
    audio_path = None
    media_tag = None
    voice_compatible = None
    provider = None

    if rendered:
        audio_path = rendered.get("file_path")
        media_tag = rendered.get("media_tag")
        voice_compatible = rendered.get("voice_compatible")
        provider = rendered.get("provider")

    return {
        "status": "ok",
        "platform": platform or DEFAULT_PLATFORM,
        "display_text": packet.get("display_text", ""),
        "speech_text": packet.get("speech_text", ""),
        "audio_path": audio_path,
        "media_tag": media_tag,
        "voice_compatible": voice_compatible,
        "provider": provider,
        "identity_profile": packet.get("identity_profile", {}),
        "voice_profile": packet.get("voice_profile", {}),
        "style_profile": packet.get("style_profile", {}),
    }


def _transcribe_voice_input(audio_path: str, model: Optional[str] = None) -> Dict[str, Any]:
    """Transcribe an inbound audio file using the shared STT pipeline."""
    from tools.transcription_tools import transcribe_audio, get_stt_model_from_config

    resolved_model = model or get_stt_model_from_config()
    result = transcribe_audio(audio_path, model=resolved_model)
    if isinstance(result, str):
        try:
            return json.loads(result)
        except Exception:
            return {"success": False, "transcript": "", "error": "invalid transcription response"}
    return dict(result)


def orchestrate_voice_input(
    text: str = "",
    audio_path: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
    identity_profile: Optional[Dict[str, Any]] = None,
    voice_profile: Optional[Dict[str, Any]] = None,
    style_profile: Optional[Dict[str, Any]] = None,
    output_path: Optional[str] = None,
    platform: Optional[str] = None,
    dry_run: bool = False,
    transcribe_model: Optional[str] = None,
) -> str:
    """Accept text or audio input, transcribe audio if needed, then orchestrate voice output."""
    normalized_text = (text or "").strip()
    transcript = None
    transcription_result: Optional[Dict[str, Any]] = None

    stage1 = _STAGE_1_GATE.execute(text=normalized_text, audio_path=audio_path, context=context)
    source_kind = stage1["source_kind"]

    if audio_path:
        transcription_result = _transcribe_voice_input(audio_path, model=transcribe_model)
        if not transcription_result.get("success"):
            return json.dumps(
                {
                    "status": "error",
                    "mode": "text",
                    "stage1": stage1,
                    "source_kind": source_kind,
                    "input_audio_path": audio_path,
                    "transcript": "",
                    "transcription": transcription_result,
                    "final_text": "",
                    "audio_path": None,
                    "media_tag": None,
                    "provider": None,
                    "validation": {
                        "contract_valid": False,
                        "step_order_valid": True,
                        "artifact_valid": False,
                    },
                    "warnings": ["audio_transcription_failed"],
                    "error": transcription_result.get("error", "voice transcription failed"),
                },
                ensure_ascii=False,
            )
        transcript = (transcription_result.get("transcript") or "").strip()
        normalized_text = transcript

    if not normalized_text:
        return json.dumps(
            {
                "status": "error",
                "mode": "text",
                "stage1": stage1,
                "source_kind": source_kind,
                "input_audio_path": audio_path,
                "transcript": transcript or "",
                "transcription": transcription_result,
                "final_text": "",
                "audio_path": None,
                "media_tag": None,
                "provider": None,
                "validation": {
                    "contract_valid": True,
                    "step_order_valid": True,
                    "artifact_valid": False,
                },
                "warnings": ["empty_voice_input"],
                "error": "voice input is empty",
            },
            ensure_ascii=False,
        )

    voice_context = dict(context or {})
    voice_context.setdefault("input_channel", stage1["input_channel"])
    voice_context.setdefault("voice_trigger", stage1["voice_trigger"])
    voice_context.setdefault("source_kind", stage1["source_kind"])
    voice_context.setdefault("interaction_route", stage1["route"])
    voice_context.setdefault("route_reason", stage1["route_reason"])
    if transcript and source_kind == "audio":
        voice_context.setdefault("transcript", transcript)

    result_json = orchestrate_voice(
        text=normalized_text,
        context=voice_context,
        identity_profile=identity_profile,
        voice_profile=voice_profile,
        style_profile=style_profile,
        output_path=output_path,
        platform=platform,
        dry_run=dry_run,
    )
    result = json.loads(result_json)
    result.update(
        {
            "stage1": stage1,
            "source_kind": source_kind,
            "input_audio_path": audio_path,
            "transcript": transcript,
            "transcription": transcription_result,
        }
    )
    return json.dumps(result, ensure_ascii=False)


def orchestrate_voice(
    text: str,
    context: Optional[Dict[str, Any]] = None,
    identity_profile: Optional[Dict[str, Any]] = None,
    voice_profile: Optional[Dict[str, Any]] = None,
    style_profile: Optional[Dict[str, Any]] = None,
    output_path: Optional[str] = None,
    platform: Optional[str] = None,
    dry_run: bool = False,
) -> str:
    """Run the full voice orchestration pipeline and return JSON.

    The output is intentionally verbose: callers get the composed contract,
    the validated packet, the render result, and the emitted platform-ready
    metadata in one response.
    """
    composed = compose_voice_prompt(
        text=text,
        context=context,
        identity_profile=identity_profile,
        voice_profile=voice_profile,
        style_profile=style_profile,
    )
    validated = validate_voice_packet(composed)

    if validated.get("status") != "ok":
        return json.dumps(
            {
                "status": "error",
                "composed": composed,
                "validated": validated,
                "rendered": None,
                "emitted": None,
                "error": "voice packet validation failed",
            },
            ensure_ascii=False,
        )

    if dry_run:
        emitted = _emit_voice_result(validated, None, platform=platform)
        emitted.update(
            {
                "status": "ok",
                "mode": "dry_run",
                "composed": composed,
                "validated": validated,
                "rendered": None,
                "speech_plan": validated.get("speech_plan", {}),
                "final_text": validated.get("display_text", ""),
            }
        )
        return json.dumps(emitted, ensure_ascii=False)

    rendered = render_voice_packet(validated, output_path=output_path, platform=platform)
    emitted = _emit_voice_result(validated, rendered, platform=platform)
    emitted.update(
        {
            "status": "ok" if rendered.get("success") else "error",
            "mode": "rendered" if rendered.get("success") else "failed",
            "composed": composed,
            "validated": validated,
            "rendered": rendered,
            "speech_plan": validated.get("speech_plan", {}),
            "final_text": validated.get("display_text", ""),
        }
    )
    if not rendered.get("success"):
        emitted["error"] = rendered.get("error", "voice rendering failed")
    return json.dumps(emitted, ensure_ascii=False)


def voice_orchestrator_tool(
    text: str,
    context: Optional[Dict[str, Any]] = None,
    identity_profile: Optional[Dict[str, Any]] = None,
    voice_profile: Optional[Dict[str, Any]] = None,
    style_profile: Optional[Dict[str, Any]] = None,
    output_path: Optional[str] = None,
    platform: Optional[str] = None,
    dry_run: bool = False,
    audio_path: Optional[str] = None,
    transcribe_model: Optional[str] = None,
) -> str:
    """Tool handler wrapper."""
    if audio_path:
        return orchestrate_voice_input(
            text=text,
            audio_path=audio_path,
            context=context,
            identity_profile=identity_profile,
            voice_profile=voice_profile,
            style_profile=style_profile,
            output_path=output_path,
            platform=platform,
            dry_run=dry_run,
            transcribe_model=transcribe_model,
        )
    return orchestrate_voice(
        text=text,
        context=context,
        identity_profile=identity_profile,
        voice_profile=voice_profile,
        style_profile=style_profile,
        output_path=output_path,
        platform=platform,
        dry_run=dry_run,
    )


from tools.registry import registry

VOICE_ORCHESTRATOR_SCHEMA = {
    "name": "voice_orchestrator",
    "description": "Joint voice skill: accepts either response text or an inbound audio file, transcribes audio when needed, composes the voice contract, validates speech-safe output, renders audio via the TTS pipeline, and emits platform-ready metadata. The caller provides response text and/or audio_path plus optional context and profiles.",
    "parameters": {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "The source text to orchestrate for voice output. May be empty when audio_path is provided.",
            },
            "audio_path": {
                "type": "string",
                "description": "Optional local audio file path to transcribe before orchestration.",
            },
            "transcribe_model": {
                "type": "string",
                "description": "Optional STT model override used when audio_path is provided.",
            },
            "context": {
                "type": "object",
                "description": "Optional conversation or event context used to shape the voice contract.",
            },
            "identity_profile": {
                "type": "object",
                "description": "Optional voice identity profile override.",
            },
            "voice_profile": {
                "type": "object",
                "description": "Optional rendering profile override for cadence, authority, warmth, etc.",
            },
            "style_profile": {
                "type": "object",
                "description": "Optional style override for strategic/analytical/reflective tone.",
            },
            "output_path": {
                "type": "string",
                "description": "Optional explicit file path for the generated audio.",
            },
            "platform": {
                "type": "string",
                "description": "Target platform hint (cli, telegram, discord, etc.).",
            },
            "dry_run": {
                "type": "boolean",
                "description": "If true, run composition + validation only and skip synthesis.",
            },
        },
        "required": ["text"],
    },
}

registry.register(
    name="voice_orchestrator",
    toolset="tts",
    schema=VOICE_ORCHESTRATOR_SCHEMA,
    handler=lambda args, **kw: voice_orchestrator_tool(
        text=args.get("text", ""),
        context=args.get("context"),
        identity_profile=args.get("identity_profile"),
        voice_profile=args.get("voice_profile"),
        style_profile=args.get("style_profile"),
        output_path=args.get("output_path"),
        platform=args.get("platform"),
        dry_run=bool(args.get("dry_run", False)),
        audio_path=args.get("audio_path"),
        transcribe_model=args.get("transcribe_model"),
    ),
    emoji="🎙️",
)
