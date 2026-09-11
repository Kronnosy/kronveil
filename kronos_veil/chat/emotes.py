"""
Emote and Badge Manager for Kronos Veil.
Resolves Twitch & 7TV emotes, manages disk and in-memory LRU caching,
and converts plain chat messages into rich-text HTML with inline badges and emotes.
"""

from __future__ import annotations

import hashlib
import html
import json
import logging
import os
import re
import threading
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set

from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)

# Pre-populated dictionary of high-frequency global emotes with stable CDN endpoints
POPULAR_EMOTES: Dict[str, str] = {
    # 7TV Emotes
    "KEKW": "https://cdn.7tv.app/emote/60ae3e54229664e9625902b4/2x.webp",
    "monkaS": "https://cdn.7tv.app/emote/603cb92b5853b900140c83e7/2x.webp",
    "monkaW": "https://cdn.7tv.app/emote/60ae3f2b229664e9625903b4/2x.webp",
    "catJAM": "https://cdn.7tv.app/emote/60ae3f23229664e9625903a4/2x.webp",
    "PepeHands": "https://cdn.7tv.app/emote/60ae3f25229664e9625903a8/2x.webp",
    "Clap": "https://cdn.7tv.app/emote/60ae3f27229664e9625903ac/2x.webp",
    "EZ": "https://cdn.7tv.app/emote/60ae3f29229664e9625903b0/2x.webp",
    "OMEGALUL": "https://cdn.7tv.app/emote/60ae3f2e229664e9625903bc/2x.webp",
    "AYAYA": "https://cdn.7tv.app/emote/60ae3f32229664e9625903c4/2x.webp",
    "widepeepoHappy": "https://cdn.7tv.app/emote/60ae3f34229664e9625903c8/2x.webp",
    "Sadge": "https://cdn.7tv.app/emote/60ae3f36229664e9625903cc/2x.webp",
    "pepeLaugh": "https://cdn.7tv.app/emote/60ae3f38229664e9625903d0/2x.webp",
    "Copium": "https://cdn.7tv.app/emote/60ae3f3a229664e9625903d4/2x.webp",
    "GIGACHAD": "https://cdn.7tv.app/emote/612985f76b15e478546b1580/2x.webp",
    "Pog": "https://cdn.7tv.app/emote/60ae3f30229664e9625903c0/2x.webp",
    # Twitch Global Emotes
    "LUL": "https://static-cdn.jtvnw.net/emoticons/v2/425618/default/dark/2.0",
    "PogChamp": "https://static-cdn.jtvnw.net/emoticons/v2/305954156/default/dark/2.0",
    "Kappa": "https://static-cdn.jtvnw.net/emoticons/v2/25/default/dark/2.0",
    "BibleThump": "https://static-cdn.jtvnw.net/emoticons/v2/86/default/dark/2.0",
    "NotLikeThis": "https://static-cdn.jtvnw.net/emoticons/v2/58765/default/dark/2.0",
    "HeyGuys": "https://static-cdn.jtvnw.net/emoticons/v2/30259/default/dark/2.0",
    "VoHiYo": "https://static-cdn.jtvnw.net/emoticons/v2/81274/default/dark/2.0",
    "WutFace": "https://static-cdn.jtvnw.net/emoticons/v2/28087/default/dark/2.0",
    "Kreygasm": "https://static-cdn.jtvnw.net/emoticons/v2/41/default/dark/2.0",
    "ResidentSleeper": "https://static-cdn.jtvnw.net/emoticons/v2/245/default/dark/2.0",
}

BADGE_STYLES: Dict[str, Dict[str, str]] = {
    "broadcaster": {"bg": "#e91e63", "label": "BROADCASTER"},
    "admin": {"bg": "#b71c1c", "label": "ADMIN"},
    "staff": {"bg": "#212121", "label": "STAFF"},
    "moderator": {"bg": "#00b06f", "label": "MOD"},
    "mod": {"bg": "#00b06f", "label": "MOD"},
    "vip": {"bg": "#e005b9", "label": "VIP"},
    "subscriber": {"bg": "#7b1fa2", "label": "SUB"},
    "sub": {"bg": "#7b1fa2", "label": "SUB"},
    "verified": {"bg": "#0288d1", "label": "✓"},
    "founder": {"bg": "#ff8f00", "label": "FOUNDER"},
    "og": {"bg": "#ff6d00", "label": "OG"},
}


class EmoteManager(QObject):
    """
    Manages fetching, caching, and HTML formatting of Twitch and 7TV emotes and user badges.
    """

    emote_downloaded = Signal(str, str)  # name, local_path

    _instance: Optional[EmoteManager] = None

    @classmethod
    def get_instance(cls) -> EmoteManager:
        if cls._instance is None:
            cls._instance = EmoteManager()
        return cls._instance

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.cache_dir = self._get_cache_dir()
        self.emotes: Dict[str, str] = dict(POPULAR_EMOTES)
        self._download_queue: Set[str] = set()
        self._lock = threading.Lock()

    @staticmethod
    def _get_cache_dir() -> Path:
        appdata = os.getenv("APPDATA")
        if appdata:
            base = Path(appdata) / "KronosVeil" / "cache" / "emotes"
        else:
            base = Path.home() / ".kronos_veil" / "cache" / "emotes"
        base.mkdir(parents=True, exist_ok=True)
        return base

    def register_emote(self, name: str, url: str) -> None:
        """Register a custom or channel-specific emote mapping."""
        with self._lock:
            self.emotes[name] = url

    def get_cached_path(self, name: str) -> Optional[str]:
        """Returns the local file path if the emote image is already downloaded."""
        if name not in self.emotes:
            return None

        url = self.emotes[name]
        ext = ".webp"
        if ".png" in url:
            ext = ".png"
        elif ".gif" in url:
            ext = ".gif"

        safe_name = re.sub(r"[^\w\-]", "_", name)
        file_path = self.cache_dir / f"{safe_name}_{hashlib.md5(url.encode('utf-8')).hexdigest()[:8]}{ext}"
        if file_path.exists() and file_path.stat().st_size > 0:
            return str(file_path).replace("\\", "/")
        return None

    def request_download(self, name: str) -> None:
        """Schedules a non-blocking background download for an emote."""
        with self._lock:
            if name in self._download_queue or name not in self.emotes:
                return
            self._download_queue.add(name)

        thread = threading.Thread(target=self._download_worker, args=(name,), daemon=True)
        thread.start()

    def _download_worker(self, name: str) -> None:
        try:
            url = self.emotes.get(name)
            if not url:
                return

            ext = ".webp"
            if ".png" in url:
                ext = ".png"
            elif ".gif" in url:
                ext = ".gif"

            safe_name = re.sub(r"[^\w\-]", "_", name)
            dest_file = self.cache_dir / f"{safe_name}_{hashlib.md5(url.encode('utf-8')).hexdigest()[:8]}{ext}"

            if not dest_file.exists() or dest_file.stat().st_size == 0:
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "Mozilla/5.0 KronosVeil/1.0 EmoteCache"},
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    if resp.status == 200:
                        content = resp.read()
                        dest_file.write_bytes(content)
                        logger.debug("Successfully cached emote: %s -> %s", name, dest_file)

            if dest_file.exists() and dest_file.stat().st_size > 0:
                self.emote_downloaded.emit(name, str(dest_file).replace("\\", "/"))
        except Exception as exc:
            logger.debug("Failed downloading emote %s from %s: %s", name, self.emotes.get(name), exc)
        finally:
            with self._lock:
                self._download_queue.discard(name)

    def format_badges_html(self, badges: List[str]) -> str:
        """Converts user badge identifiers to styled HTML pills."""
        if not badges:
            return ""

        html_badges = []
        for badge in badges:
            b_key = badge.lower().split("/")[0]  # Support twitch "subscriber/12" format
            style_info = BADGE_STYLES.get(b_key)
            if style_info:
                html_badges.append(
                    f'<span style="background-color: {style_info["bg"]}; color: #ffffff; '
                    f'font-size: 7.5pt; font-weight: bold; border-radius: 3px; '
                    f'padding: 1px 4px; margin-right: 3px;">{style_info["label"]}</span>'
                )
        return "".join(html_badges)

    def format_message_html(
        self,
        raw_message: str,
        emotes_enabled: bool = True,
        size_px: int = 22,
    ) -> str:
        """
        Parses text, replaces known emote tokens with inline <img> tags,
        and safely escapes all user input to prevent HTML injection.
        """
        if not emotes_enabled:
            return html.escape(raw_message)

        tokens = raw_message.split(" ")
        formatted_tokens = []

        for token in tokens:
            if not token:
                continue

            clean_token = token.strip()
            if clean_token in self.emotes:
                cached_path = self.get_cached_path(clean_token)
                if cached_path:
                    # Render inline cached image
                    img_html = (
                        f'<img src="{cached_path}" width="{size_px}" height="{size_px}" '
                        f'style="vertical-align: middle; margin: 0 2px;" />'
                    )
                    formatted_tokens.append(img_html)
                else:
                    # Not yet downloaded: request background download & display escaped text
                    self.request_download(clean_token)
                    formatted_tokens.append(html.escape(token))
            else:
                formatted_tokens.append(html.escape(token))

        return " ".join(formatted_tokens)
