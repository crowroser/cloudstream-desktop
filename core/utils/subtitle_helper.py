"""Subtitle format detection and conversion utilities."""
from __future__ import annotations
import re
from typing import List, Tuple, Optional


def detect_format(content: str) -> str:
    """Detect subtitle format: srt, vtt, ass, ssa, lrc."""
    stripped = content.strip()
    if stripped.startswith("WEBVTT"):
        return "vtt"
    if re.search(r"^\[Script Info\]", stripped, re.MULTILINE | re.IGNORECASE):
        if "[V4+ Styles]" in stripped or "[V4 Styles]" in stripped:
            return "ass"
        return "ssa"
    if re.search(r"^\d+\r?\n\d{2}:\d{2}:\d{2}", stripped, re.MULTILINE):
        return "srt"
    if stripped.startswith("["):
        return "lrc"
    return "unknown"


def srt_to_vtt(srt: str) -> str:
    """Convert SRT subtitle content to WebVTT."""
    vtt = "WEBVTT\n\n"
    vtt += re.sub(r"(\d{2}:\d{2}:\d{2}),(\d{3})", r"\1.\2", srt)
    return vtt


def vtt_to_srt(vtt: str) -> str:
    """Convert WebVTT to SRT."""
    content = re.sub(r"^WEBVTT.*\n\n?", "", vtt, flags=re.MULTILINE)
    content = re.sub(r"(\d{2}:\d{2}:\d{2})\.(\d{3})", r"\1,\2", content)
    lines = content.splitlines()
    result = []
    counter = 1
    i = 0
    while i < len(lines):
        line = lines[i]
        if "-->" in line:
            result.append(str(counter))
            counter += 1
            result.append(line)
        elif line.strip() and not re.match(r"^[A-Za-z-]+:", line):
            result.append(line)
        elif not line.strip() and result and result[-1]:
            result.append("")
        i += 1
    return "\n".join(result)


def parse_language_code(lang: str) -> Tuple[str, str]:
    """Return (code, display_name) from a language string."""
    LANGS = {
        "en": "English", "tr": "Turkish", "de": "German", "fr": "French",
        "es": "Spanish", "it": "Italian", "pt": "Portuguese", "ru": "Russian",
        "ja": "Japanese", "ko": "Korean", "zh": "Chinese", "ar": "Arabic",
        "nl": "Dutch", "pl": "Polish", "cs": "Czech", "hu": "Hungarian",
        "ro": "Romanian", "sv": "Swedish", "no": "Norwegian", "fi": "Finnish",
        "da": "Danish", "he": "Hebrew", "fa": "Persian", "hi": "Hindi",
        "th": "Thai", "id": "Indonesian", "vi": "Vietnamese",
    }
    code = lang[:2].lower()
    return code, LANGS.get(code, lang)


def format_time(seconds: float) -> str:
    """Format seconds as HH:MM:SS.mmm for SRT."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")
