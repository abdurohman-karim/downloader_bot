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

from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.types import FSInputFile, Message

from app.core.config import PLATFORM_EMOJIS, settings
from app.db.database import db
from app.locales import t
from app.services.downloader import DownloadResult, downloader
from app.utils.text import build_caption

log = logging.getLogger(__name__)


async def safe_edit(msg: Message, text: str) -> None:
    try:
        await msg.edit_text(text)
    except TelegramRetryAfter as exc:
        await asyncio.sleep(exc.retry_after)
        with contextlib.suppress(Exception):
            await msg.edit_text(text)
    except TelegramBadRequest:
        pass  # сообщение не изменилось / удалено


@dataclasses.dataclass
class DownloadTask:
    user_id: int
    url: str
    url_key: str
    platform: str
    lang: str
    reply_to: Message
    status_msg: Message
    enqueued_at: float = dataclasses.field(default_factory=time.monotonic)


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
        event = self._inflight.get(task.url_key)
        if event is not None:
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(event.wait(), timeout=settings.download_timeout)
            if await self._try_send_cached(task):
                return

        own_event = asyncio.Event()
        self._inflight[task.url_key] = own_event
        try:
            await self._download_and_send(task)
        finally:
            self._inflight.pop(task.url_key, None)
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
            sent = await task.reply_to.reply_video(
                video=FSInputFile(result.path),
                caption=build_caption(result.title, result.duration, task.platform, emoji),
            )
            with contextlib.suppress(Exception):
                await task.status_msg.delete()
            self._total_ok += 1

            if settings.file_cache_enabled and sent.video:
                await db.save_cached_video(
                    task.url_key, sent.video.file_id, result.title, result.duration
                )
        except TelegramBadRequest:
            await safe_edit(task.status_msg, t(task.lang, "error_send_failed"))
            self._total_err += 1
        finally:
            downloader.cleanup(result.path)

    # ── Кэш file_id ───────────────────────────────────────────────────────

    async def _try_send_cached(self, task: DownloadTask) -> bool:
        if not settings.file_cache_enabled:
            return False
        cached = await db.get_cached_video(task.url_key)
        if not cached:
            return False
        emoji = PLATFORM_EMOJIS.get(task.platform, "🌐")
        try:
            await task.reply_to.reply_video(
                video=cached["file_id"],
                caption=build_caption(
                    cached["title"], cached["duration"], task.platform, emoji
                ),
            )
        except TelegramBadRequest as exc:
            log.info("stale file_id for %s: %s", task.url_key, exc)
            await db.drop_cached_video(task.url_key)
            return False
        with contextlib.suppress(Exception):
            await task.status_msg.delete()
        self._total_cached += 1
        self._total_ok += 1
        return True


queue_manager = QueueManager()
