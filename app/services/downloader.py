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

Фото и карусели Instagram:
yt-dlp не умеет скачивать посты без видео («There is no video in this post»),
но с `ignore_no_formats_error` отдаёт метаданные, где `thumbnails[-1]` —
оригинал картинки. Такие посты качаем сами по прямым CDN-ссылкам.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import aiohttp
import yt_dlp

from app.core.config import settings

log = logging.getLogger(__name__)


@dataclass
class MediaItem:
    path: str
    is_video: bool = False


@dataclass
class DownloadResult:
    path: str | None = None                          # одиночное видео (yt-dlp)
    items: list[MediaItem] = field(default_factory=list)  # фото / карусель
    title: str | None = None
    duration: int | None = None
    uploader: str | None = None       # исполнитель для аудио
    error: str | None = None          # ключ i18n, напр. "err_private"
    detail: str | None = None         # сырой текст для логов

    @property
    def ok(self) -> bool:
        return (bool(self.path) or bool(self.items)) and not self.error


# Ошибки, при которых имеет смысл попробовать следующий формат.
_RETRYABLE = (
    "requested format is not available",
    "no video formats found",
    "requested format",
    "larger than max-filesize",
    "file is larger",
)

# Пост без видео (фото / карусель Instagram) — качаем через _download_gallery.
_NO_VIDEO_MARKERS = ("no video in this post",)

# raw-текст yt-dlp -> ключ i18n
_ERROR_MAP: tuple[tuple[str, str], ...] = (
    ("video unavailable", "err_unavailable"),
    ("this video is private", "err_private"),
    ("private video", "err_private"),
    ("age", "err_age"),
    ("login required", "err_login"),
    ("only available for registered users", "err_login"),
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

    _AUDIO_BITRATE = 192  # kbps mp3

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

    #: Только метаданные: не падать на постах без видео.
    _INFO_OPTS: dict = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "socket_timeout": 20,
        "extractor_retries": 1,
        "force_ipv4": True,
        "cachedir": False,
        "ignore_no_formats_error": True,
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
                lower = (res.detail or "").lower()
                if any(k in lower for k in _NO_VIDEO_MARKERS):
                    return await self._download_gallery(url)
                if any(k in lower for k in _RETRYABLE):
                    last_error = res.error
                    continue
                return res

            if res.path:
                if Path(res.path).stat().st_size <= limit:
                    return res
                self.cleanup(res.path)
                last_error = "err_too_big"

        return DownloadResult(error=last_error or "err_too_big")

    async def download_audio(self, url: str) -> DownloadResult:
        """Извлекает звуковую дорожку в mp3 (через ffmpeg)."""
        uid = uuid.uuid4().hex[:12]
        opts = {
            **self._BASE_OPTS,
            "outtmpl": str(self._dir / f"{uid}.%(ext)s"),
            "format": "bestaudio/best",
            "http_headers": self._HTTP_HEADERS,
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": str(self._AUDIO_BITRATE),
            }],
        }
        opts.pop("merge_output_format", None)

        loop = asyncio.get_running_loop()
        try:
            info = await loop.run_in_executor(self._pool, self._sync_dl, url, opts)
        except yt_dlp.utils.DownloadError as exc:
            raw = str(exc)
            return DownloadResult(error=self._classify(raw), detail=raw)
        except Exception as exc:  # noqa: BLE001
            raw = str(exc)
            log.warning("yt-dlp audio failed: %s", raw[:200])
            return DownloadResult(error=self._classify(raw), detail=raw)

        path = self._dir / f"{uid}.mp3"
        if not path.exists():
            self.cleanup(str(path))
            return DownloadResult(error="err_unknown", detail="mp3 not found after extraction")
        if path.stat().st_size > settings.max_file_size:
            self.cleanup(str(path))
            return DownloadResult(error="err_too_big")

        return DownloadResult(
            path=str(path),
            title=info.get("title") if info else None,
            duration=info.get("duration") if info else None,
            uploader=(info.get("uploader") or info.get("channel")) if info else None,
        )

    @staticmethod
    def cleanup(path: str | None) -> None:
        if not path:
            return
        p = Path(path)
        p.unlink(missing_ok=True)
        # подчищаем возможные .part/.ytdl хвосты
        for leftover in p.parent.glob(p.stem + ".*"):
            leftover.unlink(missing_ok=True)

    def cleanup_result(self, result: DownloadResult) -> None:
        self.cleanup(result.path)
        for item in result.items:
            self.cleanup(item.path)

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)

    # ── Видео через yt-dlp ────────────────────────────────────────────────

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

    # ── Фото / карусель ───────────────────────────────────────────────────

    async def _download_gallery(self, url: str) -> DownloadResult:
        loop = asyncio.get_running_loop()
        opts = {**self._INFO_OPTS, "http_headers": self._HTTP_HEADERS}
        try:
            info = await loop.run_in_executor(self._pool, self._sync_info, url, opts)
        except yt_dlp.utils.DownloadError as exc:
            raw = str(exc)
            return DownloadResult(error=self._classify(raw), detail=raw)
        except Exception as exc:  # noqa: BLE001
            raw = str(exc)
            log.warning("gallery info failed: %s", raw[:200])
            return DownloadResult(error=self._classify(raw), detail=raw)

        if not info:
            return DownloadResult(error="err_unknown", detail="gallery: empty info")

        entries = [e for e in (info.get("entries") or [info]) if e]
        entries = entries[: settings.max_gallery_items]

        sources = [self._pick_source(e) for e in entries]
        if not any(src for src, _ in sources):
            return DownloadResult(error="err_no_format", detail="gallery: no media urls")

        uid = uuid.uuid4().hex[:12]
        timeout = aiohttp.ClientTimeout(total=settings.download_timeout, sock_read=30)
        async with aiohttp.ClientSession(
            headers=self._HTTP_HEADERS, timeout=timeout
        ) as session:
            results = await asyncio.gather(
                *(
                    self._fetch(session, src, self._dir / f"{uid}_{i}{'.mp4' if is_video else '.jpg'}")
                    for i, (src, is_video) in enumerate(sources)
                    if src
                ),
                return_exceptions=True,
            )

        items: list[MediaItem] = []
        fetched = iter(results)
        for src, is_video in sources:
            if not src:
                continue
            res = next(fetched)
            if isinstance(res, Path):
                items.append(MediaItem(str(res), is_video))
            elif isinstance(res, Exception):
                log.warning("gallery item fetch failed: %s", res)

        if not items:
            return DownloadResult(error="err_unknown", detail="gallery: all items failed")

        return DownloadResult(items=items, title=info.get("title"))

    @staticmethod
    def _sync_info(url: str, opts: dict) -> dict | None:
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)

    @staticmethod
    def _pick_source(entry: dict) -> tuple[str | None, bool]:
        """(url, is_video). Видео — прогрессивный mp4 в лимите, фото — оригинал."""
        limit = settings.max_file_size
        best: dict | None = None
        for f in entry.get("formats") or []:
            if not f.get("url") or not str(f.get("protocol", "https")).startswith("http"):
                continue
            if f.get("protocol") == "http_dash_segments":
                continue
            if f.get("vcodec") == "none" or f.get("acodec") == "none":
                continue
            size = f.get("filesize") or f.get("filesize_approx")
            if size and size > limit:
                continue
            if best is None or (f.get("height") or 0) > (best.get("height") or 0):
                best = f
        if best:
            return best["url"], True

        thumbs = entry.get("thumbnails") or []
        if thumbs:
            return thumbs[-1]["url"], False
        return None, False

    @staticmethod
    async def _fetch(session: aiohttp.ClientSession, src: str, dest: Path) -> Path:
        limit = settings.max_file_size
        async with session.get(src) as resp:
            resp.raise_for_status()
            if resp.content_length and resp.content_length > limit:
                raise ValueError(f"item too big: {resp.content_length}")
            written = 0
            with dest.open("wb") as fh:
                async for chunk in resp.content.iter_chunked(256 * 1024):
                    written += len(chunk)
                    if written > limit:
                        dest.unlink(missing_ok=True)
                        raise ValueError("item exceeded size limit")
                    fh.write(chunk)
        return dest

    # ── Прочее ────────────────────────────────────────────────────────────

    @staticmethod
    def _classify(raw: str) -> str:
        lower = raw.lower()
        for needle, key in _ERROR_MAP:
            if needle in lower:
                return key
        return "err_unknown"


downloader = VideoDownloader()
