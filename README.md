# 🎬 Video Downloader Bot

Telegram-бот для скачивания видео с **TikTok** и **Instagram** (Reels / Posts).
aiogram 3 · yt-dlp · SQLite · очередь с пулом воркеров.

---

## Структура проекта

```
downloader_bot/
├── run.py                     # точка входа: python run.py
├── .env / .env.example        # конфигурация
├── requirements.txt
└── app/
    ├── main.py                # сборка Dispatcher, startup/shutdown
    ├── states.py              # FSM-состояния
    ├── core/
    │   ├── config.py          # настройки из окружения + константы
    │   └── logger.py          # настройка логирования
    ├── db/
    │   └── database.py        # SQLite (WAL) + кэши + write-behind
    ├── handlers/
    │   ├── user.py            # /start, /lang, /help, /stats, ссылки
    │   └── admin.py           # админ-панель
    ├── keyboards/             # inline-клавиатуры
    ├── locales/               # тексты ru / en / uz
    ├── middlewares/
    │   ├── throttling.py      # антифлуд
    │   └── user_context.py    # язык, режим техработ
    ├── services/
    │   ├── downloader.py      # обёртка yt-dlp
    │   ├── queue.py           # очередь загрузок + кэш file_id
    │   └── subscription.py    # обязательная подписка на каналы
    └── utils/                 # разбор ссылок, форматирование текста
```

---

## Быстрый старт

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env               # укажите BOT_TOKEN и ADMIN_IDS
python run.py
```

FFmpeg нужен для склейки видео- и аудиопотоков:

- Ubuntu/Debian — `sudo apt install ffmpeg`
- macOS — `brew install ffmpeg`
- Windows — [ffmpeg.org/download](https://ffmpeg.org/download.html), добавить в PATH

### Docker

```bash
docker compose up -d --build
```

---

## Конфигурация (`.env`)

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `BOT_TOKEN` | — | токен от @BotFather (обязательно) |
| `ADMIN_IDS` | — | ID админов через запятую |
| `DB_PATH` | `bot_data.db` | файл SQLite |
| `DOWNLOAD_DIR` | `downloads` | временная папка для файлов |
| `MAX_FILE_SIZE_MB` | `49` | лимит размера (Telegram — 50 МБ) |
| `MAX_WORKERS` | `15` | параллельных загрузок |
| `MAX_QUEUE_SIZE` | `500` | размер очереди |
| `MAX_USER_TASKS` | `2` | задач от одного пользователя |
| `DOWNLOAD_TIMEOUT` | `180` | секунд на загрузку |
| `MAX_WAIT_TIME` | `600` | секунд ожидания в очереди |
| `THROTTLE_MS` | `700` | антифлуд-интервал |
| `LOG_LEVEL` | `INFO` | уровень логов |
| `DEFAULT_LANG` | `ru` | язык по умолчанию |
| `FILE_CACHE_ENABLED` | `true` | кэш `file_id` |
| `USER_FLUSH_INTERVAL` | `30` | период записи активности, сек |

---

## Как это работает

```
сообщение
  └── ThrottlingMiddleware        # антифлуд
        └── UserContextMiddleware # язык из кэша, режим техработ
              └── handle_link
                    ├── кэш file_id → мгновенная отправка (без скачивания)
                    └── очередь → воркер → yt-dlp → отправка → запись в кэш
```

### Ключевые оптимизации

| Решение | Что даёт |
|---|---|
| Кэш `file_id` в SQLite | повторная ссылка отдаётся мгновенно, без скачивания и трафика |
| Дедупликация «в полёте» | одну и ту же ссылку от разных пользователей качаем один раз |
| Селектор формата с `filesize` + `max_filesize` | обычно одна попытка вместо перебора 720p→480p→360p, большие файлы обрываются на лету |
| Собственный `ThreadPoolExecutor` | пул под `MAX_WORKERS`, дефолтный executor цикла не переполняется |
| Кэш языка, настроек и каналов в памяти | нет обращений к БД на каждое сообщение |
| Write-behind `last_active` | одна пачечная запись раз в 30 с вместо записи на каждое сообщение |
| SQLite WAL + `synchronous=NORMAL` + индексы | чтения не блокируются записями |
| Параллельная проверка подписок (`asyncio.gather`) | проверка N каналов за время одного запроса |
| `parse_mode` по умолчанию + экранирование HTML | меньше дублей в коде, нет падений на «ломаных» заголовках |
| Коды ошибок вместо строк | сообщения об ошибках переводятся на язык пользователя |
| Корректный shutdown | воркеры и БД останавливаются штатно, буфер активности сбрасывается |

---

## Админ-панель

`/admin` (только для `ADMIN_IDS`):

- каналы обязательной подписки: добавить / включить / выключить / удалить;
- настройки: проверка подписки, режим техработ;
- статистика: пользователи, каналы, очередь, кэш.

---

## Ограничения

- Максимум **50 МБ** — лимит Telegram Bot API.
- Приватные видео и контент с авторскими ограничениями не загружаются.
- Требуется Python **3.9+** и FFmpeg в PATH.
