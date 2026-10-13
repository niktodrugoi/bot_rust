import logging
import asyncio
import json
import os

from aiogram import Dispatcher
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import MODERATOR_CHAT_ID
from telegram.publisher import publish_to_channel
from storage.database import mark_as_processed
from parser.commits_parser import parse_new_commits
from utils.screenshot import make_commit_screenshot  # скриншот коммита

logger = logging.getLogger(__name__)

# Состояния FSM
class ModerationStates(StatesGroup):
    waiting_for_edit = State()
    waiting_for_image = State()

# Хранилище постов на модерации
moderation_data = {}
auto_publish_enabled = False  # по умолчанию выключена

# Файлы сохранения
MODERATION_FILE = "moderation_data.json"
SETTINGS_FILE = "bot_settings.json"


# ────────────────────────────────
# Загрузка / сохранение
# ────────────────────────────────

def load_settings():
    global auto_publish_enabled
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                settings = json.load(f)
                auto_publish_enabled = settings.get('auto_publish_enabled', False)
            logger.info(f"Автопубликация загружена: {'Вкл' if auto_publish_enabled else 'Выкл'}")
        except Exception as e:
            logger.error(f"Ошибка загрузки настроек: {e}")


def save_settings():
    try:
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump({'auto_publish_enabled': auto_publish_enabled}, f, ensure_ascii=False, indent=2)
        logger.info("Настройки сохранены")
    except Exception as e:
        logger.error(f"Ошибка сохранения настроек: {e}")


def load_moderation_data():
    global moderation_data
    if os.path.exists(MODERATION_FILE):
        try:
            with open(MODERATION_FILE, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
                moderation_data = {}
                for k, v in loaded.items():
                    moderation_data[k] = {
                        'text': v['text'],
                        'image_bytes': v.get('image_bytes'),
                        'message_id': v.get('message_id')
                    }
            logger.info(f"Загружено {len(moderation_data)} постов из файла")
        except Exception as e:
            logger.error(f"Ошибка загрузки moderation_data: {e}")
            moderation_data = {}
    else:
        moderation_data = {}


def save_moderation_data():
    try:
        serializable = {k: {'text': v['text'], 'message_id': v.get('message_id')} for k, v in moderation_data.items()}
        with open(MODERATION_FILE, 'w', encoding='utf-8') as f:
            json.dump(serializable, f, ensure_ascii=False, indent=2)
        logger.info("moderation_data сохранена")
    except Exception as e:
        logger.error(f"Ошибка сохранения moderation_data: {e}")


# Загрузка при старте модуля
load_settings()
load_moderation_data()


# ────────────────────────────────
# Главное меню
# ────────────────────────────────

def get_main_menu_keyboard():
    auto_text = "Автопубликация: Вкл" if auto_publish_enabled else "Автопубликация: Выкл"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Проверить новые коммиты", callback_data="check_new_commits")],
        [InlineKeyboardButton(text="📋 Список на модерации", callback_data="show_pending")],
        [InlineKeyboardButton(text="📭 Последний пост", callback_data="show_last_pending")],
        [InlineKeyboardButton(text=auto_text, callback_data="toggle_auto_publish")],
        [InlineKeyboardButton(text="❓ Помощь", callback_data="help_menu")],
    ])


async def send_main_menu(bot):
    text = (
        "👋 Привет, Эмин!\n"
        f"Автопубликация: {'ВКЛЮЧЕНА' if auto_publish_enabled else 'ВЫКЛЮЧЕНА'}\n\n"
        "Выбери действие:"
    )
    await bot.send_message(MODERATOR_CHAT_ID, text, reply_markup=get_main_menu_keyboard())
    logger.info("Главное меню отправлено")


# ────────────────────────────────
# Уведомление о новом коммите + скриншот (только блок нового коммита)
# ────────────────────────────────

async def notify_new_commit(bot, commit_id: str, post_text: str, url: str, author: str = "Unknown"):
    global auto_publish_enabled

    # Фикс "Rust"
    post_text = post_text.replace("rust", "Rust") \
                         .replace("Rust", "Rust") \
                         .replace("Руст", "Rust") \
                         .replace("rRust", "Rust") \
                         .replace("RUST", "Rust")

    # Фикс "турель"
    post_text = post_text.replace("тюрель", "турель") \
                         .replace("Тюрель", "Турель") \
                         .replace("тюрели", "турели") \
                         .replace("Тюрели", "Турели") \
                         .replace("tyurel", "turel") \
                         .replace("Tyurel", "Turel")

    # Скриншот — ТОЛЬКО блок нового коммита по ID
    screenshot_bytes = None
    try:
        logger.info(f"[SCREENSHOT] Запуск для НОВОГО коммита {commit_id} → URL: {url}")
        screenshot_path = await make_commit_screenshot(url, commit_id)
        if screenshot_path and os.path.exists(screenshot_path):
            with open(screenshot_path, "rb") as f:
                screenshot_bytes = f.read()
            logger.info(f"[SCREENSHOT] Скриншот успешно загружен (новый): {screenshot_path}")
        else:
            logger.warning(f"[SCREENSHOT] Не удалось сделать скриншот для {commit_id}")
    except Exception as e:
        logger.error(f"[SCREENSHOT] Ошибка скриншота для {commit_id}: {e}")

    # Автопубликация (если включена)
    if auto_publish_enabled:
        photo = BufferedInputFile(screenshot_bytes, filename=f"commit_{commit_id}.png") if screenshot_bytes else None
        await publish_to_channel(bot, post_text, photo, commit_id)
        await mark_as_processed(commit_id)
        logger.info(f"Автопубликация: коммит {commit_id} опубликован с новым скрином")
        await bot.send_message(
            MODERATOR_CHAT_ID,
            f"✅ Автопубликация: коммит {commit_id} опубликован"
        )
        return

    # Ручная модерация
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve_{commit_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{commit_id}"),
        ],
        [
            InlineKeyboardButton(text="✏ Редактировать", callback_data=f"edit_{commit_id}"),
            InlineKeyboardButton(text="🖼 Добавить фото", callback_data=f"image_{commit_id}"),
        ],
        [
            InlineKeyboardButton(text="🔙 В главное меню", callback_data="back_to_menu"),
        ]
    ])

    caption = f"🔥 Новый коммит!\nАвтор: {author}\n\n{post_text}"

    if screenshot_bytes:
        sent = await bot.send_photo(
            MODERATOR_CHAT_ID,
            photo=BufferedInputFile(screenshot_bytes, filename=f"commit_{commit_id}.png"),
            caption=caption,
            reply_markup=keyboard
        )
    else:
        sent = await bot.send_message(
            MODERATOR_CHAT_ID,
            caption,
            reply_markup=keyboard
        )

    moderation_data[commit_id] = {
        'text': post_text,
        'image_bytes': screenshot_bytes,
        'message_id': sent.message_id
    }

    save_moderation_data()
    logger.info(f"Коммит {commit_id} отправлен на модерацию")


# ────────────────────────────────
# Обработчики (без изменений — всё как было)
# ────────────────────────────────

def moderation_handlers(dp: Dispatcher):

    @dp.callback_query(lambda c: c.data == "toggle_auto_publish")
    async def toggle_auto(callback: CallbackQuery):
        global auto_publish_enabled
        auto_publish_enabled = not auto_publish_enabled
        save_settings()

        status = "ВКЛЮЧЕНА" if auto_publish_enabled else "ВЫКЛЮЧЕНА"
        await callback.message.edit_text(
            f"Автопубликация теперь {status}\n\n",
            reply_markup=get_main_menu_keyboard()
        )
        await callback.answer(f"Автопубликация {status}")


    @dp.callback_query(lambda c: c.data.startswith('approve_'))
    async def approve_callback(callback: CallbackQuery):
        commit_id = callback.data.split('_')[1]
        data = moderation_data.pop(commit_id, None)

        if not data:
            await callback.answer("Пост уже обработан или не найден", show_alert=True)
            return

        image = None
        if data.get('image_bytes'):
            image = BufferedInputFile(data['image_bytes'], filename=f"commit_{commit_id}.png")

        await publish_to_channel(callback.bot, data['text'], image, commit_id)
        await mark_as_processed(commit_id)

        await callback.message.edit_text(data['text'] + "\n\n✅ Опубликовано в канал!")
        await callback.answer("Опубликовано!")

        save_moderation_data()


    @dp.callback_query(lambda c: c.data.startswith('reject_'))
    async def reject_callback(callback: CallbackQuery):
        commit_id = callback.data.split('_')[1]
        moderation_data.pop(commit_id, None)
        await callback.message.edit_text("❌ Отклонено")
        await callback.answer("Отклонено")

        save_moderation_data()


    @dp.callback_query(lambda c: c.data.startswith('edit_'))
    async def edit_callback(callback: CallbackQuery, state: FSMContext):
        commit_id = callback.data.split('_')[1]
        if commit_id not in moderation_data:
            await callback.answer("Пост уже обработан", show_alert=True)
            return

        await state.set_state(ModerationStates.waiting_for_edit)
        await state.update_data(commit_id=commit_id)
        await callback.message.reply("Отправьте новый текст поста:")
        await callback.answer()


    @dp.message(ModerationStates.waiting_for_edit)
    async def receive_edit(message: Message, state: FSMContext):
        data = await state.get_data()
        commit_id = data.get('commit_id')

        if commit_id not in moderation_data:
            await message.reply("❌ Сессия устарела")
            await state.clear()
            return

        new_text = message.text.strip()
        if not new_text:
            await message.reply("Текст не может быть пустым")
            return

        moderation_data[commit_id]['text'] = new_text
        await message.reply("Текст обновлён ✓\nВернись к посту и одобри")
        await state.clear()

        save_moderation_data()


    @dp.callback_query(lambda c: c.data.startswith('image_'))
    async def image_callback(callback: CallbackQuery, state: FSMContext):
        commit_id = callback.data.split('_')[1]
        if commit_id not in moderation_data:
            await callback.answer("Пост уже обработан", show_alert=True)
            return

        await state.set_state(ModerationStates.waiting_for_image)
        await state.update_data(commit_id=commit_id)
        await callback.message.reply("Отправьте изображение:")
        await callback.answer()


    @dp.message(ModerationStates.waiting_for_image)
    async def receive_image(message: Message, state: FSMContext):
        if not message.photo:
            await message.reply("Отправьте фото.")
            return

        data = await state.get_data()
        commit_id = data.get('commit_id')

        if commit_id not in moderation_data:
            await message.reply("❌ Сессия устарела")
            await state.clear()
            return

        photo = message.photo[-1]
        file_bytes = await message.bot.download(photo.file_id)
        moderation_data[commit_id]['image_bytes'] = file_bytes.read()

        await message.reply("Фото добавлено ✓\nВернись к посту и одобри")
        await state.clear()

        save_moderation_data()


    @dp.callback_query(lambda c: c.data == "show_pending")
    async def show_pending(callback: CallbackQuery):
        if not moderation_data:
            await callback.message.edit_text(
                "📭 Нет постов на модерации сейчас",
                reply_markup=get_main_menu_keyboard()
            )
            await callback.answer()
            return

        keyboard = InlineKeyboardMarkup(inline_keyboard=[])

        for cid in moderation_data:
            keyboard.inline_keyboard.append([
                InlineKeyboardButton(
                    text=f"Коммит {cid[:8]}...",
                    callback_data=f"view_{cid}"
                ),
                InlineKeyboardButton(
                    text="🗑 Удалить",
                    callback_data=f"delete_pending_{cid}"
                )
            ])

        keyboard.inline_keyboard.append([
            InlineKeyboardButton(text="🔙 Вернуться в меню", callback_data="back_to_menu"),
            InlineKeyboardButton(text="🗑 Удалить ВСЕ посты", callback_data="delete_all_pending")
        ])

        await callback.message.edit_text("📋 Посты на модерации:", reply_markup=keyboard)
        await callback.answer()


    @dp.callback_query(lambda c: c.data.startswith("delete_pending_"))
    async def delete_pending(callback: CallbackQuery):
        commit_id = callback.data.split("_")[-1]

        if commit_id in moderation_data:
            del moderation_data[commit_id]
            save_moderation_data()
            logger.info(f"Пост {commit_id} удалён пользователем")

            await show_pending(callback)
            await callback.answer("Пост удалён ✓")
        else:
            await callback.answer("Пост уже удалён или не найден", show_alert=True)


    @dp.callback_query(lambda c: c.data == "delete_all_pending")
    async def delete_all_pending(callback: CallbackQuery):
        if moderation_data:
            count = len(moderation_data)
            moderation_data.clear()
            save_moderation_data()
            logger.info(f"Все {count} постов удалены пользователем")

            await callback.message.edit_text(
                f"🗑 Все {count} постов удалены.\n\n",
                reply_markup=get_main_menu_keyboard()
            )
            await callback.answer(f"Удалено {count} постов")
        else:
            await callback.answer("Нет постов для удаления", show_alert=True)


    @dp.callback_query(lambda c: c.data == "check_new_commits")
    async def check_new_commits(callback: CallbackQuery):
        await callback.answer("Проверка запущена, подожди 15 сек...")

        await callback.message.edit_text("🔍 Проверка запущена... ⏳\nЧерез 15 секунд будет результат")

        await asyncio.sleep(15)

        try:
            new_commits = await parse_new_commits()
            count = len(new_commits)

            if count == 0:
                result = "📭 Новых коммитов не найдено"
            else:
                result = f"🔥 Найдено **{count}** новых коммитов!\nСкоро придут уведомления"
        except Exception as e:
            logger.error(f"Ошибка при проверке: {e}")
            result = "❌ Ошибка проверки, попробуй позже"

        await callback.message.edit_text(
            result + "\n\n",
            reply_markup=get_main_menu_keyboard()
        )


    @dp.callback_query(lambda c: c.data == "show_last_pending")
    async def show_last_pending(callback: CallbackQuery):
        if not moderation_data:
            await callback.message.edit_text(
                "📭 Нет постов на модерации",
                reply_markup=get_main_menu_keyboard()
            )
        else:
            cid, data = list(moderation_data.items())[-1]
            await callback.message.edit_text(
                f"Последний пост:\n\n{data['text'][:500]}...",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton("🔙 В главное меню", callback_data="back_to_menu")]
                ])
            )
        await callback.answer()


    @dp.callback_query(lambda c: c.data == "help_menu")
    async def help_menu(callback: CallbackQuery):
        text = (
            "Помощь:\n\n"
            "• Бот проверяет коммиты каждые 15 сек\n"
            "• При новом — уведомление с скриншотом (если автопубликация выкл)\n"
            "• Одобрить — публикует в канал с скриншотом\n"
            "• Автопубликация — все коммиты сразу в канал\n"
            "• Посты и скриншоты сохраняются после перезапуска\n"
            "• В списке модерации можно удалять посты по кнопке 🗑"
        )
        await callback.message.edit_text(
            text,
            reply_markup=get_main_menu_keyboard()
        )
        await callback.answer()


    @dp.callback_query(lambda c: c.data == "back_to_menu")
    async def back_to_menu(callback: CallbackQuery):
        await callback.message.edit_text(
            "👋 Главное меню\nВыбери действие:",
            reply_markup=get_main_menu_keyboard()
        )
        await callback.answer()