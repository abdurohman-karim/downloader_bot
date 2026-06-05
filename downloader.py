"""
yt-dlp download wrapper.

Strategy (auto mode): try formats from best (720p) down to worst.
Stop at the first file that fits within Telegram's 50 MB limit.
Quality mode (YouTube): download the exact requested quality directly.
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

    # Auto quality chain — ordered best → worst (TikTok / Instagram).
    # Both portrait and landscape orientations are covered.
    _QUALITY_CHAIN: tuple[str, ...] = (
        "bestvideo[width<=1280][height<=720]+bestaudio"
        "/bestvideo[width<=720][height<=1280]+bestaudio"
        "/best[width<=1280][height<=720]/best[width<=720][height<=1280]",
        "bestvideo[width<=854][height<=480]+bestaudio"
        "/bestvideo[width<=480][height<=854]+bestaudio"
        "/best[width<=854][height<=480]/best[width<=480][height<=854]",
        "bestvideo[width<=640][height<=360]+bestaudio"
        "/bestvideo[width<=360][height<=640]+bestaudio"
        "/best[width<=640][height<=360]/best[width<=360][height<=640]",
        "best[ext=mp4]/best",
        "worst",
    )

    # Errors that mean the format wasn't available — safe to retry next format.
    _FORMAT_ERRORS: tuple[str, ...] = (
        "requested format is not available",
        "no video formats found",
        "requested format",
        "не удалось найти подходящий формат",  # already translated by _friendly()
    )

    _HTTP_HEADERS: dict[str, str] = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }

    # Base yt-dlp options shared by every request
    _BASE_OPTS: dict = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 30,
        "retries": 3,
        "fragment_retries": 3,
        "force_ipv4": True,  # avoids [Errno 101] on servers without IPv6
    }

    def __init__(self) -> None:
        self._dir = Path(DOWNLOAD_DIR)
        self._dir.mkdir(parents=True, exist_ok=True)

    # ── Public ────────────────────────────────────────────────────────────────

    async def download(self, url: str) -> DownloadResult:
        last_error: Optional[str] = None
        for fmt in self._QUALITY_CHAIN:
            res = await self._attempt(url, fmt)

            if res.error:
                if any(k in res.error.lower() for k in self._FORMAT_ERRORS):
                    last_error = res.error
                    continue
                return res

            if res.path:
                if Path(res.path).stat().st_size <= MAX_FILE_SIZE:
                    return res
                self.cleanup(res.path)

        if last_error:
            return DownloadResult(error="Не удалось найти подходящий формат видео.")
        return DownloadResult(error="Видео слишком большое для Telegram (лимит 50 МБ).")

    @staticmethod
    def cleanup(path: str) -> None:
        Path(path).unlink(missing_ok=True)

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _attempt(self, url: str, fmt: str) -> DownloadResult:
        uid = uuid.uuid4().hex[:12]
        tmpl = str(self._dir / f"{uid}.%(ext)s")

        opts: dict = {
            **self._BASE_OPTS,
            "outtmpl": tmpl,
            "format": fmt,
            "http_headers": self._HTTP_HEADERS,
        }

        opts["merge_output_format"] = "mp4"

        try:
            info = await asyncio.to_thread(self._sync_dl, url, opts)
        except yt_dlp.utils.DownloadError as exc:
            return DownloadResult(error=self._friendly(str(exc)))
        except Exception as exc:  # noqa: BLE001
            return DownloadResult(error=f"Ошибка загрузки: {str(exc)[:120]}")

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
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url)

    @staticmethod
    def _friendly(raw: str) -> str:
        lower = raw.lower()
        checks = {
            "video unavailable":                 "Видео недоступно.",
            "private video":                     "Видео приватное.",
            "this video is private":             "Видео приватное.",
            "age":                               "Видео с возрастным ограничением.",
            "login required":                    "Требуется авторизация (приватный контент).",
            "copyright":                         "Видео заблокировано по авторским правам.",
            "not a valid url":                   "Неверная ссылка.",
            "unsupported url":                   "Ссылка не поддерживается.",
            "no video formats":                  "Не удалось найти подходящий формат видео.",
            "requested format is not available": "Не удалось найти подходящий формат видео.",
            "network is unreachable":            "Ошибка сети. Попробуй позже.",
            "errno 101":                         "Ошибка сети. Попробуй позже.",
            "giving up after":                   "Ошибка сети. Попробуй позже.",
        }
        for key, msg in checks.items():
            if key in lower:
                return msg
        return f"Не удалось скачать: {raw[:120]}"
