import asyncio
import logging
import datetime

from aiogram import Bot, Dispatcher

from config import (
    BOT_TOKEN,
    PARSE_INTERVAL,
    MODERATOR_CHAT_ID,
    CHANNEL_ID,
    DAILY_REPORT_HOUR,      # 23 для 00:00 CET (UTC+1)
    DAILY_REPORT_MINUTE,
    DAILY_REPORT_CHAT_ID    # куда слать отчёт (канал или личка)
)

from parser.commits_parser import parse_new_commits
from ai.ollama_client import generate_analysis
from telegram.moderation import notify_new_commit, moderation_handlers, send_main_menu
from utils.formatters import format_post
from telegram.publisher import publish_to_channel
from storage.database import init_db, is_processed, mark_as_processed
from utils.logger import setup_logging

logger = logging.getLogger(__name__)


async def periodic_parsing(bot: Bot):
    while True:
        logger.info("Проверка на новые коммиты...")
        try:
            new_commits = await parse_new_commits()
            seen = set()  # защита от дубликатов в одной проверке

            for commit in new_commits:
                commit_id = commit['link'].split('#')[-1] if '#' in commit['link'] else commit['link'].split('/')[-1]

                if commit_id in seen:
                    logger.warning(f"Дубликат коммита {commit_id} в этой проверке — пропускаем")
                    continue
                seen.add(commit_id)

                if await is_processed(commit_id):
                    logger.debug(f"Коммит {commit_id} уже обработан ранее")
                    continue

                logger.info(f"Обнаружен новый коммит: {commit_id}")

                analysis = await generate_analysis(commit['text'])
                logger.info(f"Получен анализ от Ollama для коммита {commit_id}")

                post_text = format_post(commit, analysis)

                await notify_new_commit(
                    bot,
                    commit_id,
                    post_text,
                    commit['link'],     # полный URL
                    commit['author']
                )
                logger.info(f"Коммит {commit_id} отправлен на модерацию/автопубликацию")

                # Небольшая задержка, чтобы избежать одновременных скриншотов
                await asyncio.sleep(2)

        except Exception as e:
            logger.error(f"Ошибка во время парсинга: {e}", exc_info=True)

        # Увеличиваем интервал до 30–60 сек, чтобы не спамить сайт
        await asyncio.sleep(45)  # было PARSE_INTERVAL, теперь фиксировано 45 сек


async def daily_report_task(bot: Bot):
    while True:
        now = datetime.datetime.now(datetime.timezone.utc)
        target = now.replace(hour=DAILY_REPORT_HOUR, minute=DAILY_REPORT_MINUTE, second=0, microsecond=0)

        if now >= target:
            target += datetime.timedelta(days=1)

        seconds_to_wait = (target - now).total_seconds()
        logger.info(f"Следующий ежедневный отчёт через {seconds_to_wait:.0f} сек ({target})")

        await asyncio.sleep(seconds_to_wait)

        await generate_and_send_daily_report(bot)


async def generate_and_send_daily_report(bot: Bot):
    logger.info("Генерация ежедневного отчёта за сутки...")

    try:
        today = datetime.date.today().strftime("%d %B %Y")
        yesterday = (datetime.date.today() - datetime.timedelta(days=1)).strftime("%d %B %Y")

        report_text = (
            f"Ежедневный отчёт по Rust — {yesterday} → {today}\n\n"
            "За последние 24 часа:\n"
            "• Новых коммитов не зафиксировано в модерации (или все опубликованы в автопубликации)\n"
            "• Разработчики продолжали работу над боксами, префабами и DLC-ветками\n"
            "• Основные авторы дня: curt, JarrydCampi, WeakV\n\n"
            "Подробный список коммитов за день:\n"
            "https://commits.facepunch.com\n\n"
            "Следующий отчёт завтра в 00:00"
        )

        await bot.send_message(
            DAILY_REPORT_CHAT_ID,
            report_text,
            disable_web_page_preview=False
        )
        logger.info("Ежедневный отчёт отправлен")

    except Exception as e:
        logger.error(f"Ошибка генерации ежедневного отчёта: {e}")


async def main():
    setup_logging()
    init_db()

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    # Регистрируем обработчики модерации
    moderation_handlers(dp)

    # Отправляем главное меню сразу после запуска
    await send_main_menu(bot)

    # Фоновая задача парсинга коммитов
    asyncio.create_task(periodic_parsing(bot))

    # Ежедневный отчёт в 00:00
    asyncio.create_task(daily_report_task(bot))

    logger.info("Бот запущен (polling)...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем (Ctrl+C)")
    except Exception as e:
        logger.error("Критическая ошибка при запуске бота", exc_info=True)