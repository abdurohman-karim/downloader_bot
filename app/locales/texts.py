"""Тексты интерфейса. Ключ -> перевод на ru / en / uz."""

from __future__ import annotations

TEXTS: dict[str, dict[str, str]] = {
    "ru": {
        "choose_language": "👋 <b>Добро пожаловать!</b>\n\nПожалуйста, выберите язык интерфейса:",
        "language_set": "✅ Язык установлен: <b>Русский</b>",
        "send_link": (
            "📎 Отправьте ссылку на видео с <b>TikTok</b> или <b>Instagram</b> —\n"
            "я скачаю его и пришлю прямо сюда.\n\n"
            "⚠️ Максимальный размер файла: <b>50 МБ</b>"
        ),
        "adding_to_queue": "⏳ Добавляю в очередь…",
        "downloading": "{emoji} Загружаю с {platform}…",
        "sending": "📤 Отправляю…",
        "in_queue": "⏳ В очереди: позиция <b>{pos}</b>",
        "bot_disabled": "🛠 Бот временно на техобслуживании. Попробуйте позже.",
        "error_unsupported": "⚠️ Поддерживаются только ссылки с <b>TikTok</b> и <b>Instagram</b>.",
        "error_queue_full": "⚠️ Очередь переполнена. Попробуйте через минуту.",
        "error_user_limit": "⚠️ У вас уже {limit} задачи в очереди. Дождитесь их выполнения.",
        "error_wait_timeout": "❌ Запрос отменён — слишком долго ждал в очереди.",
        "error_timeout": "❌ Время загрузки истекло.",
        "error_send_failed": "❌ Не удалось отправить файл — вероятно, он слишком большой для Telegram.",
        "err_unavailable": "❌ Видео недоступно.",
        "err_private": "❌ Видео приватное.",
        "err_age": "❌ Видео с возрастным ограничением.",
        "err_login": "❌ Требуется авторизация (приватный контент).",
        "err_copyright": "❌ Видео заблокировано по авторским правам.",
        "err_bad_url": "❌ Неверная ссылка.",
        "err_unsupported": "❌ Ссылка не поддерживается.",
        "err_no_format": "❌ Не удалось найти подходящий формат видео.",
        "err_network": "❌ Ошибка сети. Попробуйте позже.",
        "err_too_big": "❌ Видео слишком большое для Telegram (лимит 50 МБ).",
        "err_unknown": "❌ Не удалось скачать видео. Попробуйте позже.",
        "subscribe_required": (
            "🔔 <b>Для использования бота подпишитесь на каналы:</b>\n\n"
            "{channels}\n\nПосле подписки нажмите кнопку ниже."
        ),
        "subscribe_check_btn": "✅ Проверить подписку",
        "subscribe_success": "✅ <b>Отлично!</b> Все подписки подтверждены.\nТеперь вы можете пользоваться ботом.",
        "subscribe_fail": "❌ Вы ещё не подписались на все каналы.",
        "help_text": (
            "ℹ️ <b>Как пользоваться</b>\n\n"
            "Отправьте ссылку на видео — бот скачает и пришлёт файл.\n\n"
            "<b>Платформы:</b>\n• TikTok\n• Instagram Reels и Posts\n\n"
            "<b>Ограничения:</b>\n"
            "• Максимальный размер: <b>50 МБ</b>\n"
            "• Приватные видео и видео с авторскими правами не загружаются\n\n"
            "<b>Команды:</b>\n/start — начать\n/lang — сменить язык\n/stats — статистика"
        ),
        "stats_text": (
            "📊 <b>Статистика бота</b>\n\n"
            "• В очереди: <b>{queue_size}</b> / {max_queue}\n"
            "• Активных загрузок: <b>{active}</b> / {max_workers}\n"
            "• Успешно обработано: <b>{total_ok}</b>\n"
            "• Из кэша: <b>{total_cached}</b>\n"
            "• Ошибок: <b>{total_err}</b>"
        ),
    },
    "en": {
        "choose_language": "👋 <b>Welcome!</b>\n\nPlease choose your language:",
        "language_set": "✅ Language set: <b>English</b>",
        "send_link": (
            "📎 Send a link to a video from <b>TikTok</b> or <b>Instagram</b> —\n"
            "I'll download it and send it right here.\n\n"
            "⚠️ Maximum file size: <b>50 MB</b>"
        ),
        "adding_to_queue": "⏳ Adding to the queue…",
        "downloading": "{emoji} Downloading from {platform}…",
        "sending": "📤 Sending…",
        "in_queue": "⏳ In queue: position <b>{pos}</b>",
        "bot_disabled": "🛠 The bot is under maintenance. Please try again later.",
        "error_unsupported": "⚠️ Only <b>TikTok</b> and <b>Instagram</b> links are supported.",
        "error_queue_full": "⚠️ The queue is full. Please try again in a minute.",
        "error_user_limit": "⚠️ You already have {limit} tasks in the queue. Please wait.",
        "error_wait_timeout": "❌ Request cancelled — it waited in the queue for too long.",
        "error_timeout": "❌ Download timed out.",
        "error_send_failed": "❌ Could not send the file — it is probably too large for Telegram.",
        "err_unavailable": "❌ Video is unavailable.",
        "err_private": "❌ The video is private.",
        "err_age": "❌ The video is age-restricted.",
        "err_login": "❌ Login required (private content).",
        "err_copyright": "❌ The video is blocked for copyright reasons.",
        "err_bad_url": "❌ Invalid link.",
        "err_unsupported": "❌ This link is not supported.",
        "err_no_format": "❌ No suitable video format found.",
        "err_network": "❌ Network error. Please try again later.",
        "err_too_big": "❌ The video is too large for Telegram (50 MB limit).",
        "err_unknown": "❌ Could not download the video. Please try again later.",
        "subscribe_required": (
            "🔔 <b>To use the bot, please subscribe to these channels:</b>\n\n"
            "{channels}\n\nPress the button below after subscribing."
        ),
        "subscribe_check_btn": "✅ Check subscription",
        "subscribe_success": "✅ <b>Great!</b> All subscriptions confirmed.\nYou can now use the bot.",
        "subscribe_fail": "❌ You haven't subscribed to all channels yet.",
        "help_text": (
            "ℹ️ <b>How to use</b>\n\n"
            "Send a video link — the bot will download and send the file.\n\n"
            "<b>Platforms:</b>\n• TikTok\n• Instagram Reels and Posts\n\n"
            "<b>Limits:</b>\n"
            "• Maximum size: <b>50 MB</b>\n"
            "• Private and copyrighted videos cannot be downloaded\n\n"
            "<b>Commands:</b>\n/start — start\n/lang — change language\n/stats — statistics"
        ),
        "stats_text": (
            "📊 <b>Bot statistics</b>\n\n"
            "• In queue: <b>{queue_size}</b> / {max_queue}\n"
            "• Active downloads: <b>{active}</b> / {max_workers}\n"
            "• Successfully processed: <b>{total_ok}</b>\n"
            "• Served from cache: <b>{total_cached}</b>\n"
            "• Errors: <b>{total_err}</b>"
        ),
    },
    "uz": {
        "choose_language": "👋 <b>Xush kelibsiz!</b>\n\nIltimos, tilni tanlang:",
        "language_set": "✅ Til o'rnatildi: <b>O'zbek</b>",
        "send_link": (
            "📎 <b>TikTok</b> yoki <b>Instagram</b>dan video havolasini yuboring —\n"
            "men uni yuklab, shu yerga yuboraman.\n\n"
            "⚠️ Maksimal fayl hajmi: <b>50 MB</b>"
        ),
        "adding_to_queue": "⏳ Navbatga qo'shilmoqda…",
        "downloading": "{emoji} {platform}dan yuklanmoqda…",
        "sending": "📤 Yuborilmoqda…",
        "in_queue": "⏳ Navbatda: <b>{pos}</b>-o'rin",
        "bot_disabled": "🛠 Bot texnik xizmatda. Keyinroq urinib ko'ring.",
        "error_unsupported": "⚠️ Faqat <b>TikTok</b> va <b>Instagram</b> havolalari qo'llab-quvvatlanadi.",
        "error_queue_full": "⚠️ Navbat to'ldi. Bir daqiqadan so'ng urinib ko'ring.",
        "error_user_limit": "⚠️ Navbatda allaqachon {limit} ta vazifangiz bor. Ularni kutib turing.",
        "error_wait_timeout": "❌ So'rov bekor qilindi — navbatda juda uzoq kutdi.",
        "error_timeout": "❌ Yuklab olish vaqti tugadi.",
        "error_send_failed": "❌ Faylni yuborib bo'lmadi — u Telegram uchun juda katta.",
        "err_unavailable": "❌ Video mavjud emas.",
        "err_private": "❌ Video shaxsiy.",
        "err_age": "❌ Video yosh cheklovi bilan.",
        "err_login": "❌ Avtorizatsiya talab qilinadi (shaxsiy kontent).",
        "err_copyright": "❌ Video mualliflik huquqi bo'yicha bloklangan.",
        "err_bad_url": "❌ Noto'g'ri havola.",
        "err_unsupported": "❌ Havola qo'llab-quvvatlanmaydi.",
        "err_no_format": "❌ Mos video formati topilmadi.",
        "err_network": "❌ Tarmoq xatosi. Keyinroq urinib ko'ring.",
        "err_too_big": "❌ Video Telegram uchun juda katta (50 MB chegara).",
        "err_unknown": "❌ Videoni yuklab bo'lmadi. Keyinroq urinib ko'ring.",
        "subscribe_required": (
            "🔔 <b>Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:</b>\n\n"
            "{channels}\n\nObuna bo'lgach, quyidagi tugmani bosing."
        ),
        "subscribe_check_btn": "✅ Obunani tekshirish",
        "subscribe_success": "✅ <b>Ajoyib!</b> Barcha obunalar tasdiqlandi.\nEndi botdan foydalanishingiz mumkin.",
        "subscribe_fail": "❌ Siz hali barcha kanallarga obuna bo'lmadingiz.",
        "help_text": (
            "ℹ️ <b>Qanday foydalanish kerak</b>\n\n"
            "Video havolasini yuboring — bot faylni yuklab, shu yerga yuboradi.\n\n"
            "<b>Platformalar:</b>\n• TikTok\n• Instagram Reels va Posts\n\n"
            "<b>Cheklovlar:</b>\n"
            "• Maksimal hajm: <b>50 MB</b>\n"
            "• Shaxsiy videolar yuklab olinmaydi\n\n"
            "<b>Buyruqlar:</b>\n/start — boshlash\n/lang — tilni almashtirish\n/stats — statistika"
        ),
        "stats_text": (
            "📊 <b>Bot statistikasi</b>\n\n"
            "• Navbatda: <b>{queue_size}</b> / {max_queue}\n"
            "• Faol yuklamalar: <b>{active}</b> / {max_workers}\n"
            "• Muvaffaqiyatli: <b>{total_ok}</b>\n"
            "• Keshdan: <b>{total_cached}</b>\n"
            "• Xatolar: <b>{total_err}</b>"
        ),
    },
}
