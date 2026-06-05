from __future__ import annotations

TEXTS: dict[str, dict[str, str]] = {
    "ru": {
        "choose_language": (
            "👋 <b>Добро пожаловать!</b>\n\n"
            "Пожалуйста, выберите язык интерфейса:"
        ),
        "language_set": "✅ Язык установлен: <b>Русский</b>",
        "send_link": (
            "📎 Отправьте ссылку на видео с <b>TikTok</b> или <b>Instagram</b> —\n"
            "я скачаю его и пришлю прямо сюда.\n\n"
            "⚠️ Максимальный размер файла: <b>50 МБ</b>"
        ),
        "downloading": "{emoji} Загружаю с {platform}…",
        "in_queue": "⏳ В очереди: позиция <b>{pos}</b>",
        "error_unsupported": (
            "⚠️ Поддерживаются только ссылки с <b>TikTok</b> и <b>Instagram</b>."
        ),
        "error_queue_full": "⚠️ Очередь переполнена. Попробуйте через минуту.",
        "error_user_limit": (
            "⚠️ У вас уже {limit} задачи в очереди. Дождитесь их выполнения."
        ),
        "subscribe_required": (
            "🔔 <b>Для использования бота подпишитесь на каналы:</b>\n\n"
            "{channels}\n\n"
            "После подписки нажмите кнопку ниже."
        ),
        "subscribe_check_btn": "✅ Проверить подписку",
        "subscribe_success": (
            "✅ <b>Отлично!</b> Все подписки подтверждены.\n"
            "Теперь вы можете пользоваться ботом."
        ),
        "subscribe_fail": (
            "❌ Вы ещё не подписались на все каналы.\n\n"
            "Оставшиеся:\n{channels}\n\n"
            "Подпишитесь и нажмите кнопку снова."
        ),
        "help_text": (
            "ℹ️ <b>Как пользоваться</b>\n\n"
            "Отправьте ссылку на видео — бот скачает и пришлёт файл.\n\n"
            "<b>Платформы:</b>\n"
            "• TikTok\n"
            "• Instagram Reels и Posts\n\n"
            "<b>Ограничения:</b>\n"
            "• Максимальный размер: <b>50 МБ</b>\n"
            "• Приватные видео и видео с авторскими правами не загружаются"
        ),
        "stats_text": (
            "📊 <b>Статистика бота</b>\n\n"
            "• В очереди: <b>{queue_size}</b> / {max_queue}\n"
            "• Активных загрузок: <b>{active}</b> / {max_workers}\n"
            "• Успешно обработано: <b>{total_ok}</b>\n"
            "• Ошибок: <b>{total_err}</b>"
        ),
    },
    "en": {
        "choose_language": (
            "👋 <b>Welcome!</b>\n\n"
            "Please choose your language:"
        ),
        "language_set": "✅ Language set: <b>English</b>",
        "send_link": (
            "📎 Send a link to a video from <b>TikTok</b> or <b>Instagram</b> —\n"
            "I'll download it and send it right here.\n\n"
            "⚠️ Maximum file size: <b>50 MB</b>"
        ),
        "downloading": "{emoji} Downloading from {platform}…",
        "in_queue": "⏳ In queue: position <b>{pos}</b>",
        "error_unsupported": (
            "⚠️ Only links from <b>TikTok</b> and <b>Instagram</b> are supported."
        ),
        "error_queue_full": "⚠️ Queue is full. Please try again in a minute.",
        "error_user_limit": (
            "⚠️ You already have {limit} tasks in the queue. Please wait for them to finish."
        ),
        "subscribe_required": (
            "🔔 <b>To use the bot, please subscribe to these channels:</b>\n\n"
            "{channels}\n\n"
            "Press the button below after subscribing."
        ),
        "subscribe_check_btn": "✅ Check subscription",
        "subscribe_success": (
            "✅ <b>Great!</b> All subscriptions confirmed.\n"
            "You can now use the bot."
        ),
        "subscribe_fail": (
            "❌ You haven't subscribed to all channels yet.\n\n"
            "Remaining:\n{channels}\n\n"
            "Subscribe and press the button again."
        ),
        "help_text": (
            "ℹ️ <b>How to use</b>\n\n"
            "Send a video link — the bot will download and send the file.\n\n"
            "<b>Platforms:</b>\n"
            "• TikTok\n"
            "• Instagram Reels and Posts\n\n"
            "<b>Limits:</b>\n"
            "• Maximum size: <b>50 MB</b>\n"
            "• Private videos and copyrighted content cannot be downloaded"
        ),
        "stats_text": (
            "📊 <b>Bot Statistics</b>\n\n"
            "• In queue: <b>{queue_size}</b> / {max_queue}\n"
            "• Active downloads: <b>{active}</b> / {max_workers}\n"
            "• Successfully processed: <b>{total_ok}</b>\n"
            "• Errors: <b>{total_err}</b>"
        ),
    },
    "uz": {
        "choose_language": (
            "👋 <b>Xush kelibsiz!</b>\n\n"
            "Iltimos, tilni tanlang:"
        ),
        "language_set": "✅ Til o'rnatildi: <b>O'zbek</b>",
        "send_link": (
            "📎 <b>TikTok</b> yoki <b>Instagram</b>dan video havolasini yuboring —\n"
            "men uni yuklab, shu yerga yuboraman.\n\n"
            "⚠️ Maksimal fayl hajmi: <b>50 MB</b>"
        ),
        "downloading": "{emoji} {platform}dan yuklanmoqda…",
        "in_queue": "⏳ Navbatda: <b>{pos}</b>-o'rin",
        "error_unsupported": (
            "⚠️ Faqat <b>TikTok</b> va <b>Instagram</b> havolalari qo'llab-quvvatlanadi."
        ),
        "error_queue_full": "⚠️ Navbat to'ldi. Bir daqiqadan so'ng urinib ko'ring.",
        "error_user_limit": (
            "⚠️ Navbatda allaqachon {limit} ta vazifangiz bor. Ularni kutib turing."
        ),
        "subscribe_required": (
            "🔔 <b>Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:</b>\n\n"
            "{channels}\n\n"
            "Obuna bo'lgach, quyidagi tugmani bosing."
        ),
        "subscribe_check_btn": "✅ Obunani tekshirish",
        "subscribe_success": (
            "✅ <b>Ajoyib!</b> Barcha obunalar tasdiqlandi.\n"
            "Endi botdan foydalanishingiz mumkin."
        ),
        "subscribe_fail": (
            "❌ Siz hali barcha kanallarga obuna bo'lmadingiz.\n\n"
            "Qolganlar:\n{channels}\n\n"
            "Obuna bo'ling va tugmani qayta bosing."
        ),
        "help_text": (
            "ℹ️ <b>Qanday foydalanish kerak</b>\n\n"
            "Video havolasini yuboring — bot faylni yuklab, shu yerga yuboradi.\n\n"
            "<b>Platformalar:</b>\n"
            "• TikTok\n"
            "• Instagram Reels va Posts\n\n"
            "<b>Cheklovlar:</b>\n"
            "• Maksimal hajm: <b>50 MB</b>\n"
            "• Shaxsiy videolar yuklab olinmaydi"
        ),
        "stats_text": (
            "📊 <b>Bot statistikasi</b>\n\n"
            "• Navbatda: <b>{queue_size}</b> / {max_queue}\n"
            "• Faol yuklamalar: <b>{active}</b> / {max_workers}\n"
            "• Muvaffaqiyatli bajarildi: <b>{total_ok}</b>\n"
            "• Xatolar: <b>{total_err}</b>"
        ),
    },
}


def t(user_lang: str, key: str, **kwargs: object) -> str:
    lang = user_lang if user_lang in TEXTS else "ru"
    template = TEXTS[lang].get(key, TEXTS["ru"].get(key, key))
    return template.format(**kwargs) if kwargs else template
