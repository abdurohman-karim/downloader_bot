import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")

DOWNLOAD_DIR: str = "downloads"

# Telegram hard limit is 50 MB; use 49 MB as safe margin
MAX_FILE_SIZE: int = 49 * 1024 * 1024

SUPPORTED_DOMAINS: tuple[str, ...] = (
    "tiktok.com",
    "vm.tiktok.com",
    "instagram.com",
    "instagr.am",
)

PLATFORM_EMOJIS: dict[str, str] = {
    "TikTok": "🎵",
    "Instagram": "📸",
}

MAX_WORKERS: int = 15       # параллельных загрузок одновременно
MAX_QUEUE_SIZE: int = 500   # максимум задач в очереди
MAX_USER_TASKS: int = 2     # задач от одного пользователя в очереди
DOWNLOAD_TIMEOUT: int = 180 # секунд на одну загрузку (3 мин)
MAX_WAIT_TIME: int = 600    # секунд ожидания в очереди (10 мин)
