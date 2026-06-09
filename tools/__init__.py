#!/usr/bin/env python3
"""Tools package for Hermes.

The package intentionally avoids eager imports of optional backends so that
submodules can be imported in lightweight environments without pulling in
unavailable extras (Firecrawl, FAL, etc.). Import the specific tool module
directly, e.g. ``from tools.tts_tool import text_to_speech_tool``.
"""

__all__ = []
