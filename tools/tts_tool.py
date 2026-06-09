#!/usr/bin/env python3
"""
Text-to-Speech Tool Module

Supports a single production TTS provider:
- OpenVoice V2 (primary renderer) with a configured base voice under the OpenVoice stack.

Output formats:
- Opus (.ogg) for Telegram voice bubbles
- MP3 (.mp3) only when explicitly requested for file output

Configuration is loaded from ~/.hermes/config.yaml under the 'tts:' key.
The model sends text; the voice pipeline is fixed to OpenVoice.

Usage:
    from tools.tts_tool import text_to_speech_tool, check_tts_requirements

    result = text_to_speech_tool(text="Hello world")
"""

import asyncio
import datetime
import json
import logging
import os
import queue
import re
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from hermes_constants import get_hermes_home
from typing import Callable, Dict, Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy imports -- providers are imported only when actually used to avoid
# crashing in headless environments (SSH, Docker, WSL, no PortAudio).
# ---------------------------------------------------------------------------

def _import_edge_tts():
    """Lazy import edge_tts. Returns the module or raises ImportError."""
    import edge_tts
    return edge_tts

def _import_elevenlabs():
    """Lazy import ElevenLabs client. Returns the class or raises ImportError."""
    from elevenlabs.client import ElevenLabs
    return ElevenLabs

def _import_openai_client():
    """Lazy import OpenAI client. Returns the class or raises ImportError."""
    from openai import OpenAI as OpenAIClient
    return OpenAIClient

def _import_sounddevice():
    """Lazy import sounddevice. Returns the module or raises ImportError/OSError."""
    import sounddevice as sd
    return sd


# ===========================================================================
# Defaults
# ===========================================================================
DEFAULT_PROVIDER = "openvoice"
DEFAULT_EDGE_VOICE = "es-ES-ElviraNeural"
DEFAULT_ELEVENLABS_VOICE_ID = "pNInz6obpgDQGcFmaJgB"  # Adam
DEFAULT_ELEVENLABS_MODEL_ID = "eleven_multilingual_v2"
DEFAULT_ELEVENLABS_STREAMING_MODEL_ID = "eleven_flash_v2_5"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini-tts"
DEFAULT_OPENAI_VOICE = "alloy"
def _get_default_output_dir() -> str:
    from hermes_constants import get_hermes_dir
    return str(get_hermes_dir("cache/audio", "audio_cache"))

DEFAULT_OUTPUT_DIR = _get_default_output_dir()
MAX_TEXT_LENGTH = 4000

# OpenVoice lazy-load cache keyed by config/runtime tuple
_OPENVOICE_CACHE: Dict[str, Any] = {}


# ===========================================================================
# Config loader -- reads tts: section from ~/.hermes/config.yaml
# ===========================================================================
def _load_tts_config() -> Dict[str, Any]:
    """
    Load TTS configuration from ~/.hermes/config.yaml.

    Returns a dict with provider settings. Falls back to defaults
    for any missing fields.
    """
    try:
        from hermes_cli.config import load_config
        config = load_config()
        return config.get("tts", {})
    except ImportError:
        logger.debug("hermes_cli.config not available, using default TTS config")
        return {}
    except Exception as e:
        logger.warning("Failed to load TTS config: %s", e, exc_info=True)
        return {}


def _get_provider(tts_config: Dict[str, Any]) -> str:
    """Get the configured TTS provider name."""
    return (tts_config.get("provider") or DEFAULT_PROVIDER).lower().strip()


# ===========================================================================
# ffmpeg Opus conversion (Edge TTS MP3 -> OGG Opus for Telegram)
# ===========================================================================
def _has_ffmpeg() -> bool:
    """Check if ffmpeg is available on the system."""
    if shutil.which("ffmpeg") is not None:
        return True
    try:
        from imageio_ffmpeg import get_ffmpeg_exe
        return bool(get_ffmpeg_exe())
    except Exception:
        return False


def _convert_to_opus(mp3_path: str) -> Optional[str]:
    """
    Convert an MP3 file to OGG Opus format for Telegram voice bubbles.

    Args:
        mp3_path: Path to the input MP3 file.

    Returns:
        Path to the .ogg file, or None if conversion fails.
    """
    if not _has_ffmpeg():
        return None

    ffmpeg = _resolve_ffmpeg_executable()
    if not ffmpeg:
        return None

    ogg_path = mp3_path.rsplit(".", 1)[0] + ".ogg"
    try:
        result = subprocess.run(
            [ffmpeg, "-i", mp3_path, "-acodec", "libopus",
             "-ac", "1", "-b:a", "64k", "-vbr", "off", ogg_path, "-y"],
            capture_output=True, timeout=30,
        )
        if result.returncode != 0:
            logger.warning("ffmpeg conversion failed with return code %d: %s", 
                          result.returncode, result.stderr.decode('utf-8', errors='ignore')[:200])
            return None
        if os.path.exists(ogg_path) and os.path.getsize(ogg_path) > 0:
            return ogg_path
    except subprocess.TimeoutExpired:
        logger.warning("ffmpeg OGG conversion timed out after 30s")
    except Exception as e:
        logger.warning("ffmpeg OGG conversion failed: %s", e, exc_info=True)
    return None


def _resolve_ffmpeg_executable() -> str | None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        return ffmpeg
    try:
        from imageio_ffmpeg import get_ffmpeg_exe
        ffmpeg = get_ffmpeg_exe()
        return ffmpeg or None
    except Exception:
        return None


def _convert_audio_file(src_path: str, output_path: str) -> str:
    """Convert an audio file to the requested output format."""
    if src_path == output_path:
        return output_path

    if output_path.endswith(".wav"):
        shutil.copy2(src_path, output_path)
        return output_path

    ffmpeg = _resolve_ffmpeg_executable()
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required to convert OpenVoice output to non-WAV formats")

    cmd = [ffmpeg, "-i", src_path, "-y", "-loglevel", "error"]
    if output_path.endswith((".ogg", ".oga")):
        cmd.extend(["-acodec", "libopus", "-ac", "1", "-b:a", "64k", "-vbr", "off"])
    result = subprocess.run(
        cmd + [output_path],
        capture_output=True,
        timeout=60,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="ignore").strip()
        raise RuntimeError(f"ffmpeg conversion failed: {stderr or 'unknown error'}")
    return output_path


def _generate_silence(path: str, duration_ms: int, sample_rate: int = 48000) -> str:
    ffmpeg = _resolve_ffmpeg_executable()
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required to generate silence segments")
    duration = max(0.0, duration_ms / 1000.0)
    if duration <= 0:
        return path
    result = subprocess.run(
        [
            ffmpeg,
            "-f", "lavfi",
            "-i", f"anullsrc=channel_layout=mono:sample_rate={sample_rate}",
            "-t", str(duration),
            "-y",
            "-loglevel", "error",
            path,
        ],
        capture_output=True,
        timeout=60,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="ignore").strip()
        raise RuntimeError(f"silence generation failed: {stderr or 'unknown error'}")
    return path


def _apply_pitch_contour(src_path: str, output_path: str, strength: float = 0.05, sections: int = 3) -> str:
    """Apply a gentle rising pitch contour across an audio phrase.

    The phrase starts slightly lower and ends about `strength` higher, with a
    mild mid-phrase lift to avoid a flat, monotone delivery.
    """
    import wave

    ffmpeg = _resolve_ffmpeg_executable()
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required to apply pitch contour")

    sections = max(2, int(sections or 3))
    strength = max(0.0, float(strength or 0.0))
    if strength < 0.01:
        shutil.copy2(src_path, output_path)
        return output_path

    with wave.open(src_path, "rb") as wf:
        frames = wf.getnframes()
        rate = wf.getframerate() or 48000
    duration = frames / float(rate or 48000)
    if duration <= 0.05:
        shutil.copy2(src_path, output_path)
        return output_path

    tmp_dir = Path(output_path).parent
    tmp_dir.mkdir(parents=True, exist_ok=True)
    section_files: list[str] = []
    boundaries = [duration * (i / sections) for i in range(sections + 1)]
    start_factor = 1.0 - (strength * 0.30)
    end_factor = 1.0 + strength
    for idx in range(sections):
        start = boundaries[idx]
        end = boundaries[idx + 1]
        if idx == sections - 1:
            end = duration
        blend = idx / max(sections - 1, 1)
        factor = start_factor + ((end_factor - start_factor) * blend)
        factor = max(0.92, min(1.08, factor))
        temp_section = str(tmp_dir / f"pitch_contour_{Path(src_path).stem}_{idx:02d}.wav")
        result = subprocess.run(
            [
                ffmpeg,
                "-i", src_path,
                "-filter_complex",
                f"[0:a]atrim=start={start:.6f}:end={end:.6f},asetpts=PTS-STARTPTS,asetrate=48000*{factor:.8f},atempo={1.0 / factor:.8f},aresample=48000[a]",
                "-map", "[a]",
                "-ac", "1",
                "-ar", "48000",
                "-c:a", "pcm_s16le",
                "-y",
                "-loglevel", "error",
                temp_section,
            ],
            capture_output=True,
            timeout=60,
        )
        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="ignore").strip()
            raise RuntimeError(f"pitch contour section failed: {stderr or 'unknown error'}")
        section_files.append(temp_section)

    if len(section_files) == 1:
        shutil.copy2(section_files[0], output_path)
        return output_path

    concat_list = tmp_dir / f"pitch_contour_{Path(src_path).stem}_concat.txt"
    with open(concat_list, "w", encoding="utf-8") as f:
        for p in section_files:
            f.write(f"file '{Path(p).as_posix()}'\n")

    result = subprocess.run(
        [
            ffmpeg,
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_list),
            "-ac", "1",
            "-ar", "48000",
            "-c:a", "pcm_s16le",
            "-y",
            "-loglevel", "error",
            output_path,
        ],
        capture_output=True,
        timeout=60,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="ignore").strip()
        raise RuntimeError(f"pitch contour concat failed: {stderr or 'unknown error'}")
    return output_path


def _apply_tempo_gain(src_path: str, output_path: str, tempo: float = 1.0, gain: float = 1.0) -> str:
    """Apply a small tempo and gain adjustment to an audio segment."""
    ffmpeg = _resolve_ffmpeg_executable()
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required to apply tempo and gain")
    tempo = max(0.5, min(2.0, float(tempo or 1.0)))
    gain = max(0.1, min(3.0, float(gain or 1.0)))
    result = subprocess.run(
        [
            ffmpeg,
            "-i", src_path,
            "-af", f"atempo={tempo:.8f},volume={gain:.4f}",
            "-ac", "1",
            "-ar", "48000",
            "-c:a", "pcm_s16le",
            "-y",
            "-loglevel", "error",
            output_path,
        ],
        capture_output=True,
        timeout=60,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="ignore").strip()
        raise RuntimeError(f"tempo/gain adjustment failed: {stderr or 'unknown error'}")
    return output_path


# ===========================================================================
# Provider: Edge TTS (free)
# ===========================================================================
async def _generate_edge_tts(text: str, output_path: str, tts_config: Dict[str, Any]) -> str:
    """Generate audio using Edge TTS.

    This is an internal OpenVoice base-voice helper only. The production
    TTS provider exposed by text_to_speech_tool() remains OpenVoice.
    Accepts rate/pitch from tts_config["edge"] for per-segment prosody.
    """
    _edge_tts = _import_edge_tts()
    edge_config = tts_config.get("edge", {})
    voice = edge_config.get("voice", DEFAULT_EDGE_VOICE)
    rate = edge_config.get("rate", "+0%")
    pitch = edge_config.get("pitch", "+0Hz")

    communicate = _edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    await communicate.save(output_path)
    return output_path


# ===========================================================================
# Provider: ElevenLabs (premium)
# ===========================================================================
def _generate_elevenlabs(text: str, output_path: str, tts_config: Dict[str, Any]) -> str:
    """
    Generate audio using ElevenLabs.

    Args:
        text: Text to convert.
        output_path: Where to save the audio file.
        tts_config: TTS config dict.

    Returns:
        Path to the saved audio file.
    """
    api_key = os.getenv("ELEVENLABS_API_KEY", "")
    if not api_key:
        raise ValueError("ELEVENLABS_API_KEY not set. Get one at https://elevenlabs.io/")

    el_config = tts_config.get("elevenlabs", {})
    voice_id = el_config.get("voice_id", DEFAULT_ELEVENLABS_VOICE_ID)
    model_id = el_config.get("model_id", DEFAULT_ELEVENLABS_MODEL_ID)

    # Determine output format based on file extension
    if output_path.endswith(".ogg"):
        output_format = "opus_48000_64"
    else:
        output_format = "mp3_44100_128"

    ElevenLabs = _import_elevenlabs()
    client = ElevenLabs(api_key=api_key)
    audio_generator = client.text_to_speech.convert(
        text=text,
        voice_id=voice_id,
        model_id=model_id,
        output_format=output_format,
    )

    # audio_generator yields chunks -- write them all
    with open(output_path, "wb") as f:
        for chunk in audio_generator:
            f.write(chunk)

    return output_path


# ===========================================================================
# Provider: OpenAI TTS
# ===========================================================================
def _generate_openai_tts(text: str, output_path: str, tts_config: Dict[str, Any]) -> str:
    """
    Generate audio using OpenAI TTS.

    Args:
        text: Text to convert.
        output_path: Where to save the audio file.
        tts_config: TTS config dict.

    Returns:
        Path to the saved audio file.
    """
    api_key = os.getenv("VOICE_TOOLS_OPENAI_KEY", "")
    if not api_key:
        raise ValueError("VOICE_TOOLS_OPENAI_KEY not set. Get one at https://platform.openai.com/api-keys")

    oai_config = tts_config.get("openai", {})
    model = oai_config.get("model", DEFAULT_OPENAI_MODEL)
    voice = oai_config.get("voice", DEFAULT_OPENAI_VOICE)
    base_url = oai_config.get("base_url", "https://api.openai.com/v1")

    # Determine response format from extension
    if output_path.endswith(".ogg"):
        response_format = "opus"
    else:
        response_format = "mp3"

    OpenAIClient = _import_openai_client()
    client = OpenAIClient(api_key=api_key, base_url=base_url)
    response = client.audio.speech.create(
        model=model,
        voice=voice,
        input=text,
        response_format=response_format,
    )

    response.stream_to_file(output_path)
    return output_path


# ===========================================================================
# OpenVoice V2 (primary voice engine)
# ===========================================================================

def _import_openvoice_modules():
    """Lazy import OpenVoice V2 dependencies."""
    from openvoice.api import ToneColorConverter
    return ToneColorConverter


def _import_melotts() -> Any:
    """Lazy import MeloTTS. Returns the TTS class or raises ImportError."""
    from melo.api import TTS as MeloTTS
    return MeloTTS


def _check_melotts_available() -> bool:
    """Check if MeloTTS is importable."""
    try:
        _import_melotts()
        return True
    except Exception:
        return False


def _check_openvoice_available() -> bool:
    """Check if OpenVoice V2 dependencies are importable."""
    try:
        _import_openvoice_modules()
        return True
    except Exception:
        return False


def _openvoice_config(tts_config: Dict[str, Any]) -> Dict[str, Any]:
    cfg = tts_config.get("openvoice", {}) or {}
    default_reference = Path(get_hermes_home()) / "openvoice" / "reference" / "example_reference.mp3"
    return {
        "version": cfg.get("version", "v2"),
        "language": cfg.get("language", "es"),
        "speed": float(cfg.get("speed", 1.0) or 1.0),
        "reference_audio": cfg.get("reference_audio") or cfg.get("ref_audio") or cfg.get("reference") or str(default_reference),
        "checkpoints_dir": str(Path(cfg.get("checkpoints_dir") or (Path(get_hermes_home()) / "openvoice" / "checkpoints_v2"))),
        "cache_dir": str(Path(cfg.get("cache_dir") or (Path(get_hermes_home()) / "cache" / "openvoice"))),
        "converter_message": cfg.get("converter_message", "@Hermes"),
        # Edge is the practical default base voice in this environment: it is
        # installed, lighter than MeloTTS, and lets OpenVoice run reliably
        # without a fragile extra MeCab/fugashi stack.
        "base_provider": (cfg.get("base_provider") or "edge").strip().lower(),
        "prosody_mode": (cfg.get("prosody_mode") or "natural").strip().lower(),
        "prosody_jitter": float(cfg.get("prosody_jitter", 0.08) or 0.08),
        "prosody_pause_scale": float(cfg.get("prosody_pause_scale", 1.05) or 1.05),
        "pitch_semitones": float(cfg.get("pitch_semitones", 0.0) or 0.0),
        "pitch_contour_strength": float(cfg.get("pitch_contour_strength", 0.0) or 0.0),
        "pitch_contour_sections": int(cfg.get("pitch_contour_sections", 4) or 4),
        # MeloTTS-specific prosody parameters
        "melotts_language": (cfg.get("melotts_language") or "ES").strip().upper(),
        "melotts_sdp_ratio": float(cfg.get("melotts_sdp_ratio", 0.3) or 0.3),
        "melotts_noise_scale": float(cfg.get("melotts_noise_scale", 0.65) or 0.65),
        "melotts_noise_scale_w": float(cfg.get("melotts_noise_scale_w", 0.8) or 0.8),
        # tau controls OpenVoice conversion intensity: 0.1=subtle, 0.3=balanced, 0.6=strong
        "tau": float(cfg.get("tau", 0.3) or 0.3),
        # Fixed pre-computed src_se path for MeloTTS ES (avoids per-segment extraction)
        "melotts_src_se": cfg.get("melotts_src_se") or str(
            Path(cfg.get("checkpoints_dir") or (Path(get_hermes_home()) / "openvoice" / "checkpoints_v2"))
            / "base_speakers" / "ses" / "es.pth"
        ),
    }


def _generate_openvoice_v2(text: str, output_path: str, tts_config: Dict[str, Any]) -> str:
    """Generate audio using a configurable base speaker plus OpenVoice tone conversion.

    v2 path:
    - split into natural clauses
    - vary speed slightly per clause
    - insert pauses between clauses
    - convert with OpenVoice per clause when possible
    - concatenate into the requested output
    """
    import copy
    import tempfile
    import torch

    def _split_phrases(src: str) -> list[str]:
        src = (src or "").strip()
        if not src:
            return []

        def _merge_fragments(fragments: list[str], target_min: int = 52, target_max: int = 118) -> list[str]:
            """Merge tiny fragments so we speak phrases, not isolated words."""
            merged: list[str] = []
            buffer = ""
            connector_words = {
                "y", "e", "o", "u", "pero", "aunque", "porque", "que", "si", "cuando",
                "mientras", "entonces", "luego", "además", "sin", "con", "de", "del", "al",
                "por", "para", "en", "sobre", "sin embargo", "por eso", "por lo tanto",
            }

            def _starts_like_connector(text: str) -> bool:
                first = re.findall(r"[a-záéíóúüñ]+", text.lower())[:1]
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
                    # Keep the flow continuous unless the phrase is already rich enough.
                    buffer = candidate
                else:
                    merged.append(buffer)
                    buffer = frag
            if buffer:
                merged.append(buffer)
            return merged

        # Prefer sentence boundaries first; don't atomize the text too early.
        sentence_parts = [p.strip() for p in re.split(r"(?<=[\.\?\!…])\s+|\n+", src) if p and p.strip()]
        if len(sentence_parts) > 1:
            return sentence_parts

        sentence = sentence_parts[0] if sentence_parts else src
        if len(sentence) <= 115:
            return [sentence]

        # Only split on soft punctuation when the sentence is actually long.
        raw_clauses = [p.strip() for p in re.split(r"(?<=[,;:—–])\s+", sentence) if p and p.strip()]
        if len(raw_clauses) <= 1:
            # One surgical split for extremely long single clauses.
            if len(sentence) > 150 and "," in sentence:
                left, right = sentence.split(",", 1)
                raw_clauses = [left.strip() + ",", right.strip()]
            else:
                raw_clauses = [sentence]

        # Merge fragments back into phrase-sized chunks to preserve fluency.
        parts = _merge_fragments(raw_clauses)
        if len(parts) > 1:
            return parts
        return parts or [src]

    def _segment_profile(segment: str) -> str:
        seg = (segment or "").strip().lower()
        words = re.findall(r"[a-záéíóúüñ]+", seg)
        if not words:
            return "neutral"

        connectors = {
            "y", "e", "o", "u", "pero", "aunque", "porque", "que", "si", "cuando",
            "mientras", "entonces", "luego", "además", "sin", "con", "de", "del", "al",
            "por", "para", "en", "sobre", "sin embargo", "por eso", "por lo tanto",
        }
        starts_with_subject = words[0] in {
            "yo", "tu", "tú", "el", "él", "ella", "nosotros", "nosotras", "vosotros", "vosotras", "ellos", "ellas", "uno", "una", "mi", "mis", "su", "sus"
        }
        starts_with_connector = words[0] in connectors
        verbish = any(
            w.endswith(("ar", "er", "ir", "ando", "iendo", "ado", "ada", "ido", "ida", "amos", "emos", "imos", "aré", "eré", "iré", "aba", "ía", "ó", "é", "í"))
            or w in {"es", "son", "ser", "estar", "está", "están", "tener", "tiene", "tienen", "hacer", "hace", "hacen", "decir", "dice", "dicen", "ir", "va", "van"}
            for w in words
        )
        adjectiveish = any(
            w.endswith(("oso", "osa", "ivo", "iva", "al", "able", "ible", "ante", "ente", "ado", "ada", "ido", "ida", "ario", "aria"))
            for w in words
        )
        closing_mark = seg.endswith((".", "…", "...", "!", "?"))
        if starts_with_connector:
            return "connector"
        if adjectiveish and not verbish:
            return "adjective"
        if starts_with_subject:
            return "subject"
        if verbish:
            return "verb"
        if closing_mark:
            return "closing"
        return "neutral"

    def _deterministic_jitter(segment: str, idx: int, spread: int, salt: str) -> int:
        """Return a small, stable jitter without relying on randomness."""
        if spread <= 0:
            return 0
        seed = 0
        for ch in f"{salt}|{idx}|{segment}":
            seed = (seed * 131 + ord(ch)) & 0xFFFFFFFF
        return int(seed % (2 * spread + 1)) - spread

    def _speed_for_segment(segment: str, idx: int, total: int, base_speed: float = 1.0) -> float:
        # Content-aware speed variation: slow down at semantic breaks,
        # slightly faster for connectors and filler clauses.
        profile = _segment_profile(segment)
        delta = {
            "connector": 0.02,   # connectors flow quickly between ideas
            "subject": -0.03,    # new subjects get slight emphasis/weight
            "verb": -0.02,       # action verbs carry semantic weight
            "closing": -0.04,    # closing phrases land slower and final
            "adjective": -0.01,  # adjectives are measured
        }.get(profile, 0.0)
        # Natural bookending: start and end slightly slower
        if idx == 0:
            delta -= 0.01
        elif idx == total - 1:
            delta -= 0.02
        return max(0.85, min(1.15, base_speed + delta))

    def _pause_ms(segment: str, scale: float, idx: int, total: int) -> int:
        seg = segment.strip()
        profile = _segment_profile(seg)
        pause = 0
        if seg.endswith(("...", "…")):
            pause = 280
        elif seg.endswith((".", "!", "?")):
            pause = 170
        elif seg.endswith((";", ":", "—", "–")):
            pause = 110
        elif seg.endswith(","):
            pause = 60
        elif profile == "closing":
            pause = 135
        elif profile == "connector":
            pause = 40
        elif profile == "verb":
            pause = 50
        elif profile == "subject":
            pause = 45
        elif profile == "adjective":
            pause = 65
        if len(seg) > 110:
            pause += 45
        if idx == total - 1:
            pause += 90
        elif idx == 0:
            pause += 15
        pause += int(_deterministic_jitter(seg, idx, 12, "pause"))
        pause = int(max(20, pause * scale))
        return pause

    cfg = _openvoice_config(tts_config)
    checkpoints_dir = Path(cfg["checkpoints_dir"])
    cache_dir = Path(cfg["cache_dir"])
    converter_dir = checkpoints_dir / "converter"

    config_path = converter_dir / "config.json"
    ckpt_path = converter_dir / "checkpoint.pth"
    if not config_path.exists() or not ckpt_path.exists():
        raise FileNotFoundError(
            f"OpenVoice checkpoints not found in {converter_dir}. Install checkpoints_v2 under {checkpoints_dir}"
        )

    ToneColorConverter = _import_openvoice_modules()
    device = "cuda" if torch.cuda.is_available() else "cpu"

    conv_cache_key = (str(converter_dir), device)
    if conv_cache_key not in _OPENVOICE_CACHE:
        converter = ToneColorConverter(str(config_path), device=device)
        converter.load_ckpt(str(ckpt_path))
        _OPENVOICE_CACHE[conv_cache_key] = converter
    tone_color_converter = _OPENVOICE_CACHE[conv_cache_key]

    reference_audio = cfg["reference_audio"]
    target_se = None
    if reference_audio and os.path.exists(reference_audio):
        try:
            target_cache_key = (str(Path(reference_audio).resolve()), str(converter_dir), device)
            if target_cache_key in _OPENVOICE_CACHE:
                target_se = _OPENVOICE_CACHE[target_cache_key]
            else:
                cache_dir.mkdir(parents=True, exist_ok=True)
                target_se_path = cache_dir / f"target_se_{Path(reference_audio).stem}.pth"
                if target_se_path.exists():
                    target_se = torch.load(str(target_se_path), map_location=device)
                else:
                    target_se = tone_color_converter.extract_se(reference_audio, se_save_path=str(target_se_path))
                _OPENVOICE_CACHE[target_cache_key] = target_se
        except Exception as exc:
            logger.warning("OpenVoice target speaker extraction failed, using base voice only: %s", exc)
            target_se = None

    tmp_dir = Path(tempfile.gettempdir()) / "hermes_openvoice"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    base_provider = cfg.get("base_provider", "edge")

    parts = _split_phrases(text)
    if not parts:
        parts = [text]

    generated_files: list[str] = []
    total = len(parts)
    prosody_mode = cfg.get("prosody_mode", "natural")
    pause_scale = float(cfg.get("prosody_pause_scale", 1.05) or 1.05)
    pitch_semitones = float(cfg.get("pitch_semitones", 0.0) or 0.0)
    pitch_contour_strength = float(cfg.get("pitch_contour_strength", 0.0) or 0.0)
    pitch_contour_sections = int(cfg.get("pitch_contour_sections", 4) or 4)
    conv_tau = float(cfg.get("tau", 0.3) or 0.3)

    # MeloTTS state — loaded once, reused across all segments for efficiency
    _melotts_model: Any = None
    _melotts_speaker_id: Optional[int] = None

    def _get_melotts():
        nonlocal _melotts_model, _melotts_speaker_id
        if _melotts_model is None:
            MeloTTS = _import_melotts()
            lang = cfg.get("melotts_language", "ES")
            _melotts_model = MeloTTS(language=lang, device=device)
            spk2id = _melotts_model.hps.data.spk2id
            # HParams object — access as attribute, not dict.get()
            _melotts_speaker_id = getattr(spk2id, lang, 0) if hasattr(spk2id, lang) else (
                spk2id.get(lang, 0) if isinstance(spk2id, dict) else 0
            )
        return _melotts_model, _melotts_speaker_id

    def _generate_melotts(segment_text: str, src_path: str, seg_speed: float) -> None:
        """Generate base audio with MeloTTS ES — best quality base for Spanish."""
        ov_cfg = cfg
        sdp_ratio = float(ov_cfg.get("melotts_sdp_ratio", 0.3) or 0.3)
        noise_scale = float(ov_cfg.get("melotts_noise_scale", 0.65) or 0.65)
        noise_scale_w = float(ov_cfg.get("melotts_noise_scale_w", 0.8) or 0.8)
        model, spk_id = _get_melotts()
        model.tts_to_file(
            segment_text,
            speaker_id=spk_id,
            output_path=src_path,
            speed=seg_speed,
            sdp_ratio=sdp_ratio,
            noise_scale=noise_scale,
            noise_scale_w=noise_scale_w,
            quiet=True,
        )

    def _generate_base(segment_text: str, src_path: str, local_tts_config: Dict[str, Any]) -> None:
        seg_ov = local_tts_config.get("openvoice", {})
        seg_speed = float(seg_ov.get("speed", 1.0) or 1.0)
        if base_provider == "melotts":
            _generate_melotts(segment_text, src_path, seg_speed)
        elif base_provider == "neutts":
            if not _check_neutts_available():
                raise RuntimeError("OpenVoice base provider NeuTTS is not available")
            _generate_neutts(segment_text, src_path, local_tts_config)
        elif base_provider == "edge":
            base_edge_config = dict(local_tts_config)
            base_edge_config["edge"] = dict(base_edge_config.get("edge", {}))
            base_edge_config["provider"] = "edge"
            asyncio.run(_generate_edge_tts(segment_text, src_path, base_edge_config))
        elif base_provider == "openai":
            _generate_openai_tts(segment_text, src_path, local_tts_config)
        elif base_provider == "elevenlabs":
            _generate_elevenlabs(segment_text, src_path, local_tts_config)
        else:
            raise ValueError(f"Unsupported OpenVoice base provider: {base_provider}")

    for idx, segment in enumerate(parts):
        segment_safe = re.sub(r"[^a-zA-Z0-9]+", "_", segment)[:24] or f"seg_{idx:02d}"
        seg_src = str(tmp_dir / f"openvoice_{idx:03d}_{segment_safe}_src.wav")
        seg_out = str(tmp_dir / f"openvoice_{idx:03d}_{segment_safe}_out.wav")
        seg_cfg = copy.deepcopy(tts_config)
        seg_openvoice = dict(seg_cfg.get("openvoice", {}))
        seg_openvoice.update(cfg)
        if prosody_mode != "static":
            seg_openvoice["speed"] = _speed_for_segment(segment, idx, total, base_speed=cfg.get("speed", 1.0))
        seg_cfg["openvoice"] = seg_openvoice

        # Pass per-segment speed to Edge TTS as a native rate parameter.
        # Synthesis-time rate is clean and natural; post-processing atempo
        # degrades formants and causes artifacts on short segments.
        if base_provider == "edge" and prosody_mode != "static":
            seg_spd = float(seg_openvoice.get("speed", 1.0))
            rate_pct = int(round((seg_spd - 1.0) * 100))
            edge_conf = dict(seg_cfg.get("edge", {}))
            edge_conf["rate"] = f"{rate_pct:+d}%"
            seg_cfg["edge"] = edge_conf

        _generate_base(segment, seg_src, seg_cfg)
        final_seg = seg_src

        if target_se is not None:
            try:
                # For MeloTTS base: use the pre-computed fixed src_se (exact match,
                # fast, consistent). For other bases: extract per-segment.
                if base_provider == "melotts":
                    melotts_se_path = cfg.get("melotts_src_se", "")
                    melotts_src_se_key = ("melotts_fixed", str(melotts_se_path))
                    if melotts_src_se_key in _OPENVOICE_CACHE:
                        source_se = _OPENVOICE_CACHE[melotts_src_se_key]
                    elif melotts_se_path and Path(melotts_se_path).exists():
                        source_se = torch.load(melotts_se_path, map_location=device)
                        _OPENVOICE_CACHE[melotts_src_se_key] = source_se
                    else:
                        source_se = tone_color_converter.extract_se(seg_src, se_save_path=str(cache_dir / f"source_se_{idx:03d}.pth"))
                else:
                    source_cache_key = (str(Path(seg_src).resolve()), str(converter_dir), device)
                    if source_cache_key in _OPENVOICE_CACHE:
                        source_se = _OPENVOICE_CACHE[source_cache_key]
                    else:
                        source_se = tone_color_converter.extract_se(seg_src, se_save_path=str(cache_dir / f"source_se_{idx:03d}.pth"))
                        _OPENVOICE_CACHE[source_cache_key] = source_se

                tone_color_converter.convert(
                    audio_src_path=seg_src,
                    src_se=source_se,
                    tgt_se=target_se,
                    output_path=seg_out,
                    tau=conv_tau,
                    message=cfg["converter_message"],
                )
                final_seg = seg_out
            except Exception as exc:
                logger.warning("OpenVoice conversion failed for segment %s, returning base voice only: %s", idx, exc)

        if pitch_contour_strength > 0.0:
            contour_out = str(tmp_dir / f"openvoice_{idx:03d}_{segment_safe}_pitch.wav")
            try:
                _apply_pitch_contour(final_seg, contour_out, strength=pitch_contour_strength, sections=pitch_contour_sections)
                final_seg = contour_out
            except Exception as exc:
                logger.warning("OpenVoice pitch contour failed for segment %s, keeping original: %s", idx, exc)

        generated_files.append(final_seg)

        if idx < total - 1:
            pause_ms = _pause_ms(segment, pause_scale, idx, total)
            if pause_ms > 0:
                pause_file = str(tmp_dir / f"openvoice_{idx:03d}_pause.wav")
                _generate_silence(pause_file, pause_ms)
                generated_files.append(pause_file)

    if not generated_files:
        raise RuntimeError("OpenVoice generation failed: no segments were rendered")

    combined_wav = str(tmp_dir / "openvoice_combined.wav")
    if len(generated_files) == 1:
        shutil.copy2(generated_files[0], combined_wav)
    else:
        concat_list = tmp_dir / "concat_list.txt"
        with open(concat_list, "w", encoding="utf-8") as f:
            for p in generated_files:
                f.write(f"file '{Path(p).as_posix()}'\n")
        ffmpeg = _resolve_ffmpeg_executable()
        if not ffmpeg:
            raise RuntimeError("ffmpeg is required to concatenate OpenVoice segments")
        result = subprocess.run(
            [
                ffmpeg,
                "-f", "concat",
                "-safe", "0",
                "-i", str(concat_list),
                "-ac", "1",
                "-ar", "48000",
                "-c:a", "pcm_s16le",
                "-y",
                "-loglevel", "error",
                combined_wav,
            ],
            capture_output=True,
            timeout=120,
        )
        if result.returncode != 0:
            raise RuntimeError(f"OpenVoice concat failed: {result.stderr.decode('utf-8', errors='ignore').strip() or 'unknown error'}")

    pitched_wav = combined_wav
    if abs(pitch_semitones) >= 0.05:
        ffmpeg = _resolve_ffmpeg_executable()
        if not ffmpeg:
            raise RuntimeError("ffmpeg is required to apply OpenVoice pitch shaping")
        pitch_factor = 2 ** (pitch_semitones / 12.0)
        pitch_wav = str(tmp_dir / "openvoice_pitch.wav")
        result = subprocess.run(
            [
                ffmpeg,
                "-i", combined_wav,
                "-af", f"asetrate=48000*{pitch_factor:.8f},atempo={1.0 / pitch_factor:.8f},aresample=48000",
                "-ac", "1",
                "-ar", "48000",
                "-c:a", "pcm_s16le",
                "-y",
                "-loglevel", "error",
                pitch_wav,
            ],
            capture_output=True,
            timeout=120,
        )
        if result.returncode != 0:
            raise RuntimeError(f"OpenVoice pitch shaping failed: {result.stderr.decode('utf-8', errors='ignore').strip() or 'unknown error'}")
        pitched_wav = pitch_wav

    _convert_audio_file(pitched_wav, output_path)
    return output_path


# ===========================================================================
# NeuTTS (local, on-device TTS via neutts_cli)
# ===========================================================================

def _check_neutts_available() -> bool:
    """Check if the neutts engine is importable (installed locally)."""
    try:
        import importlib.util
        return importlib.util.find_spec("neutts") is not None
    except Exception:
        return False


def _default_neutts_ref_audio() -> str:
    """Return path to the bundled default voice reference audio."""
    return str(Path(__file__).parent / "neutts_samples" / "jo.wav")


def _default_neutts_ref_text() -> str:
    """Return path to the bundled default voice reference transcript."""
    return str(Path(__file__).parent / "neutts_samples" / "jo.txt")


def _generate_neutts(text: str, output_path: str, tts_config: Dict[str, Any]) -> str:
    """Generate speech using the local NeuTTS engine.

    Runs synthesis in a subprocess via tools/neutts_synth.py to keep the
    ~500MB model in a separate process that exits after synthesis.
    Outputs WAV; the caller handles conversion for Telegram if needed.
    """
    import sys

    neutts_config = tts_config.get("neutts", {})
    ref_audio = neutts_config.get("ref_audio", "") or _default_neutts_ref_audio()
    ref_text = neutts_config.get("ref_text", "") or _default_neutts_ref_text()
    model = neutts_config.get("model", "neuphonic/neutts-air-q4-gguf")
    device = neutts_config.get("device", "cpu")

    # NeuTTS outputs WAV natively — use a .wav path for generation,
    # let the caller convert to the final format afterward.
    wav_path = output_path
    if not output_path.endswith(".wav"):
        wav_path = output_path.rsplit(".", 1)[0] + ".wav"

    synth_script = str(Path(__file__).parent / "neutts_synth.py")
    cmd = [
        sys.executable, synth_script,
        "--text", text,
        "--out", wav_path,
        "--ref-audio", ref_audio,
        "--ref-text", ref_text,
        "--model", model,
        "--device", device,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        stderr = result.stderr.strip()
        # Filter out the "OK:" line from stderr
        error_lines = [l for l in stderr.splitlines() if not l.startswith("OK:")]
        raise RuntimeError(f"NeuTTS synthesis failed: {chr(10).join(error_lines) or 'unknown error'}")

    # If the caller wanted .mp3 or .ogg, convert from WAV
    if wav_path != output_path:
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            conv_cmd = [ffmpeg, "-i", wav_path, "-y", "-loglevel", "error", output_path]
            subprocess.run(conv_cmd, check=True, timeout=30)
            os.remove(wav_path)
        else:
            # No ffmpeg — just rename the WAV to the expected path
            os.rename(wav_path, output_path)

    return output_path


# ===========================================================================
# Main tool function
# ===========================================================================
def text_to_speech_tool(
    text: str,
    output_path: Optional[str] = None,
) -> str:
    """
    Convert text to speech audio.

    Reads provider/voice config from ~/.hermes/config.yaml (tts: section).
    The model sends text; the user configures voice and provider.

    On messaging platforms, the returned MEDIA:<path> tag is intercepted
    by the send pipeline and delivered as a native voice message.
    In CLI mode, the file is saved to ~/voice-memos/.

    Args:
        text: The text to convert to speech.
        output_path: Optional custom save path. Defaults to ~/voice-memos/<timestamp>.mp3

    Returns:
        str: JSON result with success, file_path, and optionally MEDIA tag.
    """
    if not text or not text.strip():
        return json.dumps({"success": False, "error": "Text is required"}, ensure_ascii=False)

    # Truncate very long text with a warning
    if len(text) > MAX_TEXT_LENGTH:
        logger.warning("TTS text too long (%d chars), truncating to %d", len(text), MAX_TEXT_LENGTH)
        text = text[:MAX_TEXT_LENGTH]

    tts_config = _load_tts_config()
    provider = _get_provider(tts_config)

    # Detect platform from gateway env var to choose the best output format.
    # Telegram voice bubbles require Opus (.ogg). OpenVoice is the only
    # supported renderer in this production path.
    platform = os.getenv("HERMES_SESSION_PLATFORM", "").lower()
    want_opus = (platform == "telegram")

    # Determine output path
    if output_path:
        file_path = Path(output_path).expanduser()
    else:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = Path(DEFAULT_OUTPUT_DIR)
        out_dir.mkdir(parents=True, exist_ok=True)
        if want_opus and provider == "openvoice":
            file_path = out_dir / f"tts_{timestamp}.ogg"
        else:
            file_path = out_dir / f"tts_{timestamp}.mp3"

    # Ensure parent directory exists
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_str = str(file_path)

    try:
        # Generate audio with the configured provider.
        # Production policy: OpenVoice is the primary renderer path, but if the
        # runtime environment lacks OpenVoice dependencies we fall back to Edge
        # TTS so voice delivery still works instead of going silent.
        if provider != "openvoice":
            return json.dumps({
                "success": False,
                "error": f"Unsupported TTS provider '{provider}'. OpenVoice is the only allowed renderer.",
            }, ensure_ascii=False)

        use_edge_fallback = False
        try:
            _import_openvoice_modules()
        except ImportError:
            use_edge_fallback = True
            logger.warning("OpenVoice dependencies missing; falling back to Edge TTS for voice output")

        if not use_edge_fallback:
            logger.info("Generating speech with OpenVoice V2...")
            try:
                _generate_openvoice_v2(text, file_str, tts_config)
            except Exception as exc:
                return json.dumps({
                    "success": False,
                    "error": f"OpenVoice generation failed: {exc}",
                }, ensure_ascii=False)
        else:
            tmp_edge_path = f"{file_str}.edge.mp3"
            try:
                asyncio.run(_generate_edge_tts(text, tmp_edge_path, tts_config))
                if file_str.endswith(".ogg"):
                    converted = _convert_to_opus(tmp_edge_path)
                    if converted and converted != file_str:
                        os.replace(converted, file_str)
                    elif os.path.exists(tmp_edge_path):
                        _convert_audio_file(tmp_edge_path, file_str)
                    else:
                        raise RuntimeError("Edge TTS generated no usable audio output")
                else:
                    _convert_audio_file(tmp_edge_path, file_str)
            except Exception as exc:
                return json.dumps({
                    "success": False,
                    "error": f"Edge TTS fallback failed: {exc}",
                }, ensure_ascii=False)
            finally:
                try:
                    if os.path.exists(tmp_edge_path):
                        os.remove(tmp_edge_path)
                except OSError:
                    pass

        # Check the file was actually created
        if not os.path.exists(file_str) or os.path.getsize(file_str) == 0:
            return json.dumps({
                "success": False,
                "error": f"TTS generation produced no output (provider: {provider})"
            }, ensure_ascii=False)

        # Try Opus conversion for Telegram compatibility.
        # OpenVoice may emit an OGG container that is actually Vorbis; Telegram
        # voice notes require Opus, so we must force a re-encode when the target
        # is a Telegram voice path.
        voice_compatible = False
        if provider == "openvoice" and want_opus and file_str.endswith(".ogg"):
            ffmpeg = _resolve_ffmpeg_executable()
            if not ffmpeg:
                return json.dumps({
                    "success": False,
                    "error": "ffmpeg is required to convert OpenVoice output to Telegram-compatible Opus",
                }, ensure_ascii=False)

            tmp_opus = f"{file_str}.tmp.opus"
            try:
                proc = subprocess.run(
                    [
                        ffmpeg,
                        "-y",
                        "-loglevel", "error",
                        "-i", file_str,
                        "-c:a", "libopus",
                        "-b:a", "48k",
                        "-vbr", "on",
                        tmp_opus,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                if proc.returncode != 0:
                    raise RuntimeError(proc.stderr.strip() or "ffmpeg opus conversion failed")
                os.replace(tmp_opus, file_str)
                voice_compatible = True
            finally:
                try:
                    if os.path.exists(tmp_opus):
                        os.remove(tmp_opus)
                except OSError:
                    pass
        elif provider == "openvoice":
            voice_compatible = file_str.endswith(".ogg")

        file_size = os.path.getsize(file_str)
        logger.info("TTS audio saved: %s (%s bytes, provider: %s)", file_str, f"{file_size:,}", provider)

        # Build response with MEDIA tag for platform delivery
        media_tag = f"MEDIA:{file_str}"
        if voice_compatible:
            media_tag = f"[[audio_as_voice]]\n{media_tag}"

        return json.dumps({
            "success": True,
            "file_path": file_str,
            "media_tag": media_tag,
            "provider": provider,
            "voice_compatible": voice_compatible,
        }, ensure_ascii=False)

    except ValueError as e:
        # Configuration errors (missing API keys, etc.)
        error_msg = f"TTS configuration error ({provider}): {e}"
        logger.error("%s", error_msg)
        return json.dumps({"success": False, "error": error_msg}, ensure_ascii=False)
    except FileNotFoundError as e:
        # Missing dependencies or files
        error_msg = f"TTS dependency missing ({provider}): {e}"
        logger.error("%s", error_msg, exc_info=True)
        return json.dumps({"success": False, "error": error_msg}, ensure_ascii=False)
    except Exception as e:
        # Unexpected errors
        error_msg = f"TTS generation failed ({provider}): {e}"
        logger.error("%s", error_msg, exc_info=True)
        return json.dumps({"success": False, "error": error_msg}, ensure_ascii=False)


# ===========================================================================
# Requirements check
# ===========================================================================
def check_tts_requirements() -> bool:
    """
    Check if the OpenVoice renderer is available.

    Returns:
        bool: True if OpenVoice can work.
    """
    try:
        _import_openvoice_modules()
        return True
    except Exception:
        return False


# ===========================================================================
# Streaming TTS: sentence-by-sentence pipeline for ElevenLabs
# ===========================================================================
# Sentence boundary pattern: punctuation followed by space or newline
_SENTENCE_BOUNDARY_RE = re.compile(r'(?<=[.!?])(?:\s|\n)|(?:\n\n)')

# Markdown stripping patterns (same as cli.py _voice_speak_response)
_MD_CODE_BLOCK = re.compile(r'```[\s\S]*?```')
_MD_LINK = re.compile(r'\[([^\]]+)\]\([^)]+\)')
_MD_URL = re.compile(r'https?://\S+')
_MD_BOLD = re.compile(r'\*\*(.+?)\*\*')
_MD_ITALIC = re.compile(r'\*(.+?)\*')
_MD_INLINE_CODE = re.compile(r'`(.+?)`')
_MD_HEADER = re.compile(r'^#+\s*', flags=re.MULTILINE)
_MD_LIST_ITEM = re.compile(r'^\s*[-*]\s+', flags=re.MULTILINE)
_MD_HR = re.compile(r'---+')
_MD_EXCESS_NL = re.compile(r'\n{3,}')
_AUDIO_VOICE_DIRECTIVE_RE = re.compile(r'\[\[audio_as_voice\]\]', flags=re.IGNORECASE)
_MEDIA_DIRECTIVE_RE = re.compile(r'MEDIA:\s*', flags=re.IGNORECASE)
_PATH_LIKE_TOKEN_RE = re.compile(r'(?<!\w)(?:[\w.-]+(?:/[\w.-]+)+|[\w.-]+(?:\\[\w.-]+)+)(?!\w)')
_TECHNICAL_TOKEN_RE = re.compile(r'(?<!\w)(?=[\w.-]*[_-])(?=[\w.-]*\d)[\w.-]{8,}(?!\w)')
_TECHNICAL_KEYWORD_RE = re.compile(r'\b(endpoint|api|ruta|url|path|registro|auth|login|token|webhook|payload|header|json|query|param(?:eter)?|bearer)\b', flags=re.IGNORECASE)


def _collapse_technical_sentences(text: str) -> str:
    """Remove or condense sentences that are still technical after token stripping."""
    chunks = re.split(r'(?<=[.!?])\s+|\n+', text)
    cleaned: list[str] = []
    for chunk in chunks:
        chunk = re.sub(r'\s+', ' ', chunk).strip()
        if not chunk:
            continue
        tech_signals = len(re.findall(r'[\\/{}\[\]<>:=@]', chunk)) + len(_TECHNICAL_KEYWORD_RE.findall(chunk))
        tech_signals += 1 if re.search(r'(?<!\w)[\w.-]*[_-][\w.-]*\d', chunk) else 0
        if tech_signals >= 2 or (tech_signals >= 1 and len(chunk.split()) > 6):
            cleaned.append('un dato técnico')
        else:
            cleaned.append(chunk)
    return ' '.join(cleaned).strip()


def _strip_markdown_for_tts(text: str) -> str:
    """Remove markdown and technical artifacts that shouldn't be spoken aloud."""
    text = _AUDIO_VOICE_DIRECTIVE_RE.sub(' ', text)
    text = _MEDIA_DIRECTIVE_RE.sub(' ', text)
    text = _MD_CODE_BLOCK.sub(' ', text)
    text = _MD_LINK.sub(r'\1', text)
    text = _MD_URL.sub('', text)
    text = _MD_BOLD.sub(r'\1', text)
    text = _MD_ITALIC.sub(r'\1', text)
    text = _MD_INLINE_CODE.sub(r'\1', text)
    text = _MD_HEADER.sub('', text)
    text = _MD_LIST_ITEM.sub('', text)
    text = _MD_HR.sub('', text)
    text = _PATH_LIKE_TOKEN_RE.sub(' ', text)
    text = _TECHNICAL_TOKEN_RE.sub(' ', text)
    text = _collapse_technical_sentences(text)
    text = _MD_EXCESS_NL.sub('\n\n', text)
    return text.strip()


def stream_tts_to_speaker(
    text_queue: queue.Queue,
    stop_event: threading.Event,
    tts_done_event: threading.Event,
    display_callback: Optional[Callable[[str], None]] = None,
):
    """Consume text deltas from *text_queue*, buffer them into sentences,
    and stream each sentence through ElevenLabs TTS to the speaker in
    real-time.

    Protocol:
        * The producer puts ``str`` deltas onto *text_queue*.
        * A ``None`` sentinel signals end-of-text (flush remaining buffer).
        * *stop_event* can be set to abort early (e.g. user interrupt).
        * *tts_done_event* is **set** in the ``finally`` block so callers
          waiting on it (continuous voice mode) know playback is finished.
    """
    tts_done_event.clear()

    try:
        # --- TTS client setup (OpenVoice-only) ---
        output_stream = None
        tts_config = _load_tts_config()
        if _get_provider(tts_config) != "openvoice":
            logger.warning("Streaming TTS disabled: OpenVoice is the only supported renderer")
            return

        try:
            _import_openvoice_modules()
        except ImportError:
            logger.warning("OpenVoice dependencies not available; streaming TTS disabled")
            return

        try:
            sd = _import_sounddevice()
            output_stream = sd.OutputStream(samplerate=24000, channels=1, dtype="int16")
            output_stream.start()
        except (ImportError, OSError) as exc:
            logger.debug("sounddevice not available: %s", exc)
            output_stream = None
        except Exception as exc:
            logger.warning("sounddevice OutputStream failed: %s", exc)
            output_stream = None

        sentence_buf = ""
        min_sentence_len = 20
        long_flush_len = 100
        queue_timeout = 0.5
        _spoken_sentences: list[str] = []  # track spoken sentences to skip duplicates
        # Regex to strip complete <think>...</think> blocks from buffer
        _think_block_re = re.compile(r'<think[\s>].*?</think>', flags=re.DOTALL)

        def _play_rendered_audio(audio_path: str):
            if output_stream is None:
                return
            ffmpeg = _resolve_ffmpeg_executable()
            if not ffmpeg:
                return
            wav_tmp = None
            try:
                import wave
                import numpy as _np
                tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
                wav_tmp = tmp.name
                tmp.close()
                result = subprocess.run(
                    [ffmpeg, "-i", audio_path, "-y", "-loglevel", "error", wav_tmp],
                    capture_output=True,
                    timeout=60,
                )
                if result.returncode != 0:
                    raise RuntimeError(result.stderr.decode("utf-8", errors="ignore").strip() or "unknown error")
                with wave.open(wav_tmp, "rb") as wf:
                    while not stop_event.is_set():
                        frames = wf.readframes(2048)
                        if not frames:
                            break
                        audio_array = _np.frombuffer(frames, dtype=_np.int16)
                        output_stream.write(audio_array.reshape(-1, 1))
            except Exception as exc:
                logger.warning("OpenVoice playback failed: %s", exc)
            finally:
                if wav_tmp:
                    try:
                        os.unlink(wav_tmp)
                    except OSError:
                        pass

        def _speak_sentence(sentence: str):
            """Display sentence and generate + play OpenVoice audio."""
            if stop_event.is_set():
                return
            cleaned = _strip_markdown_for_tts(sentence).strip()
            if not cleaned:
                return
            cleaned_lower = cleaned.lower().rstrip(".!,")
            for prev in _spoken_sentences:
                if prev.lower().rstrip(".!,") == cleaned_lower:
                    return
            _spoken_sentences.append(cleaned)
            if display_callback is not None:
                display_callback(sentence)
            if len(cleaned) > MAX_TEXT_LENGTH:
                cleaned = cleaned[:MAX_TEXT_LENGTH]
            tmp_audio = None
            try:
                from tools.tts_tool import text_to_speech_tool
                tmp = tempfile.NamedTemporaryFile(suffix=".ogg", delete=False)
                tmp_audio = tmp.name
                tmp.close()
                result_json = text_to_speech_tool(text=cleaned, output_path=tmp_audio)
                result = json.loads(result_json) if isinstance(result_json, str) else dict(result_json)
                if not result.get("success"):
                    logger.warning("OpenVoice sentence synthesis failed: %s", result.get("error", "unknown error"))
                    return
                _play_rendered_audio(result.get("file_path") or tmp_audio)
            except Exception as exc:
                logger.warning("OpenVoice sentence synthesis failed: %s", exc)
            finally:
                if tmp_audio:
                    try:
                        os.unlink(tmp_audio)
                    except OSError:
                        pass

        while not stop_event.is_set():
            # Read next delta from queue
            try:
                delta = text_queue.get(timeout=queue_timeout)
            except queue.Empty:
                # Timeout: if we have accumulated a long buffer, flush it
                if len(sentence_buf) > long_flush_len:
                    _speak_sentence(sentence_buf)
                    sentence_buf = ""
                continue

            if delta is None:
                # End-of-text sentinel: strip any remaining think blocks, flush
                sentence_buf = _think_block_re.sub('', sentence_buf)
                if sentence_buf.strip():
                    _speak_sentence(sentence_buf)
                break

            sentence_buf += delta

            # --- Think block filtering ---
            # Strip complete <think>...</think> blocks from buffer.
            # Works correctly even when tags span multiple deltas.
            sentence_buf = _think_block_re.sub('', sentence_buf)

            # If an incomplete <think tag is at the end, wait for more data
            # before extracting sentences (the closing tag may arrive next).
            if '<think' in sentence_buf and '</think>' not in sentence_buf:
                continue

            # Check for sentence boundaries
            while True:
                m = _SENTENCE_BOUNDARY_RE.search(sentence_buf)
                if m is None:
                    break
                end_pos = m.end()
                sentence = sentence_buf[:end_pos]
                sentence_buf = sentence_buf[end_pos:]
                # Merge short fragments into the next sentence
                if len(sentence.strip()) < min_sentence_len:
                    sentence_buf = sentence + sentence_buf
                    break
                _speak_sentence(sentence)

        # Drain any remaining items from the queue
        while True:
            try:
                text_queue.get_nowait()
            except queue.Empty:
                break

        # output_stream is closed in the finally block below

    except Exception as exc:
        logger.warning("Streaming TTS pipeline error: %s", exc)
    finally:
        # Always close the audio output stream to avoid locking the device
        if output_stream is not None:
            try:
                output_stream.stop()
                output_stream.close()
            except Exception:
                pass
        tts_done_event.set()


# ===========================================================================
# Main -- quick diagnostics
# ===========================================================================
if __name__ == "__main__":
    print("🔊 Text-to-Speech Tool Module")
    print("=" * 50)

    def _check(importer, label):
        try:
            importer()
            return True
        except ImportError:
            return False

    print("\nOpenVoice availability:")
    print(f"  OpenVoice: {'installed' if _check(_import_openvoice_modules, 'ov') else 'not installed'}")
    print(f"  ffmpeg:    {'✅ found' if _has_ffmpeg() else '❌ not found (needed for Telegram Opus)'}")
    print(f"\n  Output dir: {DEFAULT_OUTPUT_DIR}")

    config = _load_tts_config()
    provider = _get_provider(config)
    print(f"  Configured provider: {provider}")


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
from tools.registry import registry

TTS_SCHEMA = {
    "name": "text_to_speech",
    "description": "Convert text to speech audio using OpenVoice. Returns a MEDIA: path that the platform delivers as a voice message. On Telegram it plays as a voice bubble; on file output, it saves to the requested path. OpenVoice is the only production renderer.",
    "parameters": {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "The text to convert to speech. Keep under 4000 characters."
            },
            "output_path": {
                "type": "string",
                "description": "Optional custom file path to save the audio. Defaults to a timestamped path under the Hermes audio cache."
            }
        },
        "required": ["text"]
    }
}

registry.register(
    name="text_to_speech",
    toolset="tts",
    schema=TTS_SCHEMA,
    handler=lambda args, **kw: text_to_speech_tool(
        text=args.get("text", ""),
        output_path=args.get("output_path")),
    check_fn=check_tts_requirements,
    emoji="🔊",
)
