"""
Очередь загрузок с пулом воркеров.

Оптимизации:
* кэш file_id — повторная ссылка отдаётся без скачивания (мгновенно);
* дедупликация одновременных запросов одной и той же ссылки: второй
  запрос ждёт первый и отдаёт результат из кэша, а не качает второй раз;
* задачи, слишком долго провисевшие в очереди, отбрасываются;
* корректная остановка воркеров при shutdown.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import logging
import time

from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramNetworkError,
    TelegramRetryAfter,
)
from aiogram.types import FSInputFile, InputMediaPhoto, InputMediaVideo, Message

from app.core.config import PLATFORM_EMOJIS, settings
from app.db.database import db
from app.keyboards.user import audio_kb
from app.locales import t
from app.services.downloader import DownloadResult, downloader
from app.utils.text import build_caption, safe_filename

log = logging.getLogger(__name__)

_MEDIA_GROUP_MAX = 10  # лимит Telegram на альбом

#: (media, type) — media: путь-FSInputFile при первой отправке или file_id из кэша.
MediaSpec = tuple[str | FSInputFile, str]


async def safe_edit(msg: Message, text: str) -> None:
    """Статусное сообщение — вспомогательное: его сбой не должен ронять задачу."""
    try:
        await msg.edit_text(text)
    except TelegramRetryAfter as exc:
        await asyncio.sleep(exc.retry_after)
        with contextlib.suppress(Exception):
            await msg.edit_text(text)
    except TelegramBadRequest:
        pass  # сообщение не изменилось / удалено
    except TelegramNetworkError as exc:
        log.warning("status edit failed (network): %s", exc)


def _sent_ids(messages: list[Message]) -> list[dict]:
    out: list[dict] = []
    for m in messages:
        if m.video:
            out.append({"file_id": m.video.file_id, "type": "video"})
        elif m.photo:
            out.append({"file_id": m.photo[-1].file_id, "type": "photo"})
    return out


async def send_items(
    reply_to: Message,
    items: list[MediaSpec],
    caption: str,
    link_id: int | None = None,
    lang: str = "ru",
) -> list[dict]:
    """
    Отправляет одно медиа или альбом(ы) по 10 штук.
    Под одиночным видео — кнопка «MP3» (альбомы inline-клавиатуру не поддерживают).
    Возвращает [{file_id, type}] в порядке отправки — для кэша.
    """
    if len(items) == 1:
        media, kind = items[0]
        if kind == "video":
            sent = await reply_to.reply_video(
                video=media,
                caption=caption,
                reply_markup=audio_kb(link_id, lang) if link_id is not None else None,
            )
        else:
            sent = await reply_to.reply_photo(photo=media, caption=caption)
        return _sent_ids([sent])

    out: list[dict] = []
    for start in range(0, len(items), _MEDIA_GROUP_MAX):
        group = []
        for j, (media, kind) in enumerate(items[start : start + _MEDIA_GROUP_MAX]):
            cap = caption if start == 0 and j == 0 else None
            cls = InputMediaVideo if kind == "video" else InputMediaPhoto
            group.append(cls(media=media, caption=cap))
        out.extend(_sent_ids(await reply_to.reply_media_group(media=group)))
    return out


def result_items(result: DownloadResult) -> list[MediaSpec]:
    if result.path:
        return [(FSInputFile(result.path), "video")]
    return [(FSInputFile(it.path), "video" if it.is_video else "photo") for it in result.items]


def cached_items(cached: dict) -> list[MediaSpec]:
    return [(it["file_id"], it["type"]) for it in cached["items"]]


async def send_audio(
    reply_to: Message,
    audio: str | FSInputFile,
    caption: str,
    title: str | None,
    duration: int | None,
    performer: str | None = None,
) -> str | None:
    """Отправляет mp3 (файл или file_id), возвращает file_id для кэша."""
    sent = await reply_to.reply_audio(
        audio=audio,
        caption=caption,
        title=title,
        performer=performer,
        duration=duration,
    )
    return sent.audio.file_id if sent.audio else None


@dataclasses.dataclass
class DownloadTask:
    user_id: int
    url: str
    url_key: str
    platform: str
    lang: str
    reply_to: Message
    status_msg: Message
    link_id: int | None = None
    mode: str = "video"               # "video" | "audio"
    enqueued_at: float = dataclasses.field(default_factory=time.monotonic)

    @property
    def inflight_key(self) -> str:
        return f"{self.mode}:{self.url_key}"


class QueueManager:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[DownloadTask] = asyncio.Queue(
            maxsize=settings.max_queue_size
        )
        self._user_tasks: dict[int, int] = {}
        self._inflight: dict[str, asyncio.Event] = {}
        self._workers: list[asyncio.Task] = []
        self._lock = asyncio.Lock()
        self._active = 0
        self._total_ok = 0
        self._total_err = 0
        self._total_cached = 0

    # ── Lifecycle ─────────────────────────────────────────────────────────

    async def start(self) -> None:
        self._workers = [
            asyncio.create_task(self._worker(i), name=f"dl-worker-{i}")
            for i in range(settings.max_workers)
        ]
        log.info("Queue started: %d workers", settings.max_workers)

    async def stop(self) -> None:
        for w in self._workers:
            w.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        downloader.shutdown()

    # ── API ───────────────────────────────────────────────────────────────

    async def enqueue(self, task: DownloadTask) -> tuple[bool, str | int]:
        async with self._lock:
            if self._user_tasks.get(task.user_id, 0) >= settings.max_user_tasks:
                return False, t(task.lang, "error_user_limit", limit=settings.max_user_tasks)
            try:
                self._queue.put_nowait(task)
            except asyncio.QueueFull:
                return False, t(task.lang, "error_queue_full")
            self._user_tasks[task.user_id] = self._user_tasks.get(task.user_id, 0) + 1
            return True, self._queue.qsize()

    @property
    def stats(self) -> dict:
        return {
            "queue_size": self._queue.qsize(),
            "active": self._active,
            "total_ok": self._total_ok,
            "total_err": self._total_err,
            "total_cached": self._total_cached,
            "max_workers": settings.max_workers,
        }

    # ── Воркеры ───────────────────────────────────────────────────────────

    async def _worker(self, worker_id: int) -> None:
        while True:
            task = await self._queue.get()
            async with self._lock:
                self._active += 1
            try:
                await self._process(task)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                self._total_err += 1
                log.exception("worker %d: unhandled error: %s", worker_id, exc)
            finally:
                async with self._lock:
                    self._active -= 1
                    left = self._user_tasks.get(task.user_id, 1) - 1
                    if left > 0:
                        self._user_tasks[task.user_id] = left
                    else:
                        self._user_tasks.pop(task.user_id, None)
                self._queue.task_done()

    async def _process(self, task: DownloadTask) -> None:
        # Слишком долго ждал в очереди — пользователю это уже не нужно.
        if time.monotonic() - task.enqueued_at > settings.max_wait_time:
            await safe_edit(task.status_msg, t(task.lang, "error_wait_timeout"))
            self._total_err += 1
            return

        # Пока задача ждала, ссылку мог скачать кто-то другой.
        if await self._try_send_cached(task):
            return

        # Ту же ссылку уже качает другой воркер — дожидаемся его результата.
        event = self._inflight.get(task.inflight_key)
        if event is not None:
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(event.wait(), timeout=settings.download_timeout)
            if await self._try_send_cached(task):
                return

        own_event = asyncio.Event()
        self._inflight[task.inflight_key] = own_event
        try:
            if task.mode == "audio":
                await self._extract_and_send_audio(task)
            else:
                await self._download_and_send(task)
        finally:
            self._inflight.pop(task.inflight_key, None)
            own_event.set()

    async def _download_and_send(self, task: DownloadTask) -> None:
        emoji = PLATFORM_EMOJIS.get(task.platform, "🌐")
        await safe_edit(
            task.status_msg,
            t(task.lang, "downloading", emoji=emoji, platform=task.platform),
        )

        try:
            result: DownloadResult = await asyncio.wait_for(
                downloader.download(task.url), timeout=settings.download_timeout
            )
        except asyncio.TimeoutError:
            await safe_edit(task.status_msg, t(task.lang, "error_timeout"))
            self._total_err += 1
            return

        if not result.ok:
            if result.detail:
                log.info("download failed [%s]: %s", result.error, result.detail[:200])
            await safe_edit(task.status_msg, t(task.lang, result.error or "err_unknown"))
            self._total_err += 1
            return

        try:
            await safe_edit(task.status_msg, t(task.lang, "sending"))
            caption = build_caption(result.title, result.duration, task.platform, emoji)
            sent_ids = await send_items(
                task.reply_to, result_items(result), caption, task.link_id, task.lang
            )
            with contextlib.suppress(Exception):
                await task.status_msg.delete()
            self._total_ok += 1

            if settings.file_cache_enabled and sent_ids:
                await db.save_cached_video(
                    task.url_key, sent_ids, result.title, result.duration
                )
        except TelegramBadRequest:
            await safe_edit(task.status_msg, t(task.lang, "error_send_failed"))
            self._total_err += 1
        except TelegramNetworkError as exc:
            log.warning("send failed (network) for %s: %s", task.url_key, exc)
            await safe_edit(task.status_msg, t(task.lang, "err_network"))
            self._total_err += 1
        finally:
            downloader.cleanup_result(result)

    async def _extract_and_send_audio(self, task: DownloadTask) -> None:
        emoji = PLATFORM_EMOJIS.get(task.platform, "🌐")
        await safe_edit(task.status_msg, t(task.lang, "extracting_audio"))

        try:
            result: DownloadResult = await asyncio.wait_for(
                downloader.download_audio(task.url), timeout=settings.download_timeout
            )
        except asyncio.TimeoutError:
            await safe_edit(task.status_msg, t(task.lang, "error_timeout"))
            self._total_err += 1
            return

        if not result.ok:
            if result.detail:
                log.info("audio failed [%s]: %s", result.error, result.detail[:200])
            key = result.error or "err_unknown"
            if "no video in this post" in (result.detail or "").lower():
                key = "audio_photo_only"  # фото-пост: звука там нет
            await safe_edit(task.status_msg, t(task.lang, key))
            self._total_err += 1
            return

        try:
            await safe_edit(task.status_msg, t(task.lang, "sending"))
            file_id = await send_audio(
                task.reply_to,
                FSInputFile(result.path, filename=safe_filename(result.title, "mp3")),
                build_caption(result.title, result.duration, task.platform, emoji),
                result.title,
                result.duration,
                result.uploader,
            )
            with contextlib.suppress(Exception):
                await task.status_msg.delete()
            self._total_ok += 1
            if settings.file_cache_enabled and file_id:
                await db.save_cached_audio(task.url_key, file_id, result.title, result.duration)
        except TelegramBadRequest:
            await safe_edit(task.status_msg, t(task.lang, "error_send_failed"))
            self._total_err += 1
        except TelegramNetworkError as exc:
            log.warning("send failed (network) for %s: %s", task.url_key, exc)
            await safe_edit(task.status_msg, t(task.lang, "err_network"))
            self._total_err += 1
        finally:
            downloader.cleanup_result(result)

    # ── Кэш file_id ───────────────────────────────────────────────────────

    async def _try_send_cached(self, task: DownloadTask) -> bool:
        if not settings.file_cache_enabled:
            return False
        if task.mode == "audio":
            cached = await db.get_cached_audio(task.url_key)
        else:
            cached = await db.get_cached_video(task.url_key)
        if not cached:
            return False
        emoji = PLATFORM_EMOJIS.get(task.platform, "🌐")
        caption = build_caption(cached["title"], cached["duration"], task.platform, emoji)
        try:
            if task.mode == "audio":
                await send_audio(
                    task.reply_to, cached["file_id"], caption, cached["title"], cached["duration"]
                )
            else:
                await send_items(
                    task.reply_to, cached_items(cached), caption, task.link_id, task.lang
                )
        except TelegramBadRequest as exc:
            log.info("stale %s file_id for %s: %s", task.mode, task.url_key, exc)
            if task.mode == "audio":
                await db.drop_cached_audio(task.url_key)
            else:
                await db.drop_cached_video(task.url_key)
            return False
        with contextlib.suppress(Exception):
            await task.status_msg.delete()
        self._total_cached += 1
        self._total_ok += 1
        return True


queue_manager = QueueManager()
