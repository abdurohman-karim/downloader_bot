from __future__ import annotations

import asyncio
import dataclasses
import logging
import time
from collections import defaultdict
from typing import Optional

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import FSInputFile, Message

from config import (
    DOWNLOAD_TIMEOUT,
    MAX_QUEUE_SIZE,
    MAX_USER_TASKS,
    MAX_WAIT_TIME,
    MAX_WORKERS,
    PLATFORM_EMOJIS,
)
from downloader import DownloadResult, VideoDownloader

log = logging.getLogger(__name__)

downloader = VideoDownloader()


# ── Shared helpers ────────────────────────────────────────────────────────────

async def safe_edit(msg: Message, text: str) -> None:
    try:
        await msg.edit_text(text, parse_mode="HTML")
    except TelegramBadRequest:
        pass


def format_duration(secs: Optional[int]) -> str:
    if not secs:
        return ""
    m, s = divmod(int(secs), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def build_caption(result: DownloadResult, platform: str) -> str:
    emoji = PLATFORM_EMOJIS.get(platform, "🌐")
    lines: list[str] = []
    if result.title:
        lines.append(f"<b>{result.title[:100]}</b>")
    dur = format_duration(result.duration)
    if dur:
        lines.append(f"⏱ {dur}")
    lines.append(f"{emoji} {platform}")
    return "\n".join(lines)


# ── Task ──────────────────────────────────────────────────────────────────────

@dataclasses.dataclass
class DownloadTask:
    user_id: int
    url: str
    platform: str
    reply_to: Message
    status_msg: Message
    enqueued_at: float = dataclasses.field(default_factory=time.monotonic)


# ── Queue manager ─────────────────────────────────────────────────────────────

class QueueManager:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[DownloadTask] = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)
        self._user_task_count: dict[int, int] = defaultdict(int)
        self._active: int = 0
        self._total_ok: int = 0
        self._total_err: int = 0
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        for i in range(MAX_WORKERS):
            asyncio.create_task(self._worker(i), name=f"worker-{i}")

    async def enqueue(self, task: DownloadTask) -> tuple[bool, str | int]:
        async with self._lock:
            if self._user_task_count[task.user_id] >= MAX_USER_TASKS:
                return False, (
                    f"⚠️ У тебя уже {MAX_USER_TASKS} задачи в очереди. "
                    "Дождись их выполнения."
                )
            try:
                self._queue.put_nowait(task)
                self._user_task_count[task.user_id] += 1
                return True, self._queue.qsize()
            except asyncio.QueueFull:
                return False, "⚠️ Очередь переполнена. Попробуй через минуту."

    @property
    def stats(self) -> dict:
        return {
            "queue_size": self._queue.qsize(),
            "active": self._active,
            "total_ok": self._total_ok,
            "total_err": self._total_err,
            "max_workers": MAX_WORKERS,
        }

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _worker(self, worker_id: int) -> None:
        while True:
            task = await self._queue.get()
            async with self._lock:
                self._active += 1
            try:
                await self._process(task)
            except Exception as exc:  # noqa: BLE001
                log.exception("Worker %d unhandled error: %s", worker_id, exc)
                self._total_err += 1
            finally:
                async with self._lock:
                    self._active -= 1
                    self._user_task_count[task.user_id] -= 1
                    if self._user_task_count[task.user_id] <= 0:
                        del self._user_task_count[task.user_id]
                self._queue.task_done()

    async def _process(self, task: DownloadTask) -> None:
        # Drop requests that waited too long
        if time.monotonic() - task.enqueued_at > MAX_WAIT_TIME:
            await safe_edit(task.status_msg, "❌ Запрос отменён — слишком долго ждал в очереди.")
            self._total_err += 1
            return

        emoji = PLATFORM_EMOJIS.get(task.platform, "🌐")
        await safe_edit(task.status_msg, f"{emoji} Загружаю с {task.platform}…")

        try:
            result = await asyncio.wait_for(
                downloader.download(task.url),
                timeout=DOWNLOAD_TIMEOUT,
            )
        except asyncio.TimeoutError:
            await safe_edit(task.status_msg, "❌ Время загрузки истекло (>3 мин).")
            self._total_err += 1
            return

        if not result.ok:
            await safe_edit(task.status_msg, f"❌ {result.error}")
            self._total_err += 1
            return

        try:
            await safe_edit(task.status_msg, "📤 Отправляю…")
            await task.reply_to.reply_video(
                video=FSInputFile(result.path),
                caption=build_caption(result, task.platform),
                parse_mode="HTML",
            )
            await task.status_msg.delete()
            self._total_ok += 1
        except TelegramBadRequest:
            await safe_edit(
                task.status_msg,
                "❌ Не удалось отправить файл — вероятно, он слишком большой для Telegram.",
            )
            self._total_err += 1
        finally:
            VideoDownloader.cleanup(result.path)
