"""
Обёртка над yt-dlp.

Оптимизации:
* сначала пробуем один селектор с фильтром по размеру — в большинстве случаев
  хватает одной попытки вместо перебора всей цепочки качеств;
* `max_filesize` обрывает скачивание слишком больших файлов на лету,
  не дожидаясь конца;
* собственный ThreadPoolExecutor на MAX_WORKERS — не «съедаем» дефолтный
  executor цикла событий (там всего min(32, cpu+4) потоков);
* ошибки возвращаются кодом, а текст подставляет i18n.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import yt_dlp

from app.core.config import settings

log = logging.getLogger(__name__)


@dataclass
class DownloadResult:
    path: str | None = None
    title: str | None = None
    duration: int | None = None
    error: str | None = None          # ключ i18n, напр. "err_private"
    detail: str | None = None         # сырой текст для логов

    @property
    def ok(self) -> bool:
        return bool(self.path) and not self.error


# Ошибки, при которых имеет смысл попробовать следующий формат.
_RETRYABLE = (
    "requested format is not available",
    "no video formats found",
    "requested format",
    "larger than max-filesize",
    "file is larger",
)

# raw-текст yt-dlp -> ключ i18n
_ERROR_MAP: tuple[tuple[str, str], ...] = (
    ("video unavailable", "err_unavailable"),
    ("this video is private", "err_private"),
    ("private video", "err_private"),
    ("age", "err_age"),
    ("login required", "err_login"),
    ("rate-limit", "err_network"),
    ("copyright", "err_copyright"),
    ("not a valid url", "err_bad_url"),
    ("unsupported url", "err_unsupported"),
    ("no video formats", "err_no_format"),
    ("requested format is not available", "err_no_format"),
    ("network is unreachable", "err_network"),
    ("errno 101", "err_network"),
    ("timed out", "err_network"),
    ("giving up after", "err_network"),
)


class VideoDownloader:
    #: Быстрый путь — один селектор, отсекающий заведомо большие форматы.
    _PRIMARY_FORMAT = (
        "bv*[filesize<{limit}][height<=1080]+ba/"
        "b[filesize<{limit}]/"
        "bv*[filesize_approx<{limit}][height<=1080]+ba/"
        "b[filesize_approx<{limit}]"
    )

    #: Резервная цепочка: 720p → 480p → 360p → худшее.
    _FALLBACK_CHAIN: tuple[str, ...] = (
        "bv*[width<=1280][height<=720]+ba/b[width<=1280][height<=720]"
        "/bv*[width<=720][height<=1280]+ba/b[width<=720][height<=1280]",
        "bv*[width<=854][height<=480]+ba/b[width<=854][height<=480]"
        "/bv*[width<=480][height<=854]+ba/b[width<=480][height<=854]",
        "b[ext=mp4]/b",
        "worst",
    )

    _HTTP_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }

    _BASE_OPTS: dict = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "noprogress": True,
        "socket_timeout": 20,
        "retries": 2,
        "fragment_retries": 3,
        "extractor_retries": 1,
        "concurrent_fragment_downloads": 4,
        "force_ipv4": True,          # обходит [Errno 101] на серверах без IPv6
        "merge_output_format": "mp4",
        "max_filesize": settings.max_file_size,
        "cachedir": False,
    }

    def __init__(self) -> None:
        self._dir = Path(settings.download_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._pool = ThreadPoolExecutor(
            max_workers=settings.max_workers, thread_name_prefix="ytdlp"
        )

    # ── Публичный API ─────────────────────────────────────────────────────

    async def download(self, url: str) -> DownloadResult:
        limit = settings.max_file_size
        formats = (
            self._PRIMARY_FORMAT.format(limit=limit),
            *self._FALLBACK_CHAIN,
        )

        last_error: str | None = None
        for fmt in formats:
            res = await self._attempt(url, fmt)

            if res.error:
                if res.detail and any(k in res.detail.lower() for k in _RETRYABLE):
                    last_error = res.error
                    continue
                return res

            if res.path:
                if Path(res.path).stat().st_size <= limit:
                    return res
                self.cleanup(res.path)
                last_error = "err_too_big"

        return DownloadResult(error=last_error or "err_too_big")

    @staticmethod
    def cleanup(path: str | None) -> None:
        if not path:
            return
        p = Path(path)
        p.unlink(missing_ok=True)
        # подчищаем возможные .part/.ytdl хвосты
        for leftover in p.parent.glob(p.stem + ".*"):
            leftover.unlink(missing_ok=True)

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)

    # ── Внутреннее ────────────────────────────────────────────────────────

    async def _attempt(self, url: str, fmt: str) -> DownloadResult:
        uid = uuid.uuid4().hex[:12]
        opts = {
            **self._BASE_OPTS,
            "outtmpl": str(self._dir / f"{uid}.%(ext)s"),
            "format": fmt,
            "http_headers": self._HTTP_HEADERS,
        }

        loop = asyncio.get_running_loop()
        try:
            info = await loop.run_in_executor(self._pool, self._sync_dl, url, opts)
        except yt_dlp.utils.DownloadError as exc:
            raw = str(exc)
            return DownloadResult(error=self._classify(raw), detail=raw)
        except Exception as exc:  # noqa: BLE001
            raw = str(exc)
            log.warning("yt-dlp failed (%s): %s", fmt[:24], raw[:200])
            return DownloadResult(error=self._classify(raw), detail=raw)

        for file in self._dir.glob(f"{uid}.*"):
            if file.suffix in (".part", ".ytdl"):
                continue
            return DownloadResult(
                path=str(file),
                title=info.get("title") if info else None,
                duration=info.get("duration") if info else None,
            )

        return DownloadResult(error="err_unknown", detail="file not found after download")

    @staticmethod
    def _sync_dl(url: str, opts: dict) -> dict | None:
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url)

    @staticmethod
    def _classify(raw: str) -> str:
        lower = raw.lower()
        for needle, key in _ERROR_MAP:
            if needle in lower:
                return key
        return "err_unknown"


downloader = VideoDownloader()
