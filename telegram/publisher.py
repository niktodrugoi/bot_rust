import logging
import time  # для timestamp в имени файла
from aiogram.types import BufferedInputFile
from aiogram.types import BufferedInputFile  # ← это главное исправление!

from config import CHANNEL_ID

logger = logging.getLogger(__name__)

async def publish_to_channel(bot, text: str, image=None, commit_id: str = None):
    """
    Публикует пост в канал.
    - Если image передан (BufferedInputFile, bytes или file_id), отправляет как фото с caption
    - Если image=None — отправляет как текст
    """
    try:
        if image:
            # Если image — это bytes, оборачиваем в BufferedInputFile с уникальным именем
            if isinstance(image, bytes):
                filename = f"commit_{commit_id or 'unknown'}_{int(time.time()*1000)}.png"
                image = BufferedInputFile(image, filename=filename)
            elif not isinstance(image, BufferedInputFile):
                logger.warning(f"Неправильный тип image для commit {commit_id}: {type(image)}")
                image = None  # если тип неверный — отправляем как текст

            await bot.send_photo(
                chat_id=CHANNEL_ID,
                photo=image,
                caption=text,
                parse_mode=None
            )
            logger.info(f"Опубликован коммит {commit_id} в канал как фото")
        else:
            await bot.send_message(
                chat_id=CHANNEL_ID,
                text=text,
                parse_mode=None
            )
            logger.info(f"Опубликован коммит {commit_id} в канал как текст")

    except Exception as e:
        logger.error(f"Ошибка публикации в канал (commit {commit_id or 'без ID'}): {e}")