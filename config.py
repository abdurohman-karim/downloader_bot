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
