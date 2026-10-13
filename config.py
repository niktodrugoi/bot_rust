import os

from dotenv import load_dotenv

load_dotenv()  # подтягивает переменные из файла .env (если он есть)


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Не задана переменная окружения {name}. "
            "Скопируй .env.example в .env и заполни его."
        )
    return value


# Telegram bot token (получить у @BotFather)
BOT_TOKEN = _required("BOT_TOKEN")

# Личный chat ID модератора (узнать можно у @userinfobot)
MODERATOR_CHAT_ID = int(_required("MODERATOR_CHAT_ID"))

# ID Telegram-канала (начинается с -100...)
CHANNEL_ID = int(_required("CHANNEL_ID"))

# Ollama settings
OLLAMA_URL = "http://localhost:11434/api/generate"   # обычно менять не нужно
OLLAMA_MODEL = "llama3.1:8b"           # ← ты указал именно эту модель — отлично!

# Parsing settings
SITE_URL = "https://commits.facepunch.com"
PARSE_INTERVAL = 300  # Seconds between parses (5 minutes)

# Prompt для Ollama (можно чуть улучшить под llama3.1, но и так работает)
OLLAMA_PROMPT = """
Ты — эксперт по игре Rust (всегда пиши название игры именно как "Rust" с большой буквы R, никогда не используй "rust", "Rust" в другом регистре, "Руст" или другие варианты).

Проанализируй сообщение коммита из репозитория Rust и напиши краткое понятное объяснение для обычного игрока на русском языке: что пофиксили, что добавили, что изменили в игре.

Стиль: дружелюбный, простой, без технического жаргона. Максимум 3–4 предложения.

Обязательно:
- Название игры всегда "Rust" (с большой R).
- Не используй "rust" ни в каком виде.
- Не переводи название игры на русский как "Руст".
"""

# Время ежедневного отчёта (в UTC, если сервер в Европе — 00:00 CET = 23:00 UTC предыдущего дня)
DAILY_REPORT_HOUR = 23  # 23:00 UTC = 00:00 CET
DAILY_REPORT_MINUTE = 0

# Куда слать отчёт (можно в канал или личку)
DAILY_REPORT_CHAT_ID = CHANNEL_ID  # или MODERATOR_CHAT_ID, если только тебе