# 🎬 Video Downloader Bot

Telegram-бот для скачивания видео с YouTube, TikTok и Instagram.

## Стек

| Компонент | Назначение |
|-----------|------------|
| `aiogram 3` | Telegram Bot Framework |
| `yt-dlp` | Загрузка видео (YouTube / TikTok / Instagram) |
| `FFmpeg` | Мerge видео + аудио потоков |

---

## Быстрый старт

### 1. Клонируй / распакуй проект

```
video_downloader_bot/
├── bot.py           # Точка входа, handlers
├── downloader.py    # yt-dlp обёртка
├── config.py        # Конфигурация
├── requirements.txt
└── .env
```

### 2. Установи зависимости

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

### 3. Установи FFmpeg

FFmpeg нужен для склейки видео- и аудио-потоков (особенно для YouTube 720p+).

- **Ubuntu/Debian**: `sudo apt install ffmpeg`
- **macOS**: `brew install ffmpeg`
- **Windows**: [ffmpeg.org/download](https://ffmpeg.org/download.html) → добавь в PATH

### 4. Создай `.env`

```env
BOT_TOKEN=1234567890:ABCDefgh...   # токен от @BotFather
```

### 5. Запусти

```bash
python bot.py
```

---

## Архитектура

```
bot.py
  └── handle_link()          # aiogram handler
        └── downloader.download(url)
              └── _attempt(url, fmt)   # asyncio.to_thread → yt-dlp
                    # повторяет: 720p → 480p → 360p → worst
                    # первый результат ≤ 49 МБ → отдаёт файл
```

**Ключевые решения:**

| Решение | Причина |
|---------|---------|
| `asyncio.to_thread` | yt-dlp блокирующий — выносим в threadpool |
| Quality fallback chain | Автоматически выбирает лучшее качество ≤ 50 МБ |
| Per-user `_busy` set | Предотвращает параллельные загрузки от одного пользователя |
| `noplaylist=True` | Не скачивает плейлист, если передали URL плейлиста |
| `skip_updates=True` | При рестарте старые сообщения не обрабатываются |

---

## Ограничения

- Максимум **50 МБ** (лимит Telegram Bot API)
- Приватные видео не загружаются
- YouTube с возрастными ограничениями требует cookies (не реализовано)
- Instagram Stories доступны только из публичных аккаунтов

## Требования

- Python **3.9+** (используется `asyncio.to_thread`)
- FFmpeg в системном PATH
