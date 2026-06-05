"""
yt-dlp download wrapper.

Strategy: try formats from best (720p) down to worst.
Stop at the first file that fits within Telegram's 50 MB limit.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yt_dlp

from config import DOWNLOAD_DIR, MAX_FILE_SIZE


@dataclass
class DownloadResult:
    path: Optional[str] = None
    title: Optional[str] = None
    duration: Optional[int] = None
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return bool(self.path) and not self.error


class VideoDownloader:
    """
    Async-friendly yt-dlp wrapper.
    Heavy I/O runs in a thread pool via asyncio.to_thread (Python 3.9+).
    """

    # Ordered best → worst. Each string is a yt-dlp format selector.
    _QUALITY_CHAIN: tuple[str, ...] = (
        # 720p — best quality that still fits most uploads
        "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]"
        "/bestvideo[height<=720]+bestaudio/best[height<=720][ext=mp4]/best[height<=720]",
        # 480p fallback
        "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]"
        "/bestvideo[height<=480]+bestaudio/best[height<=480][ext=mp4]/best[height<=480]",
        # 360p fallback
        "bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]"
        "/bestvideo[height<=360]+bestaudio/best[height<=360][ext=mp4]/best[height<=360]",
        # Last resort
        "worst",
    )

    _HTTP_HEADERS: dict[str, str] = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }

    def __init__(self) -> None:
        self._dir = Path(DOWNLOAD_DIR)
        self._dir.mkdir(parents=True, exist_ok=True)

    # ── Public ────────────────────────────────────────────────────────────────

    async def download(self, url: str) -> DownloadResult:
        """
        Try quality levels from best to worst.
        Returns the first result within the 50 MB limit,
        or an error if all levels fail or remain too large.
        """
        for fmt in self._QUALITY_CHAIN:
            res = await self._attempt(url, fmt)

            if res.error:
                return res  # yt-dlp / network error — no point retrying

            if res.path:
                file_size = Path(res.path).stat().st_size
                if file_size <= MAX_FILE_SIZE:
                    return res
                # File is too big → clean up, try lower quality
                self.cleanup(res.path)

        return DownloadResult(
            error="Видео слишком большое для Telegram (лимит 50 МБ)."
        )

    @staticmethod
    def cleanup(path: str) -> None:
        """Delete a downloaded file safely."""
        Path(path).unlink(missing_ok=True)

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _attempt(self, url: str, fmt: str) -> DownloadResult:
        uid = uuid.uuid4().hex[:12]
        tmpl = str(self._dir / f"{uid}.%(ext)s")

        opts: dict = {
            "outtmpl": tmpl,
            "format": fmt,
            "merge_output_format": "mp4",
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,      # never download full playlists
            "socket_timeout": 30,
            "retries": 3,
            "fragment_retries": 3,
            "http_headers": self._HTTP_HEADERS,
        }

        try:
            info = await asyncio.to_thread(self._sync_dl, url, opts)
        except yt_dlp.utils.DownloadError as exc:
            return DownloadResult(error=self._friendly(str(exc)))
        except Exception as exc:  # noqa: BLE001
            return DownloadResult(error=f"Ошибка загрузки: {str(exc)[:120]}")

        # Locate the file yt-dlp wrote
        for f in self._dir.iterdir():
            if f.stem == uid:
                return DownloadResult(
                    path=str(f),
                    title=info.get("title"),
                    duration=info.get("duration"),
                )

        return DownloadResult(error="Файл не найден после скачивания.")

    @staticmethod
    def _sync_dl(url: str, opts: dict) -> dict:
        """Blocking download — called from thread pool."""
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url)  # download=True by default

    @staticmethod
    def _friendly(raw: str) -> str:
        """Map yt-dlp error messages to human-readable Russian text."""
        lower = raw.lower()
        checks = {
            "video unavailable":       "Видео недоступно.",
            "private video":           "Видео приватное.",
            "this video is private":   "Видео приватное.",
            "age":                     "Видео с возрастным ограничением.",
            "login required":          "Требуется авторизация (приватный контент).",
            "copyright":               "Видео заблокировано по авторским правам.",
            "not a valid url":         "Неверная ссылка.",
            "unsupported url":         "Ссылка не поддерживается.",
            "no video formats":        "Не удалось найти подходящий формат видео.",
        }
        for key, msg in checks.items():
            if key in lower:
                return msg
        return f"Не удалось скачать: {raw[:120]}"
